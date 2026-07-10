// Thin API client. All requests send the session cookie.

async function req(path, opts = {}) {
  const res = await fetch(path, { credentials: "include", ...opts });
  if (res.status === 401) throw { status: 401 };
  if (!res.ok) throw { status: res.status, detail: await res.text() };
  return res.status === 204 ? null : res.json();
}

export const api = {
  me: () => req("/api/auth/me"),
  login: (email, password) =>
    req("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  logout: () => req("/api/auth/logout", { method: "POST" }),
  courses: () => req("/api/courses"),
  lessons: (course) =>
    req("/api/lessons" + (course ? `?course=${encodeURIComponent(course)}` : "")),
  lesson: (code) => req(`/api/lessons/${encodeURIComponent(code)}`),
  search: (q, course) =>
    req(`/api/search?q=${encodeURIComponent(q)}` +
        (course ? `&course=${encodeURIComponent(course)}` : "")),
};

// POST /api/chat and parse the SSE stream. Calls handlers as events arrive.
export async function chatStream(question, course, { onCitations, onToken, onError, onDone }) {
  const res = await fetch("/api/chat", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, course }),
  });
  if (!res.ok) {
    onError?.(res.status === 429 ? "Rate/budget limit reached." : "Chat failed.");
    onDone?.();
    return;
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop();
    for (const frame of frames) {
      const ev = /event: (.*)/.exec(frame)?.[1];
      const data = /data: (.*)/s.exec(frame)?.[1];
      if (!ev || data === undefined) continue;
      const parsed = data ? JSON.parse(data) : null;
      if (ev === "citations") onCitations?.(parsed);
      else if (ev === "token") onToken?.(parsed);
      else if (ev === "error") onError?.(parsed);
      else if (ev === "done") onDone?.();
    }
  }
  onDone?.();
}
