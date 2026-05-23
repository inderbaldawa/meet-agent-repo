import axios from "axios";

const baseURL = import.meta.env.VITE_ORCH_URL || "http://localhost:8000";

export const orch = axios.create({ baseURL, timeout: 90_000 });

export type DeployResponse = { session_id: string; status: string };

export async function deploy(meetUrl: string, displayName: string, agenda: string): Promise<DeployResponse> {
  const { data } = await orch.post<DeployResponse>("/deploy", {
    meet_url: meetUrl,
    display_name: displayName,
    agenda,
  });
  return data;
}

export async function stopSession(sid: string): Promise<void> {
  await orch.delete(`/session/${sid}`);
}
