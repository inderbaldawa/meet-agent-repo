import { useState } from "react";
import { deploy } from "../api";

export function DeployTab({ onDeployed }: { onDeployed: (sid: string) => void }) {
  const [meetUrl, setMeetUrl] = useState("");
  const [name, setName] = useState("AI Assistant");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await deploy(meetUrl.trim(), name.trim() || "AI Assistant");
      onDeployed(resp.session_id);
    } catch (err) {
      const msg =
        err && typeof err === "object" && "message" in err ? String(err.message) : String(err);
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid md:grid-cols-2 gap-8">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6"
      >
        <h2 className="text-lg font-semibold mb-4">Deploy agents to a meeting</h2>
        <label className="block text-sm font-medium text-slate-700 mb-1">Meet URL</label>
        <input
          type="url"
          required
          placeholder="https://meet.google.com/abc-defg-hij"
          value={meetUrl}
          onChange={(e) => setMeetUrl(e.target.value)}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <label className="block text-sm font-medium text-slate-700 mb-1">Bot display name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 mb-6 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        {error && (
          <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 px-3 py-2 text-sm">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={busy || !meetUrl}
          className="w-full rounded-lg bg-indigo-600 text-white px-4 py-2.5 font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Deploying… (admit the bot in your Meet tab)" : "Deploy"}
        </button>
        <p className="mt-4 text-xs text-slate-500 leading-relaxed">
          After clicking Deploy, switch to your Google Meet tab and click <strong>Admit</strong>{" "}
          when the bot requests to join. The orchestrator waits up to 60s.
        </p>
      </form>

      <aside className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
        <h3 className="text-base font-semibold mb-3">Agents on duty</h3>
        <ul className="space-y-3 text-sm">
          <Agent name="Context" emoji="🔍" desc="Watches the screen via Vision AI, distils a topic" />
          <Agent name="Research" emoji="🔎" desc="Google-searches the topic, summarises one fact" />
          <Agent name="Hype" emoji="🎉" desc="Drops a short chat line + reaction" />
          <Agent name="Moderator" emoji="⚠️" desc="Warns on emoji-spam in chat" />
        </ul>
        <h3 className="text-base font-semibold mt-6 mb-3">What to demo</h3>
        <ol className="list-decimal pl-5 space-y-1.5 text-sm text-slate-600">
          <li>Start a Google Meet as host.</li>
          <li>Paste the URL above and click Deploy.</li>
          <li>Admit the bot when prompted.</li>
          <li>Share screen showing a recognisable book or object.</li>
          <li>Watch the Dashboard light up with research and chat.</li>
        </ol>
      </aside>
    </div>
  );
}

function Agent({ name, emoji, desc }: { name: string; emoji: string; desc: string }) {
  return (
    <li className="flex items-start gap-3">
      <span className="text-xl">{emoji}</span>
      <div>
        <div className="font-medium">{name}</div>
        <div className="text-slate-500">{desc}</div>
      </div>
    </li>
  );
}
