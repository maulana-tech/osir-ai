import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";
import "./globals.css";
import { AutoRefresh } from "./components/AutoRefresh";

// Self-hosted so builds never depend on Google Fonts; same file Studio serves.
const inter = localFont({
  src: "./fonts/inter-latin-wght-normal.woff2",
  variable: "--font-inter",
  weight: "100 900",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Osir Console",
  description: "What the Osir AI autopilot did, and what it needs you to decide.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen">
        <AutoRefresh seconds={15} />
        <header className="border-b" style={{ borderColor: "var(--line)" }}>
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-bold tracking-tight">
              Osir <span style={{ color: "var(--muted)" }}>Console</span>
            </Link>
            <nav className="flex gap-6 text-sm" style={{ color: "var(--muted)" }}>
              <Link href="/" className="hover:text-black">
                Overview
              </Link>
              <Link href="/approvals" className="hover:text-black">
                Approvals
              </Link>
              <Link href="/runs" className="hover:text-black">
                Runs
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
