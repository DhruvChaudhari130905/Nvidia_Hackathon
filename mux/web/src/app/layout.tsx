import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter, JetBrains_Mono } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";

// Self-hosted at build time (no request to Google from the browser). Mona Sans + IBM Plex Mono for the
// room; Inter + JetBrains Mono for the site screens. globals.css and Tailwind read these variables.
const monaSans = localFont({
  src: "./fonts/MonaSans-latin.woff2",
  weight: "400 700",
  display: "swap",
  variable: "--nf-mona",
});
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], display: "swap", variable: "--nf-plex" });
const inter = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700"], display: "swap", variable: "--nf-inter" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500", "600", "700"], display: "swap", variable: "--nf-jetbrains" });

export const metadata: Metadata = {
  title: "MUX — Multiplayer Coding Agent",
  description: "Eight people steering, one agent building. Google Docs for AI app-building.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`dark h-full antialiased ${monaSans.variable} ${plexMono.variable} ${inter.variable} ${jetbrains.variable}`}
    >
      <body className="min-h-full flex flex-col bg-[var(--bg)] text-[var(--ink)]">
        {children}
      </body>
    </html>
  );
}
