"""Vector search over chunks (shared by /search and /chat)."""

from __future__ import annotations

from .db import cursor
from .embed import embed_query


def search(query: str, k: int, course: str | list[str] | None = None) -> list[dict]:
    vec = embed_query(query)
    if isinstance(course, str):
        course = [course]

    # Placeholder order must match the SQL below:
    #   score(vec) , [course] , order-by(vec) , limit(k)
    params: list = [vec]
    where = ""
    if course:
        where = "WHERE c.slug = ANY(%s)"
        params.append(course)
    params += [vec, k]

    sql = f"""
        SELECT ch.text, ch.source, ch.start_time,
               l.code, l.title, c.slug AS course, c.title AS course_title,
               1 - (ch.embedding <=> %s::vector) AS score
        FROM chunks ch
        JOIN lessons l ON l.id = ch.lesson_id
        JOIN courses c ON c.id = ch.course_id
        {where}
        ORDER BY ch.embedding <=> %s::vector
        LIMIT %s
    """
    with cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
