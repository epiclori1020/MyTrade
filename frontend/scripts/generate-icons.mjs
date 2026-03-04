/**
 * MyTrade PWA Icon Generator
 *
 * Generates all required PWA icons from an SVG template using sharp.
 * Design: Navy (#1a2744) background, Gold (#d4a017) "MT" logotype.
 *
 * Output:
 *   public/icons/icon-192.png          — Home Screen (standard)
 *   public/icons/icon-512.png          — Splash Screen (standard)
 *   public/icons/icon-maskable-512.png — Android Adaptive (20% safe zone)
 *   public/icons/apple-touch-icon.png  — iOS Safari (180x180)
 *
 * Usage: node scripts/generate-icons.mjs
 */

import { createRequire } from "module";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";
import { mkdirSync } from "fs";

const require = createRequire(import.meta.url);
const sharp = require("sharp");

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = resolve(__dirname, "../public/icons");

// Ensure output directory exists
mkdirSync(OUTPUT_DIR, { recursive: true });

// ─── Design tokens (matches globals.css + manifest) ──────────────────────────
const NAVY = "#1a2744";
const GOLD = "#d4a017";

/**
 * Returns an SVG string for the standard icon at the given size.
 * The "MT" logotype sits centered in a navy square.
 *
 * @param {number} size - Canvas dimension in px (square)
 * @param {number} paddingFactor - Extra padding as a fraction of size (0–0.5)
 *                                 Use 0.2 for maskable icons (20% safe zone)
 */
function buildSvg(size, paddingFactor = 0) {
  const pad = Math.round(size * paddingFactor);
  const innerSize = size - pad * 2;

  // Typography scale: "MT" at ~55% of inner width, vertically centered
  const fontSize = Math.round(innerSize * 0.55);
  const cx = size / 2;
  const cy = size / 2;

  // Subtle letterpress shadow for depth without looking cheap
  const shadowOffsetY = Math.round(size * 0.008);
  const shadowBlur = Math.round(size * 0.015);

  return `<svg
    xmlns="http://www.w3.org/2000/svg"
    width="${size}"
    height="${size}"
    viewBox="0 0 ${size} ${size}"
  >
    <defs>
      <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
        <feDropShadow
          dx="0"
          dy="${shadowOffsetY}"
          stdDeviation="${shadowBlur}"
          flood-color="#000000"
          flood-opacity="0.35"
        />
      </filter>
    </defs>

    <!-- Background: deep navy, full bleed -->
    <rect
      x="0" y="0"
      width="${size}" height="${size}"
      fill="${NAVY}"
    />

    <!-- Subtle inner glow ring for premium feel (only visible at larger sizes) -->
    ${
      size >= 192
        ? `<rect
        x="${Math.round(size * 0.04)}"
        y="${Math.round(size * 0.04)}"
        width="${Math.round(size * 0.92)}"
        height="${Math.round(size * 0.92)}"
        rx="${Math.round(size * 0.12)}"
        fill="none"
        stroke="${GOLD}"
        stroke-width="${Math.round(size * 0.012)}"
        opacity="0.18"
      />`
        : ""
    }

    <!-- "MT" logotype centered -->
    <text
      x="${cx}"
      y="${cy}"
      font-family="system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif"
      font-size="${fontSize}"
      font-weight="700"
      font-style="normal"
      fill="${GOLD}"
      text-anchor="middle"
      dominant-baseline="central"
      letter-spacing="${Math.round(size * -0.01)}"
      filter="url(#shadow)"
    >MT</text>
  </svg>`;
}

// ─── Icon definitions ─────────────────────────────────────────────────────────
const ICONS = [
  {
    filename: "icon-192.png",
    size: 192,
    paddingFactor: 0,
    label: "Home Screen (192x192)",
  },
  {
    filename: "icon-512.png",
    size: 512,
    paddingFactor: 0,
    label: "Splash Screen (512x512)",
  },
  {
    filename: "icon-maskable-512.png",
    size: 512,
    paddingFactor: 0.2, // 20% safe zone per maskable spec
    label: "Maskable / Android Adaptive (512x512, 20% pad)",
  },
  {
    filename: "apple-touch-icon.png",
    size: 180,
    paddingFactor: 0,
    label: "Apple Touch Icon (180x180)",
  },
];

// ─── Generate ─────────────────────────────────────────────────────────────────
async function generateIcons() {
  console.log("MyTrade PWA Icon Generator\n");

  for (const icon of ICONS) {
    const outPath = `${OUTPUT_DIR}/${icon.filename}`;
    const svg = buildSvg(icon.size, icon.paddingFactor);

    await sharp(Buffer.from(svg))
      .resize(icon.size, icon.size)
      .png({ compressionLevel: 9, palette: false })
      .toFile(outPath);

    console.log(`  [ok] ${icon.label}`);
    console.log(`       -> public/icons/${icon.filename}`);
  }

  console.log(`\nAll ${ICONS.length} icons generated in public/icons/`);
  console.log(
    "Add apple-touch-icon.png reference to layout.tsx if not already present.\n"
  );
}

generateIcons().catch((err) => {
  console.error("Icon generation failed:", err.message);
  process.exit(1);
});
