"use client";

import { useEffect, useState } from "react";

type Job = { name: string; routine: string; triggered_by: string; status: string; started_at: string };

export default function FeedPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/chat/feed")
      .then(r => r.json())
      .then(data => setJobs(data.recent_jobs ?? []))
      .catch(e => setError(String(e)));
  }, []);

  return (
    <div className="bg-white rounded-xl border border-zinc-200">
      <div className="px-5 py-3 border-b border-zinc-100 text-sm font-semibold">Recent triggered Jobs</div>
      {error && <div className="p-4 text-sm text-red-700">{error}</div>}
      <ul className="divide-y divide-zinc-100 text-sm">
        {jobs.map((j) => (
          <li key={j.name} className="px-5 py-3 flex items-center justify-between">
            <div>
              <div><b>{j.routine}</b> <span className="text-zinc-400">via {j.triggered_by}</span></div>
              <div className="text-xs text-zinc-500">{j.name} · {j.started_at}</div>
            </div>
            <span className={
              j.status === "succeeded" ? "text-emerald-700" :
              j.status === "failed"    ? "text-red-700"     :
                                         "text-amber-700"
            }>{j.status}</span>
          </li>
        ))}
        {jobs.length === 0 && !error && <li className="px-5 py-6 text-xs text-zinc-400">No recent jobs.</li>}
      </ul>
    </div>
  );
}
