import { useEffect, useRef, useState } from "react";
import {
  Routes, Route, Link, Navigate, useNavigate, useParams, useSearchParams,
} from "react-router-dom";
import { api, chatStream } from "./api.js";

const fmt = (s) =>
  s == null ? "" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// Lessons arrive already sorted (module_order, lesson_order). Collapse them into
// consecutive module groups, preserving that order.
function groupByModule(lessons) {
  const groups = [];
  for (const l of lessons) {
    const title = l.module_title || "";
    const last = groups[groups.length - 1];
    if (last && last.title === title) last.items.push(l);
    else groups.push({ title, items: [l] });
  }
  return groups;
}

export default function App() {
  const [authed, setAuthed] = useState(null); // null=loading
  useEffect(() => {
    api.me().then(() => setAuthed(true)).catch(() => setAuthed(false));
  }, []);

  if (authed === null) return <div className="center">Loading…</div>;
  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  return (
    <>
      <nav className="nav">
        <Link to="/"><strong>Courses</strong></Link>
        <Link to="/multi-chat">Multi-Course Chat</Link>
        <span className="grow" />
        <a href="#" onClick={(e) => { e.preventDefault(); api.logout().then(() => location.reload()); }}>
          Sign out
        </a>
      </nav>
      <div className="wrap">
        <Routes>
          <Route path="/" element={<CourseGrid />} />
          <Route path="/course/:slug" element={<CoursePage />} />
          <Route path="/lesson/:code" element={<Lesson />} />
          <Route path="/multi-chat" element={<MultiChat />} />
          <Route path="/chat" element={<Navigate to="/multi-chat" replace />} />
        </Routes>
      </div>
    </>
  );
}

function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try { await api.login(email, pw); onLogin(); }
    catch { setErr("Invalid credentials or account locked."); }
  };
  return (
    <div className="center">
      <form className="login card" onSubmit={submit}>
        <h2>Knowledge Base</h2>
        <p className="muted">Sign in to continue.</p>
        <p><input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} /></p>
        <p><input type="password" placeholder="Password" value={pw} onChange={(e) => setPw(e.target.value)} /></p>
        {err && <p className="muted" style={{ color: "#c00" }}>{err}</p>}
        <button type="submit">Sign in</button>
      </form>
    </div>
  );
}

function CourseGrid() {
  const [courses, setCourses] = useState([]);
  useEffect(() => { api.courses().then((d) => setCourses(d.courses)); }, []);
  return (
    <div className="grid-cards">
      {courses.map((c) => (
        <Link className="card course-card" key={c.slug} to={`/course/${c.slug}`}>
          <h3>{c.title}</h3>
        </Link>
      ))}
    </div>
  );
}

function CoursePage() {
  const { slug } = useParams();
  const [tab, setTab] = useState("lessons"); // "lessons" | "chat"
  const [courseTitle, setCourseTitle] = useState("");
  useEffect(() => {
    api.courses().then((d) => {
      setCourseTitle(d.courses.find((c) => c.slug === slug)?.title || slug);
    });
  }, [slug]);

  return (
    <>
      <p><Link to="/">← All courses</Link></p>
      <h2>{courseTitle}</h2>
      <div className="tabs" style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button type="button" onClick={() => setTab("lessons")} disabled={tab === "lessons"}>Lessons</button>
        <button type="button" onClick={() => setTab("chat")} disabled={tab === "chat"}>Chat</button>
      </div>
      {tab === "lessons" ? <Library course={slug} /> : <Chat course={slug} />}
    </>
  );
}

function MultiChat() {
  const [courses, setCourses] = useState([]);
  const [selected, setSelected] = useState([]);
  useEffect(() => { api.courses().then((d) => setCourses(d.courses)); }, []);

  const toggle = (slug) =>
    setSelected((s) => (s.includes(slug) ? s.filter((x) => x !== slug) : [...s, slug]));

  return (
    <>
      <h2>Multi-Course Chat</h2>
      <p className="muted">Select the courses the AI should search across.</p>
      <div className="chip-picker">
        {courses.map((c) => (
          <button
            key={c.slug}
            type="button"
            className={`tag chip ${selected.includes(c.slug) ? "chip-selected" : ""}`}
            onClick={() => toggle(c.slug)}
          >
            {c.title}
          </button>
        ))}
      </div>
      {selected.length > 0 && (
        <Chat course={selected} showCourseInCitations key={selected.join(",")} />
      )}
    </>
  );
}

