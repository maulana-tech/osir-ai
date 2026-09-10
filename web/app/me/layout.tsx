import { Shell } from "@/app/components/Shell";

export const dynamic = "force-dynamic";

export default function MeLayout({ children }: { children: React.ReactNode }) {
  return <Shell>{children}</Shell>;
}
