import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { SITES, UNITS } from "@/demo/fixtures.js";
import { useDemo } from "@/demo/DemoContext.jsx";
import { STATUS } from "./status.js";

function UnitChip({ unitId, status }) {
  const s = STATUS[status];
  const alerting = status !== "healthy";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "flex items-center gap-2 rounded-md border bg-background/60 px-2.5 py-1.5 font-mono text-sm transition-colors",
            alerting && status === "red" && "border-destructive/70 bg-destructive/15",
            alerting && status === "in_repair" && "border-warning/60 bg-warning/10",
            alerting && status === "fixed" && "border-success/60 bg-success/10",
          )}
        >
          <span className="relative flex size-2.5">
            {status === "red" && <span className={cn("absolute inline-flex size-full animate-ping rounded-full", s.dot)} />}
            <span className={cn("relative inline-flex size-2.5 rounded-full", s.dot)} />
          </span>
          {unitId}
        </div>
      </TooltipTrigger>
      <TooltipContent className="font-mono">
        {unitId} · {s.label}
      </TooltipContent>
    </Tooltip>
  );
}

export function FleetGrid({ className }) {
  const { units } = useDemo();
  return (
    <div className={cn("grid auto-rows-min grid-cols-3 gap-3", className)}>
      {SITES.map((site, i) => {
        const siteUnits = UNITS.filter((u) => u.site === site.site_id);
        const alerts = siteUnits.filter((u) => units[u.unit_id] !== "healthy").length;
        return (
          <Card key={site.site_id} size="sm" className={cn(i === 0 && "ring-1 ring-primary/40")}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-2 font-mono text-sm">
                <span>{site.label}</span>
                <span className="flex items-center gap-1.5">
                  {i === 0 && <Badge variant="outline" className="font-mono text-[11px]">night rounds</Badge>}
                  <Badge variant={alerts ? "destructive" : "secondary"} className="font-mono text-[11px]">
                    {alerts ? `${alerts} alert` : `${siteUnits.length} units`}
                  </Badge>
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-1.5">
              {siteUnits.map((u) => (
                <UnitChip key={u.unit_id} unitId={u.unit_id} status={units[u.unit_id]} />
              ))}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
