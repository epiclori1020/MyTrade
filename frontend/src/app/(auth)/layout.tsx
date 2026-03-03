import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "MyTrade — Anmelden",
  description: "AI-Powered Decision Support for long-term investors.",
};

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-svh w-full items-center justify-center bg-muted px-4 py-12">
      <div className="w-full sm:max-w-md">
        {/* Wordmark */}
        <div className="mb-8 flex flex-col items-center gap-2">
          <span className="text-2xl font-semibold tracking-tight">
            <span className="text-foreground">My</span>
            <span className="text-accent">Trade</span>
          </span>
          <p className="text-sm text-muted-foreground">
            AI-Powered Decision Support
          </p>
        </div>

        {children}
      </div>
    </div>
  );
}
