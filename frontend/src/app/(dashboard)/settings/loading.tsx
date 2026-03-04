import { Skeleton } from "@/components/ui/skeleton";

export default function SettingsLoading() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Skeleton className="h-8 w-48" />

      {/* Preset cards */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>

      {/* Comparison table */}
      <Skeleton className="h-64 w-full" />

      {/* Advanced section */}
      <Skeleton className="h-16 w-full" />
    </div>
  );
}
