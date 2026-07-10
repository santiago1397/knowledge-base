"""FastAPI app: auth, ForwardAuth, search, streaming chat, lessons, static SPA."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, budget, embed
from .config import settings
from .db import cursor
from .minimax import build_messages, stream_chat
from .retrieval import search


@asynccontextmanager
async def lifespan(app: FastAPI):
    embed.warmup()          # load bge-small before first request
    yield


app = FastAPI(title="Knowledge Base", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ---------- auth ----------
class LoginBody(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response):
    uid = auth.authenticate(body.email, body.password)
    auth.set_session(response, uid)
    return {"ok": True}


@app.post("/api/auth/logout")
def logout(response: Response):
    auth.clear_session(response)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user_id: int = Depends(auth.current_user)):
    return {"user_id": user_id}


@app.get("/auth/verify")
def forward_auth(request: Request):
    """Traefik ForwardAuth target for /media/*: 200 if session valid, else 401."""
    try:
        auth.current_user(request)
    except HTTPException:
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return Response(status_code=200)


# ---------- search (free: no LLM) ----------
@app.get("/api/search")
def search_route(q: str, course: str | None = None,
                 user_id: int = Depends(auth.current_user)):
    if not q.strip():
        return {"results": []}
    return {"results": search(q, settings.TOP_K, course)}


# ---------- chat (streaming; spends MiniMax tokens) ----------
class ChatBody(BaseModel):
    question: str
    course: str | None = None


@app.post("/api/chat")
async def chat_route(body: ChatBody, user_id: int = Depends(auth.current_user)):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Empty question")

    budget.check_and_count_question(user_id)        # rate-limit + kill-switch
    chunks = search(body.question, settings.TOP_K, body.course)
    messages = build_messages(body.question, chunks)

    citations = [
        {"code": c["code"], "title": c["title"], "course": c["course"],
         "start_time": c["start_time"]}
        for c in chunks
    ]

    async def event_stream():
        # send citations first so the UI can render deep-links immediately
        yield f"event: citations\ndata: {json.dumps(citations)}\n\n"
        total_tokens = 0
        try:
            async for delta, tokens in stream_chat(messages):
                if delta:
                    yield f"event: token\ndata: {json.dumps(delta)}\n\n"
                if tokens:
                    total_tokens = tokens
        except Exception as e:                              # noqa: BLE001
            yield f"event: error\ndata: {json.dumps(str(e))}\n\n"
        finally:
            budget.record_tokens(total_tokens)
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------- lessons ----------
@app.get("/api/courses")
def courses(user_id: int = Depends(auth.current_user)):
    with cursor() as cur:
        cur.execute("SELECT slug, title FROM courses ORDER BY title")
        return {"courses": [{"slug": s, "title": t} for s, t in cur.fetchall()]}


@app.get("/api/lessons")
def lessons(course: str | None = None, user_id: int = Depends(auth.current_user)):
    sql = ("SELECT l.code, l.title, l.duration, l.tags, c.slug AS course "
           "FROM lessons l JOIN courses c ON c.id = l.course_id")
    params: list = []
    if course:
        sql += " WHERE c.slug = %s"
        params.append(course)
    sql += " ORDER BY l.title"
    with cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return {"lessons": [dict(zip(cols, r)) for r in cur.fetchall()]}


@app.get("/api/lessons/{code}")
def lesson_detail(code: str, user_id: int = Depends(auth.current_user)):
    with cursor() as cur:
        cur.execute(
            "SELECT l.code, l.title, l.duration, l.source_url, l.video_url, "
            "l.video_file, l.summary, l.key_points, l.tags, l.content_md, "
            "l.transcript, c.slug AS course "
            "FROM lessons l JOIN courses c ON c.id = l.course_id WHERE l.code=%s",
            (code,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lesson not found")
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


# ---------- static SPA (built into the image) ----------
if os.path.isdir(settings.WEB_DIST):
    app.mount("/", StaticFiles(directory=settings.WEB_DIST, html=True), name="web")
