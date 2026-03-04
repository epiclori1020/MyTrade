"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function SettingsError({ error, reset }: ErrorProps) {
  useEffect(() => {
    console.error("[Settings] Fehler:", error);
  }, [error]);

  return (
    <div className="flex items-start justify-center pt-16">
      <Card className="w-full max-w-md border-destructive/40">
        <CardHeader>
          <div className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="size-5 shrink-0" />
            <CardTitle className="text-base">
              Einstellungen konnten nicht geladen werden
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Ein unerwarteter Fehler ist aufgetreten. Bitte versuche es erneut.
          </p>
        </CardContent>
        <CardFooter>
          <Button variant="outline" className="min-h-[44px]" onClick={reset}>
            Erneut versuchen
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
