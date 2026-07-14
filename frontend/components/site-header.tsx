"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, Circle, HelpCircle, Plus } from "lucide-react";
import { useHeader } from "@/components/app/HeaderContext";

export function SiteHeader() {
  const pathname = usePathname();
  const { header } = useHeader();
  const hasOverride = Boolean(header.title || header.subtitle || header.badge || header.actions);

  return (
    <header className="sticky top-0 z-30 flex min-h-16 shrink-0 items-center border-b border-border bg-secondary/80 backdrop-blur-md">
      <div className="flex w-full items-center justify-between gap-3 px-4 lg:px-6">
        <div className="flex min-w-0 items-center gap-4">
          {pathname === "/" ? null : (
            <Link
              href="/"
              className="grid size-10 shrink-0 place-items-center rounded-full text-muted-foreground transition hover:bg-muted"
              aria-label="Geri dön"
            >
              <ArrowLeft className="size-5" aria-hidden="true" />
            </Link>
          )}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="truncate text-lg font-semibold tracking-tight text-foreground">
                {header.title ?? routeTitle(pathname)}
              </h1>
              {header.badge}
            </div>
            <p className="truncate text-xs font-medium text-muted-foreground">
              {header.subtitle ?? defaultSubtitle(pathname)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {hasOverride ? (
            header.actions
          ) : (
            <>
              <div className="hidden items-center rounded-full border border-border bg-secondary px-4 py-2 text-sm font-medium tabular-nums text-foreground md:flex">
                <Circle className="mr-2 size-3 fill-primary text-primary" aria-hidden="true" />
                00:00:00
              </div>
              <button className="grid size-10 place-items-center rounded-full text-muted-foreground transition hover:bg-muted" type="button" aria-label="Yardım">
                <HelpCircle className="size-5" aria-hidden="true" />
              </button>
              <Link
                href="/session/new"
                className="hidden h-10 items-center justify-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary lg:inline-flex"
              >
                <Plus className="size-4" aria-hidden="true" />
                Yeni Görüşme
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

function routeTitle(pathname: string) {
  if (pathname === "/") return "Hastalar";
  if (pathname.startsWith("/patients/")) return "Hasta Detayı";
  if (pathname === "/session/new") return "Yeni Görüşme";
  if (pathname.startsWith("/session/")) return "Görüşme İncelemesi";
  return "Dashboard";
}

function defaultSubtitle(pathname: string) {
  if (pathname.startsWith("/session/")) return "Görüşme ayrıntıları yükleniyor";
  return "Tandela TR";
}
