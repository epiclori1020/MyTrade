import { LayoutDashboard, Search, Settings, type LucideIcon } from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Analyse", href: "/analyse", icon: Search },
  { label: "Einstellungen", href: "/settings", icon: Settings },
];
