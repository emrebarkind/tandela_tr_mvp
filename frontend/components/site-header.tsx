"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, Circle, HelpCircle, Plus } from "lucide-react";

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center border-b border-[#C0C9C1] bg-[#E7FEF8]/80 backdrop-blur-md">
      <div className="flex w-full items-center justify-between gap-3 px-4 lg:px-6">
        <div className="flex min-w-0 items-center gap-4">
          <Link
            href="/"
            className="grid size-10 shrink-0 place-items-center rounded-full text-[#404943] transition hover:bg-[#DCF3EC]"
            aria-label="Geri dön"
          >
            <ArrowLeft className="size-5" aria-hidden="true" />
          </Link>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold tracking-tight text-[#0A1F1B]">{routeTitle(pathname)}</h1>
            <p className="truncate text-xs font-medium text-[#404943]">Hasta: Demo Danışan · Bugünkü görüşme</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden items-center rounded-full border border-[#C0C9C1] bg-[#E1F9F2] px-4 py-2 text-sm font-medium tabular-nums text-[#0A1F1B] md:flex">
            <Circle className="mr-2 size-3 fill-[#31634B] text-[#31634B]" aria-hidden="true" />
            00:00:00
          </div>
          <button className="grid size-10 place-items-center rounded-full text-[#404943] transition hover:bg-[#DCF3EC]" type="button" aria-label="Yardım">
            <HelpCircle className="size-5" aria-hidden="true" />
          </button>
          <Link
            href="/session/new"
            className="hidden h-10 items-center justify-center gap-2 rounded-full bg-[#31634B] px-4 text-sm font-semibold text-white transition-colors hover:bg-[#4A7C63] lg:inline-flex"
          >
            <Plus className="size-4" aria-hidden="true" />
            Yeni Görüşme
          </Link>
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
