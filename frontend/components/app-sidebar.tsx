"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarDays, FilePlus2, FolderOpen, LayoutDashboard, Settings, Users } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { title: "Panel", url: "/dashboard", icon: LayoutDashboard },
  { title: "Hastalar", url: "/", icon: Users },
  { title: "Yeni Görüşme", url: "/session/new", icon: FilePlus2 },
  { title: "Ajanda", url: "/dashboard", icon: CalendarDays },
  { title: "Dosyalar", url: "/dashboard", icon: FolderOpen },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-16 flex-col items-center border-r border-border bg-secondary py-4 md:flex">
      <div className="flex flex-col items-center gap-1">
        <span className="font-heading text-2xl font-bold leading-none text-primary">T</span>
        <span className="text-[9px] font-bold tracking-tighter text-primary">KLİNİK</span>
      </div>

      <nav className="mt-8 flex w-full flex-1 flex-col items-center gap-3 px-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = item.url === "/" ? pathname === "/" : pathname.startsWith(item.url);
          return (
            <Link
              key={item.title}
              href={item.url}
              className={cn(
                "flex w-full flex-col items-center gap-1 rounded-lg p-2 text-[10px] font-semibold text-muted-foreground transition",
                active && "bg-secondary text-primary",
                !active && "hover:bg-muted hover:text-primary",
              )}
            >
              <Icon className="size-5" aria-hidden="true" />
              <span className="max-w-full truncate">{item.title}</span>
            </Link>
          );
        })}
      </nav>

      <div className="flex w-full flex-col items-center gap-3 px-2">
        <Link
          href="/dashboard"
          className="flex w-full flex-col items-center gap-1 rounded-lg p-2 text-[10px] font-semibold text-muted-foreground transition hover:bg-muted hover:text-primary"
        >
          <Settings className="size-5" aria-hidden="true" />
          Ayarlar
        </Link>
        <div className="grid size-8 place-items-center rounded-full border border-border bg-card text-xs font-bold text-primary">
          Dr
        </div>
      </div>
    </aside>
  );
}
