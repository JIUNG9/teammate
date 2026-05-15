"use client";

import { useEffect, useRef, useState } from "react";

type Citation = { path: string; score: number };
type Meta     = { by_source: Record<string, {count: number; avg_score: number}>; citations: Citation[] };
type Msg      = { role: "user" | "bot"; text: string; meta?: Meta };

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput]       = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send() {
    const q = input.trim();
    if (!q || streaming) return;
    setInput("");
    setStreaming(true);
    setMessages(prev => [...prev, { role: "user", text: q }, { role: "bot", text: "" }]);

    // /api/chat/ask?q=... — SSE stream from chat-api
    const url = `/api/chat/ask?q=${encodeURIComponent(q)}`;
    const evt = new EventSource(url);

    evt.addEventListener("meta", (e: MessageEvent) => {
      const meta = JSON.parse(e.data) as Meta;
      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = { ...next[next.length - 1], meta };
        return next;
      });
    });

    evt.addEventListener("token", (e: MessageEvent) => {
      const { t } = JSON.parse(e.data) as { t: string };
      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = { ...next[next.length - 1], text: next[next.length - 1].text + t };
        return next;
      });
    });

    evt.addEventListener("done", () => {
      evt.close();
      setStreaming(false);
    });

    evt.addEventListener("error", () => {
      evt.close();
      setStreaming(false);
    });
  }

  return (
    <div className="grid grid-cols-12 gap-6 h-[calc(100vh-7rem)]">
      <aside className="col-span-3 bg-white rounded-xl border border-zinc-200">
        <div className="px-4 py-3 border-b border-zinc-100 text-sm font-medium">Recent</div>
        <div className="p-4 text-xs text-zinc-400">Chat history will appear here.</div>
      </aside>

      <main className="col-span-9 bg-white rounded-xl border border-zinc-200 flex flex-col">
        <div ref={scrollerRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {messages.map((m, i) => (
            <Bubble key={i} msg={m} />
          ))}
        </div>
        <div className="border-t border-zinc-100 p-4">
          <form onSubmit={(e) => { e.preventDefault(); send(); }}
                className="flex items-center gap-2 bg-zinc-50 rounded-xl px-3 py-2 border border-zinc-200">
            <input
              className="flex-1 bg-transparent outline-none text-sm"
              placeholder="Ask the brain…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={streaming}
            />
            <button type="submit" disabled={streaming || !input.trim()}
                    className="bg-blue-600 text-white text-sm px-3 py-1 rounded-md disabled:opacity-50">
              {streaming ? "Streaming…" : "Send ↵"}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}

function Bubble({ msg }: { msg: Msg }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-2xl bg-blue-600 text-white px-4 py-3 rounded-2xl rounded-tr-md">{msg.text}</div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-3xl">
        {msg.meta && <SourceBadges meta={msg.meta} />}
        <div className="bg-zinc-50 border border-zinc-200 px-4 py-3 rounded-2xl rounded-tl-md text-sm whitespace-pre-wrap">
          {msg.text}
          {!msg.text && <span className="animate-pulse text-zinc-400">▍</span>}
        </div>
      </div>
    </div>
  );
}

function SourceBadges({ meta }: { meta: Meta }) {
  const entries = Object.entries(meta.by_source);
  return (
    <div className="text-xs text-zinc-500 mb-1 flex items-center gap-2 flex-wrap">
      <span>retrieved from:</span>
      {entries.map(([src, s]) => {
        const color =
          s.avg_score >= 0.75 ? "bg-emerald-50 text-emerald-700" :
          s.avg_score >= 0.55 ? "bg-blue-50 text-blue-700" :
                                "bg-amber-50 text-amber-700";
        return (
          <span key={src} className={`px-2 py-0.5 rounded-full ${color}`}>
            {src} <b>{s.avg_score.toFixed(2)}</b> ({s.count})
          </span>
        );
      })}
    </div>
  );
}
