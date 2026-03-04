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
  ticker: string;
  status: string;
  fundamentals_count: number;
  prices_count: number;
}

export interface AnalyzeResponse {
  analysis_id: string;
  ticker: string;
  status: string;
  fundamental_out: FundamentalOutput;
  token_usage: { input_tokens: number; output_tokens: number };
  model_routing: {
    model_used: string;
    tier: string;
    degraded: boolean;
    fallback_from: string | null;
  };
}

export interface ExtractClaimsResponse {
  analysis_id: string;
  claims_count: number;
  claims: ClaimRaw[];
}

export interface VerifyResponse {
  analysis_id: string;
  verified: number;
  consistent: number;
  unverified: number;
  disputed: number;
  manual_check: number;
  total: number;
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
  id: string;
  user_id: string;
  analysis_id: string;
  ticker: string;
  action: "BUY" | "SELL";
  shares: number;
  price: number;
  order_type: string;
  stop_loss: number | null;
  status: string;
  broker: string;
  broker_order_id: string | null;
  proposed_at: string;
  approved_at: string | null;
  executed_at: string | null;
  rejection_reason: string | null;
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

export interface KillSwitchEvaluateResponse {
  kill_switch_activated: boolean;
  triggers: Record<
    string,
    {
      triggered: boolean;
      current_value: number | null;
      threshold: number | null;
      message: string;
    }
  >;
  rate_pct: number | null;
  verified_count: number | null;
  total_claims: number | null;
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
