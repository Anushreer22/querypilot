import type { components } from "./api.generated";

// Schema / Table Types
export type ColumnInfo = components["schemas"]["ColumnInfo"];
export type ForeignKeyInfo = components["schemas"]["ForeignKeyInfo"];
export type TableInfo = components["schemas"]["TableInfo"];
export type SchemaResponse = components["schemas"]["SchemaResponse"];

// Health Types
export interface HealthResponse {
  status: string;
  app_db?: string;
  shop_db?: string;
  sample_shop_db?: string;
  [key: string]: unknown;
}

// Query Execution & History
export type ExecuteQueryRequest = components["schemas"]["ExecuteQueryRequest"];
export type ExecuteQueryResponse = components["schemas"]["ExecuteQueryResponse"];
export type QueryHistoryItem = components["schemas"]["QueryHistoryItem"];
export type QueryHistoryResponse = components["schemas"]["QueryHistoryResponse"];

// Ask Types (Phase 4)
export type AskRequest = components["schemas"]["AskRequest"];
export type AskResponse = components["schemas"]["AskResponse"];
export type ClarificationResponse = components["schemas"]["ClarificationResponse"];
export type AskResultPayload = components["schemas"]["AskResultPayload"];

// Agent Types (Phase 5)
export type AgentAskRequest = components["schemas"]["AgentAskRequest"];
export type AgentAskResponse = components["schemas"]["AgentAskResponse"];
export type AgentActionItem = components["schemas"]["AgentActionItem"];
export type AgentQueryResult = components["schemas"]["AgentQueryResult"];
export type AgentRunSummary = components["schemas"]["AgentRunSummary"];
export type AgentRunDetailResponse = components["schemas"]["AgentRunDetailResponse"];

// Optimizer Types (Phase 6)
export interface PlanNode {
  node_type: string;
  relation_name?: string;
  alias?: string;
  index_name?: string;
  startup_cost?: number;
  total_cost?: number;
  plan_rows?: number;
  plan_width?: number;
  actual_startup_time?: number;
  actual_total_time?: number;
  actual_rows?: number;
  actual_loops?: number;
  filter?: string;
  rows_removed_by_filter?: number;
  shared_hit_blocks?: number;
  shared_read_blocks?: number;
  plans?: PlanNode[];
  [key: string]: unknown;
}
export type PlanFinding = components["schemas"]["PlanFinding"];
export type IndexSuggestion = components["schemas"]["IndexSuggestion"];
export type BenchmarkIterationStats = components["schemas"]["BenchmarkIterationStats"];
export type BenchmarkResult = components["schemas"]["BenchmarkResult"];
export type OptimizeRequest = components["schemas"]["OptimizeRequest"];
export type OptimizeResponse = components["schemas"]["OptimizeResponse"];

// UI Mode & Selection Types
export type AppWorkspaceMode = "ask" | "editor";
export type BottomTab = "results" | "plan" | "history";
export type AskEngineType = "agent" | "simple";

