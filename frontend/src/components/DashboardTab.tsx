import { useEffect, useState } from "react";
import {
  collection,
  doc,
  limit,
  onSnapshot,
  orderBy,
  query,
  Timestamp,
} from "firebase/firestore";
import { db } from "../firebase";
import { IncidentFeed, type Incident } from "./IncidentFeed";

type SessionDoc = {
  meet_url?: string;
  display_name?: string;
  status?: string;
  shared_context?: { topic?: string; sentiment?: string; urgency?: number };
  research_data?: { topic?: string; summary?: string; citations?: string[] };
};

type EventDoc = {
  id: string;
  type?: string;
  data?: Record<string, unknown>;
  timestamp?: Timestamp;
};

export function DashboardTab({ sessionId }: { sessionId: string }) {
  const [session, setSession] = useState<SessionDoc | null>(null);
  const [events, setEvents] = useState<EventDoc[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    const unsubSession = onSnapshot(doc(db, "sessions", sessionId), (snap) => {
      setSession(snap.exists() ? (snap.data() as SessionDoc) : null);
    });

    const eventsQ = query(
      collection(db, "sessions", sessionId, "events"),
      orderBy("timestamp", "desc"),
      limit(20),
    );
    const unsubEvents = onSnapshot(eventsQ, (snap) => {
      setEvents(snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<EventDoc, "id">) })));
    });

    const incidentsQ = query(
      collection(db, "sessions", sessionId, "incidents"),
      orderBy("timestamp", "desc"),
      limit(50),
    );
    const unsubIncidents = onSnapshot(incidentsQ, (snap) => {
      setIncidents(snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<Incident, "id">) })));
    });

    return () => {
      unsubSession();
      unsubEvents();
      unsubIncidents();
    };
  }, [sessionId]);

  const ctx = session?.shared_context;
  const research = session?.research_data;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5">
        <div className="text-xs uppercase tracking-wider text-slate-500">Session</div>
        <div className="font-mono text-sm">{sessionId}</div>
        <div className="mt-1 text-sm text-slate-600 break-all">
          {session?.meet_url} · {session?.status || "…"}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <Card title="Current topic" tone="indigo">
          {ctx?.topic ? (
            <>
              <div className="text-2xl font-semibold">{ctx.topic}</div>
              <div className="mt-1 text-sm text-slate-500">
                sentiment {ctx.sentiment} · urgency {ctx.urgency?.toFixed(2)}
              </div>
            </>
          ) : (
            <Empty>Context agent is listening…</Empty>
          )}
        </Card>

        <Card title="Research" tone="rose">
          {research?.summary ? (
            <>
              <div className="text-slate-800 leading-snug">{research.summary}</div>
              {research.citations && research.citations.length > 0 && (
                <ul className="mt-3 space-y-1 text-xs">
                  {research.citations.map((c, i) => (
                    <li key={i}>
                      <a
                        href={c}
                        target="_blank"
                        rel="noreferrer"
                        className="text-indigo-600 hover:underline break-all"
                      >
                        {c}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <Empty>Awaiting topic to research…</Empty>
          )}
        </Card>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <Card title="Live events" tone="slate">
          {events.length === 0 ? (
            <Empty>No events yet — share your screen to trigger one.</Empty>
          ) : (
            <ul className="divide-y divide-slate-100">
              {events.map((e) => (
                <li key={e.id} className="py-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{e.type || "event"}</span>
                    <span className="text-xs text-slate-400">
                      {e.timestamp ? e.timestamp.toDate().toLocaleTimeString() : ""}
                    </span>
                  </div>
                  <EventBody event={e} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Incident feed" tone="amber">
          <IncidentFeed incidents={incidents} />
        </Card>
      </div>
    </div>
  );
}

function Card({
  title,
  tone,
  children,
}: {
  title: string;
  tone: "indigo" | "rose" | "slate" | "amber";
  children: React.ReactNode;
}) {
  const ring = {
    indigo: "border-indigo-100",
    rose: "border-rose-100",
    slate: "border-slate-200",
    amber: "border-amber-100",
  }[tone];
  return (
    <section className={`bg-white rounded-2xl shadow-sm border ${ring} p-5`}>
      <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-3">{title}</h3>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-sm text-slate-400 italic">{children}</div>;
}

function EventBody({ event }: { event: EventDoc }) {
  const d = event.data as Record<string, unknown> | undefined;
  if (!d) return null;
  if (event.type === "screen_analysis") {
    const labels = (d.labels as string[]) || [];
    return (
      <div className="text-xs text-slate-500 mt-0.5">
        {labels.slice(0, 5).join(", ") || "(no labels)"}
      </div>
    );
  }
  if (event.type === "chat_message") {
    return (
      <div className="text-xs text-slate-500 mt-0.5">
        <span className="text-slate-700">{(d.sender as string) || "?"}</span>: {(d.text as string) || ""}
      </div>
    );
  }
  return null;
}
