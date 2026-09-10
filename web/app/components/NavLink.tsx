"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** Sidebar link; `external` marks pages still served by Django (full navigation, no prefetch). */
export function NavLink({ href, external, children }: { href: string; external?: boolean; children: React.ReactNode }) {
  const pathname = usePathname();
  const active = !external && (pathname === href || pathname.startsWith(`${href}/`));
  const className = "flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-neutral-100";
  const style = active ? { background: "#0a0a0a", color: "#fff" } : undefined;
  if (external) {
    return (
      <a href={href} className={className} style={style}>
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={className} style={style}>
      {children}
    </Link>
  );
}
