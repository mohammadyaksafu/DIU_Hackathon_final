export type Decision = "ALLOW" | "WARN" | "HOLD";

export interface SignalOut {
  detector: string;
  score: number;
  ok: boolean;
  reason_codes: string[];
}

export interface LangMessage {
  title: string;
  body: string;
  reasons: string[];
}

export interface ScoreResponse {
  transaction_id: string;
  decision: Decision;
  risk_score: number;
  signals: SignalOut[];
  reason_codes: string[];
  customer_message: { en: LangMessage; bn: LangMessage };
  model_version: string;
  policy_version: number;
  policy: { matched: string; variables: Record<string, number>; overrides: string[] };
  latency_ms: number;
  degraded: boolean;
  degraded_reasons: string[];
  alert_id?: number;
}

export interface DemoCustomer {
  id: string;
  name: string;
  persona: string;
  division: string;
  age_band: string;
  kyc_level: number;
  home_geo: string;
  device_id: string | null;
  typical_amount: number | null;
  phone: string;
}

export interface Scenario {
  key: string;
  title: string;
  description: string;
  expected: string;
  title_bn?: string;
  story_bn?: string;
}

export interface ScenarioRun {
  scenario: string;
  setup: string[];
  setup_bn?: string[];
  transaction: TxPayload;
}

export interface TxPayload {
  type: string;
  amount: number;
  sender: string;
  receiver: string;
  device_id?: string | null;
  geo_cell?: string | null;
  channel?: string;
}

export interface AlertSummary {
  id: number;
  tx_id: string;
  created_at: number;
  tx_ts: number;
  tx_type: string;
  sender: string;
  receiver: string;
  amount: number;
  decision: Decision;
  risk_score: number;
  reason_codes: string[];
  status: string;
  label: string | null;
  customer_action: string | null;
  source: string;
}

export interface Contribution {
  feature: string;
  value: number | string | null;
  contribution: number;
}

export interface StoredSignal {
  detector: string;
  score: number;
  ok: boolean;
  reason_codes: string[];
  details: { contributions?: Contribution[]; hits?: string[]; [k: string]: unknown };
}

export interface CaseDetail extends AlertSummary {
  signals: Record<string, StoredSignal>;
  features: Record<string, number>;
  model_version: string;
  policy_version: number;
  reasons: { code: string; en: string; bn: string }[];
  sender_profile: Record<string, unknown>;
  receiver_profile: Record<string, unknown>;
  related: { count: number; same_receiver: number; total_amount_bdt: number; confirmed_fraud: number; items: AlertSummary[] };
  audit: { ts: number; actor: string; event: string; payload: Record<string, unknown> }[];
  ground_truth_scenario: string | null;
}

export interface Narrative {
  summary: string;
  what_happened: string;
  why_risky: { point: string; evidence: string[] }[];
  recommended_actions: string[];
  citations: string[];
  source: "llm" | "template";
  model?: string;
  fallback_reason?: string;
  cached?: boolean;
}

export interface GraphNode {
  id: string;
  kind: "customer" | "agent" | "merchant" | "enterprise";
  community: number;
  in_deg: number;
  comm_fanin: number;
  comm_cashout: number;
  fwd_ratio: number;
  focus: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  count: number;
  amount: number;
  type: string;
}

export interface WalletGraph {
  wallet: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  snapshot: Record<string, number> | null;
}
