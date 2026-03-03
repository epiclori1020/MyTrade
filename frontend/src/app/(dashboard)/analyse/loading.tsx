import { Skeleton } from "@/components/ui/skeleton";

export default function AnalyseLoading() {
  return (
    <div className="space-y-6">
      {/* Page heading skeleton */}
      <Skeleton className="h-8 w-36 rounded-lg" />

      {/* Search bar skeleton */}
      <Skeleton className="h-10 w-full rounded-lg" />

      {/* Analysis result cards */}
      <div className="space-y-4">
        <Skeleton className="h-40 w-full rounded-lg" />
        <Skeleton className="h-40 w-full rounded-lg" />
      </div>
    </div>
  );
}
