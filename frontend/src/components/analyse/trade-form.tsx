"use client";

import { CheckCircle, Loader2, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import type { PolicyCheckResponse, TradeResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

interface TradeFormProps {
  ticker: string;
  analysisId: string;
}

export function TradeForm({ ticker, analysisId }: TradeFormProps) {
  const [action, setAction] = useState<"BUY" | "SELL">("BUY");
  const [shares, setShares] = useState("");
  const [price, setPrice] = useState("");
  const [stopLoss, setStopLoss] = useState("");

  const [policyResult, setPolicyResult] =
    useState<PolicyCheckResponse | null>(null);
  const [checkingPolicy, setCheckingPolicy] = useState(false);

  const [proposedTrade, setProposedTrade] = useState<TradeResponse | null>(
    null,
  );
  const [proposing, setProposing] = useState(false);
  const [approving, setApproving] = useState(false);
  const [tradeStatus, setTradeStatus] = useState<string | null>(null);

  async function handlePolicyCheck() {
    if (!shares || !price) return;
    setCheckingPolicy(true);
    setPolicyResult(null);

    try {
      const result = await api.post<PolicyCheckResponse>(
        "/api/policy/full-check",
        {
          ticker,
          action,
          shares: parseFloat(shares),
          price: parseFloat(price),
          analysis_id: analysisId,
          stop_loss: stopLoss ? parseFloat(stopLoss) : null,
        },
      );
      setPolicyResult(result);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Policy-Check fehlgeschlagen",
      );
    } finally {
      setCheckingPolicy(false);
    }
  }

  async function handlePropose() {
    setProposing(true);
    try {
      const result = await api.post<TradeResponse>("/api/trades/propose", {
        ticker,
        action,
        shares: parseFloat(shares),
        price: parseFloat(price),
        analysis_id: analysisId,
        stop_loss: stopLoss ? parseFloat(stopLoss) : null,
      });
      setProposedTrade(result);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Trade-Vorschlag fehlgeschlagen",
      );
    } finally {
      setProposing(false);
    }
  }

  async function handleApprove() {
    if (!proposedTrade) return;
    setApproving(true);
    try {
      const result = await api.post<TradeResponse>(
        `/api/trades/${proposedTrade.trade_id}/approve`,
        {},
      );
      setTradeStatus(result.status);
      toast.success(
        result.status === "executed"
          ? "Paper-Trade ausgeführt"
          : `Trade-Status: ${result.status}`,
      );
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Trade konnte nicht ausgeführt werden",
      );
    } finally {
      setApproving(false);
    }
  }

  async function handleReject() {
    if (!proposedTrade) return;
    try {
      await api.post(`/api/trades/${proposedTrade.trade_id}/reject`, {});
      setTradeStatus("rejected");
      toast.info("Trade abgelehnt");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Ablehnung fehlgeschlagen",
      );
    }
  }

  const hasTradeResult = tradeStatus !== null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Trade-Plan</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Input Form */}
        {!proposedTrade && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Aktion</Label>
              <Select
                value={action}
                onValueChange={(v) => setAction(v as "BUY" | "SELL")}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="BUY">Kaufen</SelectItem>
                  <SelectItem value="SELL">Verkaufen</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Stück</Label>
              <Input
                type="number"
                min="0.01"
                step="0.01"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                placeholder="z.B. 10"
                className="font-mono"
              />
            </div>

            <div className="space-y-2">
              <Label>Limit-Preis ($)</Label>
              <Input
                type="number"
                min="0.01"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="z.B. 180.50"
                className="font-mono"
              />
            </div>

            <div className="space-y-2">
              <Label>
                Stop-Loss ($){" "}
                <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                type="number"
                min="0.01"
                step="0.01"
                value={stopLoss}
                onChange={(e) => setStopLoss(e.target.value)}
                placeholder="z.B. 160.00"
                className="font-mono"
              />
            </div>
          </div>
        )}

        {/* Policy Check Button */}
        {!proposedTrade && (
          <Button
            onClick={handlePolicyCheck}
            disabled={!shares || !price || checkingPolicy}
            variant="secondary"
          >
            {checkingPolicy && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Policy prüfen
          </Button>
        )}

        {/* Policy Result */}
        {policyResult && (
          <div
            className={cn(
              "rounded-md border p-3",
              policyResult.passed
                ? "border-verified/30 bg-verified/5"
                : "border-disputed/30 bg-disputed/5",
            )}
          >
            <div className="flex items-center gap-2">
              {policyResult.passed ? (
                <>
                  <CheckCircle className="h-4 w-4 text-verified" />
                  <span className="text-sm font-medium text-verified">
                    Trade erlaubt
                  </span>
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4 text-disputed" />
                  <span className="text-sm font-medium text-disputed">
                    Trade blockiert
                  </span>
                </>
              )}
            </div>
            {!policyResult.passed && policyResult.violations.length > 0 && (
              <ul className="mt-2 space-y-1">
                {policyResult.violations.map((v, i) => (
                  <li key={i} className="text-sm text-disputed">
                    {v.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Propose Button */}
        {policyResult?.passed && !proposedTrade && (
          <Button
            onClick={handlePropose}
            disabled={proposing}
            className="bg-accent text-accent-foreground hover:bg-accent/90"
          >
            {proposing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Trade vorschlagen
          </Button>
        )}

        {/* Approve / Reject */}
        {proposedTrade && !hasTradeResult && (
          <div className="space-y-3">
            <div className="rounded-md border bg-muted/30 p-3">
              <p className="text-sm">
                <span className="font-medium">{action}</span>{" "}
                <span className="font-mono">{shares}</span> × {ticker} @{" "}
                <span className="font-mono">${price}</span>
                {stopLoss && (
                  <span className="text-muted-foreground">
                    {" "}
                    (SL: ${stopLoss})
                  </span>
                )}
              </p>
            </div>
            <div className="flex gap-3">
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    disabled={approving}
                    className="min-h-[44px] flex-1 bg-verified text-white hover:bg-verified/90"
                  >
                    {approving && (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    )}
                    Bestätigen
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Paper-Trade bestätigen</AlertDialogTitle>
                    <AlertDialogDescription>
                      Dies erstellt eine Paper-Trade-Order bei Alpaca. Es wird
                      kein echtes Geld investiert.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                    <AlertDialogAction onClick={handleApprove}>
                      Bestätigen
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>

              <Button
                variant="destructive"
                onClick={handleReject}
                className="min-h-[44px] flex-1"
              >
                Ablehnen
              </Button>
            </div>
          </div>
        )}

        {/* Trade Result */}
        {hasTradeResult && (
          <div
            className={cn(
              "rounded-md border p-3",
              tradeStatus === "executed"
                ? "border-verified/30 bg-verified/5"
                : tradeStatus === "rejected"
                  ? "border-muted bg-muted/30"
                  : "border-disputed/30 bg-disputed/5",
            )}
          >
            <p className="text-sm font-medium">
              {tradeStatus === "executed" && "Paper-Trade ausgeführt"}
              {tradeStatus === "rejected" && "Trade abgelehnt"}
              {tradeStatus === "failed" && "Trade fehlgeschlagen"}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
