import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function DraftBadge({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  return (
    <Badge
      className={cn(
        "rounded-full border border-amber-300 bg-amber-100 font-semibold text-amber-950 hover:bg-amber-100",
        compact ? "px-2.5 py-0.5" : "px-3 py-1",
        className,
      )}
    >
      {compact ? "Taslak" : "Taslak · Hekim onayı gereklidir"}
    </Badge>
  );
}
