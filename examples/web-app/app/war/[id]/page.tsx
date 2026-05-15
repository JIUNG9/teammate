"use client";

import { useEffect, useState } from "react";

type Event = { type?: string; event_type?: string; actor?: string; payload?: any };

export default function WarRoomPage({ params }: { params: { id: string } }) {
  const id = params.id;
  const [snapshot, setSnapshot] = useState<any>(null);
  const [events, setEvents]     = useState<Event[]>([]);
  const [chatInput, setChatInput] = useState("");

  useEffect(() => {
    const evt = new EventSource(`/api/war/incident/${id}/sse`);
    evt.addEventListener("snapshot", (e: MessageEvent) => setSnapshot(JSON.parse(e.data)));
    evt.addEventListener("update",   (e: MessageEvent) => setEvents(prev => [...prev, JSON.parse(e.data)]));
    return () => evt.close();
  }, [id]);

  async function sendChat() {
    const text = chatInput.trim();
    if (!text) return;
    setChatInput("");
    await fetch(`/api/war/incident/${id}/event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: "me", text }),
    });
  }

  async function resolve() {
    if (!confirm("Resolve this incident? Postmortem drafter will run.")) return;
    await fetch(`/api/war/incident/${id}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_state: "resolved", actor: "me" }),
    });
  }

  if (!snapshot) return <div className="text-sm text-zinc-400">Loading war-room…</div>;
  const inc = snapshot.incident ?? {};
  const preload = snapshot.preload ?? null;

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border-2 border-red-300 px-5 py-4 flex items-center justify-between">
        <div>
          <div className="text-xs font-mono text-red-700">{inc.id}</div>
          <div className="text-base font-semibold">{inc.title}</div>
          <div className="text-xs text-zinc-500">state: <b>{inc.state}</b> · severity: {inc.severity}</div>
        </div>
        <button onClick={resolve} className="bg-emerald-600 hover:bg-emerald-700 text-white text-sm px-3 py-1.5 rounded">
          ✓ Resolve
        </button>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-7 space-y-4">
          {preload?.col_1 && (
            <Panel title="① Summary"><p className="text-sm">{preload.col_1}</p></Panel>
          )}
          {preload?.col_2 && (
            <Panel title="② Similar past incidents">
              <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(preload.col_2, null, 2)}</pre>
            </Panel>
          )}
          {preload?.col_3 && (
            <Panel title="③ Candidate root causes (LLM, DRAFT)">
              <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(preload.col_3, null, 2)}</pre>
            </Panel>
          )}
          {preload?.col_5 && (
            <Panel title="⑤ Action checklist">
              <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(preload.col_5, null, 2)}</pre>
            </Panel>
          )}
        </div>

        <div className="col-span-5">
          <div className="bg-white rounded-xl border border-zinc-200 flex flex-col h-[600px]">
            <div className="px-5 py-3 border-b border-zinc-100 text-xs text-zinc-500">🔴 LIVE timeline + chat</div>
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1 text-xs font-mono">
              {events.map((e, i) => (
                <div key={i} className={e.type?.startsWith("mirror") ? "bg-zinc-50 -mx-4 px-4" : ""}>
                  <span className="text-zinc-400">[{e.type ?? e.event_type}]</span>{" "}
                  <span className="text-blue-600">{e.actor}</span>{" "}
                  <span>{JSON.stringify(e.payload)}</span>
                </div>
              ))}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); sendChat(); }} className="border-t border-zinc-100 p-3 flex gap-2">
              <input className="flex-1 bg-zinc-50 rounded px-3 py-1.5 text-sm outline-none"
                     value={chatInput} onChange={(e) => setChatInput(e.target.value)}
                     placeholder="Type to war-room…" />
              <button type="submit" className="bg-blue-600 text-white text-xs px-3 py-1.5 rounded">Send</button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-zinc-200">
      <div className="px-5 py-3 border-b border-zinc-100 text-xs text-zinc-500">{title}</div>
      <div className="px-5 py-3">{children}</div>
    </div>
  );
}
