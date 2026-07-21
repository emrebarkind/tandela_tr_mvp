"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FilePlus2, Users } from "lucide-react";
import { cn } from "@/lib/utils";

const items = [
  { href: "/", label: "Hastalar", icon: Users },
  { href: "/session/new", label: "Yeni Görüşme", icon: FilePlus2 },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-56 border-r bg-card px-3 py-4 md:block">
      <div className="px-2 pb-5">
        <p className="text-base font-semibold">Klinia</p>
        <p className="text-xs text-muted-foreground">Voice clinical notes</p>
      </div>
      <nav className="space-y-1">
        {items.map((item) => {
          const Icon = item.icon;
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors",
                active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
