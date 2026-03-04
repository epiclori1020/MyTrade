// TypeScript interfaces matching backend API response shapes.
// Source of truth: backend Pydantic models + broker_adapter dataclasses.

// --- Fundamental Analysis (from backend/src/agents/fundamental.py) ---

export interface DataPoint {
  value: number | null;
  unit: string; // "USD", "USD_B", "pct", "ratio"
  source: string; // "finnhub", "alpha_vantage", "calculated"
  period: string; // "TTM", "2026-Q1"
  retrieved_at: string; // ISO-8601
}

export interface BusinessModel {
  description: string;
  moat_assessment: string;
  revenue_segments: string;
}

export interface Financials {
  revenue: DataPoint | null;
  net_income: DataPoint | null;
  free_cash_flow: DataPoint | null;
  eps: DataPoint | null;
  roe: DataPoint | null;
  roic: DataPoint | null;
}

export interface Valuation {
  pe_ratio: DataPoint | null;
  pb_ratio: DataPoint | null;
  ev_ebitda: DataPoint | null;
  fcf_yield: DataPoint | null;
  assessment: string; // "undervalued|fairly_valued|overvalued" + reasoning
}

export interface Quality {
  f_score: DataPoint | null;
  z_score: DataPoint | null;
  assessment: string;
}

export interface SourceEntry {
  provider: string;
  endpoint: string;
  retrieved_at: string;
}

export interface FundamentalOutput {
  business_model: BusinessModel;
  financials: Financials;
  valuation: Valuation;
  quality: Quality;
  moat_rating: string; // "none", "narrow", "wide"
  score: number; // 0-100
  risks: string[];
  sources: SourceEntry[];
}

// --- Pipeline Responses ---

export interface PolicyCheckResponse {
  passed: boolean;
  violations: PolicyViolation[];
  policy_snapshot: Record<string, unknown>;
}

export interface PolicyViolation {
  rule: string;
  message: string;
  severity: "blocking" | "warning";
  current_value: number | string | null;
  limit_value: number | string | null;
}

export interface CollectResponse {
  status: string;
  ticker: string;
  fundamentals: Record<string, unknown> | null;
  prices_count: number;
  news: unknown[];
  insider_trades: unknown[];
  errors: string[];
}

export interface AnalyzeResponse {
  analysis_id: string;
  ticker: string;
  status: string;
  fundamental_out: FundamentalOutput | null;
  tokens_used?: number;
  cost_usd?: number;
  error_message?: string | null;
}

export interface ExtractClaimsResponse {
  status: string;
  analysis_id: string;
  claims_count: number;
  claims: ClaimRaw[] | null;
  tokens_used?: number;
  cost_usd?: number;
  error_message?: string | null;
}

export interface VerifyResponse {
  status: string;
  analysis_id: string;
  summary: {
    verified: number;
    consistent: number;
    unverified: number;
    disputed: number;
    manual_check: number;
    has_blocking_disputed: boolean;
  };
  results_count: number;
  error_message?: string | null;
}

// --- Claims & Verification ---

export type ClaimStatus =
  | "verified"
  | "consistent"
  | "unverified"
  | "disputed"
  | "manual_check";

export type ClaimType = "number" | "ratio" | "event" | "opinion" | "forecast";

export interface ClaimRaw {
  claim_id: string;
  claim_text: string;
  claim_type: ClaimType;
  value: number | string | null;
  unit: string;
  ticker: string;
  period: string;
  tier: "A" | "B" | "C";
  required_tier: string;
  trade_critical: boolean;
}

export interface VerificationResult {
  source_verification: {
    provider: string;
    value: number | string | null;
    deviation_pct: number | null;
    retrieved_at: string;
  } | null;
  status: ClaimStatus;
  confidence_adjustment: number;
  verified_at: string;
}

export interface ClaimWithVerification {
  id: string;
  analysis_id: string;
  claim_id: string;
  claim_text: string;
  claim_type: ClaimType;
  value: number | string | null;
  unit: string;
  ticker: string;
  period: string;
  tier: "A" | "B" | "C";
  required_tier: string;
  trade_critical: boolean;
  verification: VerificationResult | null;
}

// --- Policy / Settings ---

export type PolicyMode = "BEGINNER" | "PRESET" | "ADVANCED";
export type PresetId = "beginner" | "balanced" | "active";

export interface UserPolicySettings {
  policy_mode: PolicyMode;
  preset_id: PresetId;
  policy_overrides: Record<string, number>;
  cooldown_until: string | null; // ISO-8601 or null
}

export interface PresetsResponse {
  presets: Record<PresetId, Record<string, number>>;
  constraints: Record<string, { min: number; max: number }>;
}

export interface EffectivePolicy {
  core_pct: number;
  satellite_pct: number;
  max_drawdown_pct: number;
  max_single_position_pct: number;
  max_sector_concentration_pct: number;
  max_trades_per_month: number;
  stop_loss_flag_pct: number;
  em_cap_pct: number;
  cash_reserve_pct: number;
  rebalance_trigger_pct: number;
  forbidden_types: string[];
  em_instruments: string[];
  maturity_stage: number;
  human_confirm_required: boolean;
}

// --- Trading ---

export interface TradeResponse {
  trade_id: string;
  status: string;
  ticker?: string;
  action?: "BUY" | "SELL";
  shares?: number;
  price?: number;
  order_type?: string;
  stop_loss?: number | null;
  broker_order_id?: string | null;
  executed_price?: number | null;
  proposed_at?: string;
  rejection_reason?: string | null;
}

export interface Position {
  ticker: string;
  shares: number;
  avg_price: number;
  current_price: number;
  market_value: number;
}

export interface BrokerAccount {
  total_value: number;
  cash: number;
  buying_power: number;
}

// --- System ---

export interface KillSwitchStatus {
  active: boolean;
  reason: string | null;
  activated_at: string | null;
}

export interface DrawdownTrigger {
  triggered: boolean;
  drawdown_pct?: number;
  threshold_pct?: number;
  current_value?: number;
  highwater_value?: number;
  detail?: string;
}

export interface BrokerCbTrigger {
  triggered: boolean;
  cb_state?: string;
  failure_count?: number;
  detail?: string;
}

export interface VerificationRateTrigger {
  triggered: boolean;
  rate_pct?: number;
  threshold_pct?: number;
  verified_count?: number;
  total_claims?: number;
  detail?: string;
}

export interface KillSwitchEvaluateResponse {
  triggered: boolean;
  triggers: {
    drawdown: DrawdownTrigger;
    broker_cb: BrokerCbTrigger;
    verification_rate: VerificationRateTrigger;
  };
}

export interface BudgetStatus {
  total_spend: number;
  total_cap: number;
  remaining: number;
  utilization_pct: number;
  tiers: Record<
    string,
    {
      spend: number;
      cap: number;
      remaining: number;
      utilization_pct: number;
    }
  >;
  warnings: string[];
}

// --- Analysis Run (from DB) ---

export interface AnalysisRun {
  id: string;
  ticker: string;
  started_at: string;
  status: string;
  fundamental_out: FundamentalOutput | null;
  confidence: number | null;
  recommendation: string | null;
}
