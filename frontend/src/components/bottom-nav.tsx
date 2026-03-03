"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { NAV_ITEMS } from "@/lib/navigation";

export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 flex h-14 items-stretch border-t border-sidebar-border bg-sidebar md:hidden"
      aria-label="Mobile Navigation"
    >
      {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
        const isActive = pathname === href || pathname.startsWith(href + "/");
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex flex-1 flex-col items-center justify-center gap-0.5 text-sidebar-foreground/60 transition-colors",
              isActive && "text-sidebar-primary"
            )}
            aria-current={isActive ? "page" : undefined}
          >
            <Icon className="size-5 shrink-0" />
            <span className="text-[10px] font-medium leading-none">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
