import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Literal class strings so Tailwind sees every colour it needs.
const SPONSORS = {
  qm: { name: "QM", tone: "border-qm/50 bg-qm/15 text-qm", dot: "bg-qm" },
  gbrain: { name: "GBrain", tone: "border-gbrain/50 bg-gbrain/15 text-gbrain", dot: "bg-gbrain" },
  memorable: { name: "Memorable", tone: "border-memorable/50 bg-memorable/15 text-memorable", dot: "bg-memorable" },
  superset: { name: "Superset", tone: "border-superset/50 bg-superset/15 text-superset", dot: "bg-superset" },
};

export function SponsorBadge({ sponsor, children, working = false, className }) {
  const s = SPONSORS[sponsor];
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-7 gap-2 rounded-md px-2.5 font-mono text-[13px] animate-in fade-in zoom-in-95 duration-300",
        s.tone,
        className,
      )}
    >
      <span className="relative flex size-2">
        {working && <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-75", s.dot)} />}
        <span className={cn("relative inline-flex size-2 rounded-full", s.dot)} />
      </span>
      <span className="font-semibold">{s.name}</span>
      {children && <span className="text-foreground/80">{children}</span>}
    </Badge>
  );
}
