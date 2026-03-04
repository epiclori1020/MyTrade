import { Info } from "lucide-react";

export function Disclaimer() {
  return (
    <div className="flex items-start gap-2 rounded-md border border-border/60 bg-muted/30 px-3 py-2">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <p className="text-xs text-muted-foreground">
        Dies ist keine Anlageberatung. Alle Investmententscheidungen liegen bei
        dir. Das System bietet Decision Support — kein Haftungsanspruch.
      </p>
    </div>
  );
}
