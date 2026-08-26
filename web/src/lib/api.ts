// 后端 API 封装。契约见仓库 docs/frontend-spec.md

export interface EnvInfo {
  ok: boolean;
  cache: string;
  mock: boolean;
  db: string;
  model: string;
}

export interface SchemaColumn { name: string; type: string }
export interface SchemaTable { name: string; columns: SchemaColumn[] }

export interface MemoryNote { id: number; note: string; created_at: string }

export interface NodeEvent {
  node: string;
  label: string;
  thought?: string;
  ok?: boolean;
  error_kind?: string;
  error_message?: string;
}

export interface Usage {
  llm_calls: number;
  total_tokens: number;
  cost: number;
}

export interface Attempt {
  sql: string;
  ok: boolean;
  error_kind?: string | null;
  error_message?: string | null;
}

export interface FinalPayload {
  status: "ok" | "ok_empty" | "failed" | "budget_exceeded";
  cached: boolean;
  answer: string;
  sql: string | null;
  predicted_sql: string | null;
  columns: string[];
  rows: (string | number | null)[][];
  row_count: number;
  attempts: Attempt[];
  selected_tables: string[] | null;
  hallucination_blocked: boolean;
  chart_url: string | null;
  chart_error: string | null;
  usage: Usage;
  latency_ms: number;
}

export async function fetchEnv(): Promise<EnvInfo> {
  return (await fetch("/healthz")).json();
}

export async function fetchSchema(): Promise<SchemaTable[]> {
  const data = await (await fetch("/api/schema")).json();
  return data.tables;
}

export async function fetchMemory(user = "default"): Promise<MemoryNote[]> {
  const data = await (await fetch(`/api/memory?user=${encodeURIComponent(user)}`)).json();
  return data.notes;
}

export async function addMemory(note: string, user = "default"): Promise<number> {
  const resp = await fetch("/api/memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note, user }),
  });
  return (await resp.json()).id;
}

export async function deleteMemory(id: number, user = "default"): Promise<void> {
  await fetch(`/api/memory/${id}?user=${encodeURIComponent(user)}`, { method: "DELETE" });
}

export interface AskCallbacks {
  onNode: (event: NodeEvent) => void;
  onFinal: (payload: FinalPayload) => void;
  onError: () => void;
}

/** SSE 提问；返回的 EventSource 由调用方负责在 final/停止时 close。 */
export function askStream(
  question: string,
  chart: boolean,
  callbacks: AskCallbacks,
  user = "default",
): EventSource {
  const url =
    `/api/ask?question=${encodeURIComponent(question)}` +
    `&chart=${chart ? 1 : 0}&user=${encodeURIComponent(user)}`;
  const es = new EventSource(url);
  es.addEventListener("node", (e) => callbacks.onNode(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("final", (e) => {
    callbacks.onFinal(JSON.parse((e as MessageEvent).data));
    es.close();
  });
  es.onerror = () => {
    es.close();
    callbacks.onError();
  };
  return es;
}
