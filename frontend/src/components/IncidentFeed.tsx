import type { Timestamp } from "firebase/firestore";

export type Incident = {
  id: string;
  agent?: string;
  action?: string;
  reason?: string;
  severity?: "info" | "warning" | "critical" | string;
  timestamp?: Timestamp;
  extra?: Record<string, unknown>;
};

const TONE: Record<string, string> = {
  context_agent: "bg-indigo-50 text-indigo-700 border-indigo-200",
  research_agent: "bg-rose-50 text-rose-700 border-rose-200",
  hype_agent: "bg-amber-50 text-amber-700 border-amber-200",
  moderator_agent: "bg-orange-50 text-orange-700 border-orange-200",
  system: "bg-slate-100 text-slate-700 border-slate-200",
};

export function IncidentFeed({ incidents }: { incidents: Incident[] }) {
  if (incidents.length === 0) {
    return <div className="text-sm text-slate-400 italic">No agent activity yet.</div>;
  }
  return (
    <ul className="space-y-2 max-h-[28rem] overflow-y-auto">
      {incidents.map((inc) => {
        const tone = TONE[inc.agent || "system"] || TONE.system;
        return (
          <li key={inc.id} className={`rounded-lg border ${tone} px-3 py-2`}>
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold uppercase tracking-wide">
                {inc.agent || "system"}
              </span>
              <span className="text-[10px] text-slate-500">
                {inc.timestamp ? inc.timestamp.toDate().toLocaleTimeString() : ""}
              </span>
            </div>
            <div className="text-sm font-medium mt-0.5">{inc.action}</div>
            <div className="text-xs opacity-80">{inc.reason}</div>
          </li>
        );
      })}
    </ul>
  );
}
