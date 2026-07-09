"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Plus } from "lucide-react";

export function TopBar() {
  const pathname = usePathname();
  const title = routeTitle(pathname);

  return (
    <header className="sticky top-0 z-30 border-b bg-card/90 backdrop-blur">
      <div className="flex min-h-16 flex-wrap items-center justify-between gap-3 px-4 py-3 md:px-6">
        <div>
          <p className="text-xs font-medium text-muted-foreground">Tandela TR</p>
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        </div>
        <Link
          href="/session/new"
          className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/80"
        >
          <Plus className="size-4" aria-hidden="true" />
          Yeni Görüşme
        </Link>
      </div>
    </header>
  );
}

function routeTitle(pathname: string) {
  if (pathname === "/") return "Hastalar";
  if (pathname.startsWith("/patients/")) return "Hasta Detayı";
  if (pathname === "/session/new") return "Yeni Görüşme";
  if (pathname.startsWith("/session/")) return "Review Workspace";
  return "Tandela";
}
