"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Sun, Moon } from "lucide-react";
import { useTheme } from "next-themes";

import { createClient } from "@/lib/supabase/client";
import { NAV_ITEMS } from "@/lib/navigation";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";

interface AppSidebarProps {
  userEmail?: string | null;
}

export function AppSidebar({ userEmail }: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { setTheme, resolvedTheme } = useTheme();
  const supabase = createClient();

  const avatarLetter = userEmail ? userEmail.charAt(0).toUpperCase() : "U";
  const isDark = resolvedTheme === "dark";

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  function toggleTheme() {
    setTheme(isDark ? "light" : "dark");
  }

  return (
    <Sidebar variant="sidebar" collapsible="icon">
      {/* ── Header: Wordmark ── */}
      <SidebarHeader className="px-3 py-4">
        <div className="flex h-8 items-center gap-2 overflow-hidden">
          <span className="text-xl font-semibold leading-none tracking-tight whitespace-nowrap">
            <span className="text-sidebar-foreground">My</span>
            <span className="text-sidebar-primary">Trade</span>
          </span>
        </div>
      </SidebarHeader>

      {/* ── Content: Navigation ── */}
      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
              const isActive =
                pathname === href || pathname.startsWith(href + "/");
              return (
                <SidebarMenuItem key={href}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActive}
                    tooltip={label}
                    size="default"
                  >
                    <Link href={href}>
                      <Icon />
                      <span>{label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      {/* ── Footer: User + Theme ── */}
      <SidebarFooter className="pb-3">
        <SidebarMenu>
          {/* User row */}
          <SidebarMenuItem>
            <div className="flex items-center gap-2 overflow-hidden rounded-md px-2 py-1.5">
              <Avatar size="sm" className="shrink-0">
                <AvatarFallback className="bg-sidebar-accent text-sidebar-accent-foreground text-xs font-medium">
                  {avatarLetter}
                </AvatarFallback>
              </Avatar>
              <span className="min-w-0 flex-1 truncate text-xs text-sidebar-foreground/80 group-data-[collapsible=icon]:hidden">
                {userEmail ?? "Benutzer"}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0 text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground group-data-[collapsible=icon]:hidden"
                onClick={handleSignOut}
                aria-label="Abmelden"
              >
                <LogOut className="size-3.5" />
              </Button>
            </div>
          </SidebarMenuItem>

          {/* Dark mode toggle */}
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={toggleTheme}
              tooltip={isDark ? "Helles Design" : "Dunkles Design"}
              className="text-sidebar-foreground/70 hover:text-sidebar-foreground"
            >
              {isDark ? (
                <>
                  <Sun />
                  <span>Helles Design</span>
                </>
              ) : (
                <>
                  <Moon />
                  <span>Dunkles Design</span>
                </>
              )}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
