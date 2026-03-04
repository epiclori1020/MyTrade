"use client";

import { Check, ChevronsUpDown, Search } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { MVP_UNIVERSE } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface TickerSearchProps {
  onAnalyze: (ticker: string) => void;
  disabled?: boolean;
  initialTicker?: string;
}

export function TickerSearch({ onAnalyze, disabled, initialTicker }: TickerSearchProps) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(initialTicker ?? "");

  return (
    <div className="flex items-center gap-3">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className="w-full justify-between sm:w-80"
          >
            {selected ? (
              <span className="font-mono font-medium">
                {selected} —{" "}
                <span className="font-sans text-muted-foreground">
                  {
                    MVP_UNIVERSE.find((u) => u.ticker === selected)
                      ?.name
                  }
                </span>
              </span>
            ) : (
              <span className="text-muted-foreground">Ticker auswählen…</span>
            )}
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80 p-0" align="start">
          <Command>
            <CommandInput placeholder="Ticker suchen…" />
            <CommandList>
              <CommandEmpty>Kein Ticker gefunden.</CommandEmpty>
              <CommandGroup>
                {MVP_UNIVERSE.map((item) => (
                  <CommandItem
                    key={item.ticker}
                    value={`${item.ticker} ${item.name}`}
                    onSelect={() => {
                      setSelected(item.ticker);
                      setOpen(false);
                    }}
                  >
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4",
                        selected === item.ticker
                          ? "opacity-100"
                          : "opacity-0",
                      )}
                    />
                    <span className="font-mono font-medium">
                      {item.ticker}
                    </span>
                    <span className="ml-2 text-muted-foreground">
                      {item.name}
                    </span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {item.sector}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      <Button
        onClick={() => selected && onAnalyze(selected)}
        disabled={!selected || disabled}
        className="bg-accent text-accent-foreground hover:bg-accent/90"
      >
        <Search className="mr-2 h-4 w-4" />
        Analysieren
      </Button>
    </div>
  );
}
