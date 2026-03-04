import { KillSwitchBanner } from "@/components/dashboard/kill-switch-banner";
import { PortfolioSummary } from "@/components/dashboard/portfolio-summary";
import { PositionsTable } from "@/components/dashboard/positions-table";
import { RecentAnalyses } from "@/components/dashboard/recent-analyses";
import { StatusWidgets } from "@/components/dashboard/status-widgets";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data: analyses } = await supabase
    .from("analysis_runs")
    .select("id, ticker, started_at, status, fundamental_out, confidence, recommendation")
    .eq("status", "completed")
    .order("started_at", { ascending: false })
    .limit(5);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>

      <KillSwitchBanner />

      <PortfolioSummary />

      <div className="grid gap-4 md:grid-cols-2">
        <PositionsTable />
        <RecentAnalyses data={analyses ?? []} />
      </div>

      <StatusWidgets />
    </div>
  );
}
