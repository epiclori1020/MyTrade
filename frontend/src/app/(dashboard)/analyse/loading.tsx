import { Skeleton } from "@/components/ui/skeleton";

export default function AnalyseLoading() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <Skeleton className="h-8 w-36" />

      {/* Search + button */}
      <div className="flex gap-3">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-10 w-32" />
      </div>

      {/* Empty state card */}
      <Skeleton className="h-32 w-full rounded-lg" />
    </div>
  );
}
