"use client";

import { useEffect, useState } from "react";

type Status = { vectors_count?: number; points_count?: number; status?: string };

export default function IndexStatusPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [rebuildState, setRebuildState] = useState<"idle" | "running" | "done">("idle");
  const [rebuildInfo, setRebuildInfo] = useState<{job_name?: string; started_by?: string} | null>(null);

  useEffect(() => {
    fetch("/api/chat/index-status").then(r => r.json()).then(setStatus);
  }, []);

  async function rebuild() {
    setRebuildState("running");
    const r = await fetch("/api/chat/reindex", { method: "POST" });
    const data = await r.json();
    setRebuildInfo(data);
  }

  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-8 bg-white rounded-xl border border-zinc-200 p-5">
        <div className="text-sm font-semibold mb-3">Qdrant index status</div>
        {!status ? <div className="text-xs text-zinc-400">Loading…</div> : (
          <div className="grid grid-cols-3 gap-4 text-sm">
            <Stat label="Points" value={status.points_count?.toLocaleString() ?? "—"} />
            <Stat label="Vectors" value={status.vectors_count?.toLocaleString() ?? "—"} />
            <Stat label="Status" value={status.status ?? "—"} />
          </div>
        )}
      </div>
      <aside className="col-span-4 bg-white rounded-xl border border-zinc-200 p-5">
        <div className="text-sm font-semibold mb-2">Rebuild index</div>
        <p className="text-xs text-zinc-500 mb-3">Idempotent. Only changed chunks are re-embedded.</p>
        <button onClick={rebuild} disabled={rebuildState !== "idle"}
                className="w-full bg-blue-600 text-white text-sm py-2 rounded-md disabled:opacity-50">
          {rebuildState === "idle" ? "⟳ Rebuild now" : "Rebuild requested"}
        </button>
        {rebuildInfo && (
          <div className="mt-3 text-xs bg-blue-50 border border-blue-200 rounded p-3">
            <div className="font-semibold text-blue-900">
              {rebuildInfo.job_name ? "Joined rebuild" : "Started rebuild"}
            </div>
            {rebuildInfo.job_name && <div>Job: <code>{rebuildInfo.job_name}</code></div>}
            {rebuildInfo.started_by && <div>Started by: <b>{rebuildInfo.started_by}</b></div>}
          </div>
        )}
      </aside>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );
}
