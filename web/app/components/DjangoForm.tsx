"use client";

import { useEffect, useState } from "react";

/**
 * A plain HTML form that posts to a Django view through the same-origin
 * proxy, carrying the CSRF token. Used for flows that must stay a browser
 * navigation (OAuth connect / reconnect redirects, sign out).
 */
export function DjangoForm({
  action,
  children,
  className,
  fields = {},
}: {
  action: string;
  children: React.ReactNode;
  className?: string;
  fields?: Record<string, string>;
}) {
  const [csrf, setCsrf] = useState("");
  useEffect(() => {
    const m = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
    setCsrf(m ? decodeURIComponent(m[1]) : "");
  }, []);
  return (
    <form method="post" action={action} className={className}>
      <input type="hidden" name="csrfmiddlewaretoken" value={csrf} />
      {Object.entries(fields).map(([k, v]) => (
        <input key={k} type="hidden" name={k} value={v} />
      ))}
      {children}
    </form>
  );
}
