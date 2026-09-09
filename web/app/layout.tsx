import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { AutoRefresh } from "./components/AutoRefresh";

export const metadata: Metadata = {
  title: "Osir Console",
  description: "What the Osir AI autopilot did, and what it needs you to decide.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <AutoRefresh seconds={15} />
        <header className="border-b" style={{ borderColor: "var(--line)" }}>
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-bold tracking-tight">
              Osir <span style={{ color: "var(--accent)" }}>Console</span>
            </Link>
            <nav className="flex gap-6 text-sm" style={{ color: "var(--muted)" }}>
              <Link href="/">Overview</Link>
              <Link href="/approvals">Approvals</Link>
              <Link href="/runs">Runs</Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
