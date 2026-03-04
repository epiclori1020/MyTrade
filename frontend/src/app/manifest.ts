import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "MyTrade — AI-Powered Decision Support",
    short_name: "MyTrade",
    description: "AI-powered investment analysis for long-term investors.",
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#1a2744",
    theme_color: "#1a2744",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
