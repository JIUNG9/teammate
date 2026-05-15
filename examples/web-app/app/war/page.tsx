"use client";

import { useEffect, useState } from "react";

type Incident = {
  id: string; source: string; state: string; title: string;
  severity?: string; affected_service?: string | null;
};

export default function WarListPage() {
  const [items, setItems] = useState<Record<string, Incident[]>>({ triage: [], open: [], active: [], resolved: [] });

  useEffect(() => {
    Promise.all(
      (["triage","open","active","resolved"] as const).map(state =>
        fetch(`/api/war/incident?state=${state}&limit=20`).then(r => r.json()).then(j => [state, j.incidents ?? []] as const)
      )
    ).then(pairs => {
      const next: Record<string, Incident[]> = {};
      for (const [k, v] of pairs) next[k] = v as Incident[];
      setItems(next);
    });
  }, []);

  return (
    <div className="space-y-6">
      <Section title="Pending triage"     items={items.triage}   color="amber" />
      <Section title="Active war-rooms"   items={items.active}   color="red"   />
      <Section title="Open (preload done, DMs pending)" items={items.open} color="blue" />
      <Section title="Recently resolved"  items={items.resolved} color="emerald" />
    </div>
  );
}

function Section({ title, items, color }: { title: string; items: Incident[]; color: string }) {
  const dot = {
    amber:   "bg-amber-500",
    red:     "bg-red-500",
    blue:    "bg-blue-500",
    emerald: "bg-emerald-500",
  }[color] ?? "bg-zinc-300";
  return (
    <div className="bg-white rounded-xl border border-zinc-200">
      <div className="px-5 py-3 border-b border-zinc-100 text-sm font-semibold flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${dot}`}></span>
        {title}
        <span className="text-xs bg-zinc-100 text-zinc-700 px-2 rounded-full">{items.length}</span>
      </div>
      <ul className="divide-y divide-zinc-100 text-sm">
        {items.map(i => (
          <li key={i.id} className="px-5 py-3 flex items-center justify-between">
            <div>
              <code className="text-xs text-zinc-500">{i.id}</code>
              <span className="ml-2">{i.title}</span>
              {i.affected_service && <span className="ml-2 text-xs text-zinc-500">[{i.affected_service}]</span>}
            </div>
            <a href={`/war/${i.id}`} className="text-xs text-blue-600 hover:underline">open →</a>
          </li>
        ))}
        {items.length === 0 && <li className="px-5 py-6 text-xs text-zinc-400">None.</li>}
      </ul>
    </div>
  );
}
