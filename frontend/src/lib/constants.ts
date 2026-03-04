// Frontend constants — mirrors backend source of truth.
// PRESETS: backend/src/services/policy_engine.py:35-72
// CONSTRAINTS: backend/src/services/policy_engine.py:74-84
// MVP_UNIVERSE: backend/src/constants.py

export const MVP_UNIVERSE = [
  { ticker: "AAPL", name: "Apple", sector: "Tech" },
  { ticker: "MSFT", name: "Microsoft", sector: "Tech" },
  { ticker: "JNJ", name: "Johnson & Johnson", sector: "Healthcare" },
  { ticker: "JPM", name: "JPMorgan Chase", sector: "Financials" },
  { ticker: "PG", name: "Procter & Gamble", sector: "Consumer Staples" },
  { ticker: "VOO", name: "Vanguard S&P 500 ETF", sector: "ETF" },
  { ticker: "VWO", name: "Vanguard EM ETF", sector: "ETF" },
] as const;

export const PRESETS = {
  beginner: {
    core_pct: 80,
    satellite_pct: 20,
    max_drawdown_pct: 15,
    max_single_position_pct: 5,
    max_sector_concentration_pct: 25,
    max_trades_per_month: 4,
    stop_loss_flag_pct: 10,
    em_cap_pct: 10,
    cash_reserve_pct: 10,
    rebalance_trigger_pct: 3,
  },
  balanced: {
    core_pct: 70,
    satellite_pct: 30,
    max_drawdown_pct: 20,
    max_single_position_pct: 5,
    max_sector_concentration_pct: 30,
    max_trades_per_month: 8,
    stop_loss_flag_pct: 15,
    em_cap_pct: 15,
    cash_reserve_pct: 5,
    rebalance_trigger_pct: 5,
  },
  active: {
    core_pct: 60,
    satellite_pct: 40,
    max_drawdown_pct: 25,
    max_single_position_pct: 8,
    max_sector_concentration_pct: 35,
    max_trades_per_month: 10,
    stop_loss_flag_pct: 20,
    em_cap_pct: 20,
    cash_reserve_pct: 3,
    rebalance_trigger_pct: 8,
  },
} as const;

export type PresetId = keyof typeof PRESETS;

export const PRESET_META = {
  beginner: {
    label: "Einsteiger",
    description: "Konservativ mit niedrigem Risiko. Ideal für den Start.",
    risk: "low" as const,
  },
  balanced: {
    label: "Balanced",
    description: "Ausgewogenes Verhältnis zwischen Risiko und Rendite.",
    risk: "medium" as const,
    recommended: true,
  },
  active: {
    label: "Aktiv",
    description: "Höheres Risiko, mehr Handlungsspielraum.",
    risk: "high" as const,
  },
} as const;

export interface SliderConfig {
  key: string;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
  microcopy: string;
}

export const SLIDER_CONFIG: SliderConfig[] = [
  {
    key: "satellite_pct",
    label: "Satellite-Anteil",
    unit: "%",
    min: 10,
    max: 40,
    step: 5,
    microcopy:
      "Mehr Satellite = mehr Schwankung & mehr Systemeinfluss auf dein Portfolio.",
  },
  {
    key: "max_drawdown_pct",
    label: "Max Drawdown (Kill-Switch)",
    unit: "%",
    min: 10,
    max: 30,
    step: 1,
    microcopy:
      "Stoppt alle neuen Trades wenn dein Satellite um diesen Wert fällt. Schützt vor Crash-Verlusten.",
  },
  {
    key: "max_single_position_pct",
    label: "Max Einzelposition",
    unit: "%",
    min: 3,
    max: 10,
    step: 1,
    microcopy:
      "Begrenzt wie viel eine einzelne Aktie deines Satellite ausmachen darf.",
  },
  {
    key: "max_sector_concentration_pct",
    label: "Max Sektor-Konzentration",
    unit: "%",
    min: 20,
    max: 40,
    step: 5,
    microcopy:
      "Verhindert dass dein Satellite zum Tech-only-Portfolio wird.",
  },
  {
    key: "max_trades_per_month",
    label: "Max Trades pro Monat",
    unit: "",
    min: 2,
    max: 12,
    step: 1,
    microcopy:
      "Mehr Trades = höhere Kosten & Overtrading-Risiko. Weniger = weniger Chancen.",
  },
  {
    key: "stop_loss_flag_pct",
    label: "Stop-Loss Warnung",
    unit: "%",
    min: 5,
    max: 25,
    step: 1,
    microcopy:
      "Das System warnt dich ab diesem Verlust und prüft ob die Investment-These noch stimmt. Kein Auto-Verkauf.",
  },
  {
    key: "em_cap_pct",
    label: "Emerging Markets Cap",
    unit: "%",
    min: 0,
    max: 25,
    step: 5,
    microcopy:
      "Emerging Markets sind volatiler. Cap begrenzt dein Klumpenrisiko in politisch instabilen Märkten.",
  },
  {
    key: "cash_reserve_pct",
    label: "Cash-Reserve",
    unit: "%",
    min: 0,
    max: 15,
    step: 1,
    microcopy:
      "Trockenpulver für Kaufgelegenheiten. 0% = du musst immer erst verkaufen um zu kaufen.",
  },
  {
    key: "rebalance_trigger_pct",
    label: "Rebalancing-Trigger",
    unit: "%",
    min: 2,
    max: 10,
    step: 1,
    microcopy:
      "Ab dieser Abweichung vom Target schlägt das System Rebalancing vor. Zu eng = zu viele Trades.",
  },
];

export const PIPELINE_STEPS = [
  { key: "pre-check", label: "Policy-Check" },
  { key: "collecting", label: "Daten sammeln" },
  { key: "analyzing", label: "Analyse" },
  { key: "extracting", label: "Claims extrahieren" },
  { key: "verifying", label: "Verifizierung" },
] as const;
