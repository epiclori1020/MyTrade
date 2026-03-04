import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { ServiceWorkerRegister } from "@/components/sw-register";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#1a2744" },
    { media: "(prefers-color-scheme: dark)", color: "#0d1526" },
  ],
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export const metadata: Metadata = {
  title: "MyTrade — AI-Powered Decision Support",
  description:
    "AI-powered investment analysis for long-term investors. Decision support, not investment advice.",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "MyTrade",
  },
  formatDetection: { telephone: false },
  icons: { apple: "/icons/apple-touch-icon.png" },
  other: { "mobile-web-app-capable": "yes" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="de" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <TooltipProvider>
            {children}
          </TooltipProvider>
          <Toaster />
        </ThemeProvider>
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
