import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardLoading() {
  return (
    <div className="space-y-6">
      {/* Page heading skeleton */}
      <Skeleton className="h-8 w-48 rounded-lg" />

      {/* Hero summary card skeleton */}
      <Skeleton className="h-48 w-full rounded-lg" />

      {/* Three stat cards in a grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Skeleton className="h-32 rounded-lg" />
        <Skeleton className="h-32 rounded-lg" />
        <Skeleton className="h-32 rounded-lg" />
      </div>
    </div>
  );
}