function Library({ course }) {
  const [lessons, setLessons] = useState([]);
  const [results, setResults] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => { api.lessons(course).then((d) => setLessons(d.lessons)); }, [course]);

  const runSearch = async (e) => {
    e.preventDefault();
    if (!q.trim()) return setResults(null);
    const d = await api.search(q, course);
    setResults(d.results);
  };

  const list = results
    ? results.map((r, i) => (
        <div className="card" key={i}>
          <Link to={`/lesson/${r.code}${r.start_time != null ? `?t=${Math.floor(r.start_time)}` : ""}`}>
            {r.title}
          </Link>
          <span className="muted"> · {(r.score * 100).toFixed(0)}% · {r.source}</span>
          <div className="muted">{r.text.slice(0, 160)}…</div>
        </div>
      ))
    : groupByModule(lessons).map(({ title, items }) => (
        <section key={title || "_"} className="module">
          {title && <h3 className="module-title">{title}</h3>}
          {items.map((l) => (
            <div className="card" key={l.code}>
              <Link to={`/lesson/${l.code}`}>{l.title}</Link>
              {l.duration && <span className="muted"> · {l.duration}</span>}
              <div>{(l.tags || []).map((t) => <span className="tag" key={t}>{t}</span>)}</div>
            </div>
          ))}
        </section>
      ));

  return (
    <>
      <form onSubmit={runSearch} style={{ display: "flex", gap: 8 }}>
        <input placeholder="Search lessons (free — no AI)…" value={q}
               onChange={(e) => setQ(e.target.value)} />
        <button>Search</button>
        {results && <button type="button" onClick={() => { setResults(null); setQ(""); }}>Clear</button>}
      </form>
      {list}
    </>
  );
}

function Lesson() {
  const { code } = useParams();
  const [params] = useSearchParams();
  const [l, setL] = useState(null);
  const video = useRef(null);
  useEffect(() => { api.lesson(code).then(setL); }, [code]);

  const seek = (t) => { if (video.current) { video.current.currentTime = t; video.current.play(); } };
  const onLoaded = () => { const t = params.get("t"); if (t) seek(Number(t)); };

  if (!l) return <p>Loading…</p>;
  const src = l.video_file ? `/media/${encodeURIComponent(l.course)}/${encodeURIComponent(l.video_file)}` : null;

  return (
    <>
      <p><Link to={l.course ? `/course/${l.course}` : "/"}>← Back</Link></p>
      {l.module_title && <p className="muted">{l.module_title}</p>}
      <h2>{l.title} <span className="muted">{l.duration}</span></h2>
      {src && <video ref={video} src={src} controls onLoadedMetadata={onLoaded} />}
      {l.summary && <><h3>Summary</h3><p>{l.summary}</p></>}
      {l.key_points?.length > 0 && (
        <ul>{l.key_points.map((k, i) => <li key={i}>{k}</li>)}</ul>
      )}
      <div>{(l.tags || []).map((t) => <span className="tag" key={t}>{t}</span>)}</div>
      {l.source_url && <p className="muted"><a href={l.source_url} target="_blank" rel="noreferrer">Original lesson ↗</a></p>}

      {l.transcript?.length > 0 && (
        <>
          <h3>Transcript</h3>
          <div className="grid">
            {l.transcript.map((s, i) => (
              <div className="seg" key={i} onClick={() => seek(s.start)}>
                <span className="muted">{fmt(s.start)}</span> {s.text}
              </div>
            ))}
          </div>
        </>
      )}
      {l.content_md && <><h3>Notes</h3><pre style={{ whiteSpace: "pre-wrap" }}>{l.content_md}</pre></>}
    </>
  );
}

function Chat({ course, showCourseInCitations = false }) {
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState("");
  const [cites, setCites] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const nav = useNavigate();

  const ask = async (e) => {
    e.preventDefault();
    if (!q.trim() || busy) return;
    setBusy(true); setAnswer(""); setCites([]); setErr("");
    await chatStream(q, course, {
      onCitations: setCites,
      onToken: (t) => setAnswer((a) => a + t),
      onError: setErr,
      onDone: () => setBusy(false),
    });
  };

  return (
    <>
      <form onSubmit={ask} style={{ display: "flex", gap: 8 }}>
        <input placeholder="Ask a question about the course…" value={q}
               onChange={(e) => setQ(e.target.value)} />
        <button disabled={busy}>{busy ? "…" : "Ask"}</button>
      </form>
      {err && <p className="muted" style={{ color: "#c00" }}>{err}</p>}
      {answer && <div className="card answer">{answer}</div>}
      {cites.length > 0 && (
        <div className="card">
          <div className="muted">Sources</div>
          {cites.map((c, i) => (
            <div key={i}>
              <a href="#" onClick={(e) => {
                e.preventDefault();
                nav(`/lesson/${c.code}${c.start_time != null ? `?t=${Math.floor(c.start_time)}` : ""}`);
              }}>
                {showCourseInCitations && c.course_title ? `${c.course_title} — ` : ""}
                {c.title}{c.start_time != null ? ` @ ${fmt(c.start_time)}` : ""}
              </a>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
