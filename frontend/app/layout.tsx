import type { Metadata, Viewport } from "next";

import { ChatLauncher } from "@/components/ChatLauncher";
import { Nav } from "@/components/Nav";

import "./globals.css";

export const metadata: Metadata = {
  title: "Shurokkha · AI Trust Copilot",
  description: "Real-time scam interruption, mule-ring detection and an evidence-grounded investigation copilot for MFS.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-page text-ink">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-brand focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-ink">
          Skip to content
        </a>
        <Nav />
        <main id="main" tabIndex={-1} className="animate-rise mx-auto max-w-7xl px-4 py-8 outline-none">{children}</main>
        <ChatLauncher />
        <footer className="border-t border-line/70">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-6 text-xs text-muted">
            <span><strong className="font-semibold text-ink-2">Shurokkha</strong> prototype · AI DEV FEST 2026 · DIU CPC × upay hackathon</span>
            <span>Synthetic data only · The AI explains, humans decide</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
