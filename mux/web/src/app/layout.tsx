import type { Metadata } from "next";
import "./globals.css";

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
    <html lang="en" className="dark h-full antialiased">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* Mona Sans + IBM Plex Mono for the room; Inter + JetBrains Mono for the stitch site screens */}
        <link
          href="https://fonts.googleapis.com/css2?family=Mona+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-full flex flex-col bg-[var(--bg)] text-[var(--ink)]">
        {children}
      </body>
    </html>
  );
}
