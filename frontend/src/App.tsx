import { useState } from "react";
import { DeployTab } from "./components/DeployTab";
import { DashboardTab } from "./components/DashboardTab";

type Tab = "deploy" | "dashboard";

export function App() {
  const [tab, setTab] = useState<Tab>("deploy");
  const [sessionId, setSessionId] = useState<string | null>(null);

  return (
    <div className="min-h-full bg-gradient-to-br from-slate-50 to-indigo-50 text-slate-900">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Meet AI Agents</h1>
            <p className="text-sm text-slate-500">
              Deploy a four-agent assistant into a Google Meet
            </p>
          </div>
          <nav className="flex gap-2">
            <TabButton active={tab === "deploy"} onClick={() => setTab("deploy")}>
              Deploy
            </TabButton>
            <TabButton
              active={tab === "dashboard"}
              onClick={() => setTab("dashboard")}
              disabled={!sessionId}
            >
              Dashboard
            </TabButton>
          </nav>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">
        {tab === "deploy" && (
          <DeployTab
            onDeployed={(sid) => {
              setSessionId(sid);
              setTab("dashboard");
            }}
          />
        )}
        {tab === "dashboard" && sessionId && <DashboardTab sessionId={sessionId} />}
      </main>
    </div>
  );
}

function TabButton({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
        active
          ? "bg-indigo-600 text-white"
          : "text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent"
      }`}
    >
      {children}
    </button>
  );
}
