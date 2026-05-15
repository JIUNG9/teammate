"use client";
export default function WatchPage() {
  return (
    <div className="bg-white rounded-xl border border-zinc-200 p-6 text-sm">
      <div className="font-semibold mb-2">Watch (MTTD)</div>
      <p className="text-zinc-600 mb-4">
        Watch-list YAML lives in your brain repo under <code>watchlist/*.yaml</code>.
        Sync to SigNoz is performed by the <code>teammate-watchlist-sync</code> CronJob every 5 minutes.
      </p>
      <p className="text-zinc-600">
        Past-incident similarity search is available via the chat-api{" "}
        <code>POST /search</code> endpoint with a filter on{" "}
        <code>archive/jira/INCD/</code>.
      </p>
    </div>
  );
}
