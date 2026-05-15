"use client";
import { useState } from "react";

export default function SettingsPage() {
  const [weights, setWeights] = useState({ jira: 1.0, confluence: 1.0, github: 0.8, slack: 0.6 });
  const [floor,  setFloor]    = useState(0.5);

  function save() {
    localStorage.setItem("teammate.source_weights", JSON.stringify(weights));
    localStorage.setItem("teammate.score_floor",    String(floor));
    alert("Saved.");
  }

  return (
    <div className="bg-white rounded-xl border border-zinc-200 p-6 max-w-2xl">
      <div className="font-semibold mb-4">Source weights</div>
      {(["jira", "confluence", "github", "slack"] as const).map(src => (
        <div key={src} className="mb-3">
          <div className="text-sm capitalize">{src}: <b>{weights[src].toFixed(2)}</b></div>
          <input type="range" min={0} max={1.5} step={0.05}
                 value={weights[src]}
                 onChange={e => setWeights(w => ({ ...w, [src]: parseFloat(e.target.value) }))}
                 className="w-full" />
        </div>
      ))}
      <div className="mt-4 mb-3">
        <div className="text-sm">Minimum score floor: <b>{floor.toFixed(2)}</b></div>
        <input type="range" min={0} max={1} step={0.05}
               value={floor}
               onChange={e => setFloor(parseFloat(e.target.value))}
               className="w-full" />
      </div>
      <button onClick={save} className="bg-blue-600 text-white text-sm px-4 py-2 rounded">Save</button>
    </div>
  );
}
