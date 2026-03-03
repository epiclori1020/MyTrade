import { createClient } from "@/lib/supabase/server";
import { AppSidebar } from "@/components/app-sidebar";
import { BottomNav } from "@/components/bottom-nav";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <SidebarProvider>
      <AppSidebar userEmail={user?.email} />

      <SidebarInset>
        {/* Top header bar */}
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background/80 px-4 backdrop-blur-sm md:px-6">
          <SidebarTrigger className="-ml-1 text-muted-foreground hover:text-foreground" />
          {/* Page title slot — pages can populate this via a shared context or portal in future steps */}
        </header>

        {/* Main content area */}
        <main className="flex-1 overflow-auto p-4 pb-20 md:p-6 md:pb-6">
          {children}
        </main>

        {/* Mobile bottom navigation */}
        <BottomNav />
      </SidebarInset>
    </SidebarProvider>
  );
}
