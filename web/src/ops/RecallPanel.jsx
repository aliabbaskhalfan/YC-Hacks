import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { SponsorBadge } from "@/components/sponsor-badge.jsx";
import { DEMO_DATE, PROCEDURE, RECALL_UNIT, WORK_ORDERS } from "@/demo/fixtures.js";

export function RecallPanel({ className }) {
  const wo = WORK_ORDERS[RECALL_UNIT];
  return (
    <Card className={cn("gap-4 animate-in fade-in slide-in-from-right-3 duration-500", className)}>
      <CardHeader>
        <CardTitle className="font-mono text-base">
          {wo.work_order_id} · {wo.unit_id}
        </CardTitle>
        <CardDescription className="font-mono">{wo.cause}. Fell on its right side, same cover.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <SponsorBadge sponsor="memorable" working>Recalled proven fix</SponsorBadge>
          <SponsorBadge sponsor="gbrain">Source: go2-02, {DEMO_DATE}</SponsorBadge>
        </div>

        <div className="rounded-lg border border-primary/40 bg-primary/5 p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="font-mono text-sm font-medium">3D procedure attached</span>
            <Badge variant="secondary" className="font-mono">{PROCEDURE.source}</Badge>
          </div>
          <div className="mb-3 rounded-md border border-warning/50 bg-warning/10 px-3 py-2 font-mono text-sm text-warning">
            IMPORTANT: {PROCEDURE.important}
          </div>
          <ol className="space-y-1 font-mono text-sm text-muted-foreground">
            {PROCEDURE.steps.map((s, i) => (
              <li key={s.title} className="flex gap-3">
                <span className="w-4 text-right text-primary">{i + 1}</span>
                {s.title}
              </li>
            ))}
          </ol>
        </div>

        <p className="font-mono text-sm text-muted-foreground">
          Waiting on the tech's phone before they arrive. No need to experiment.
        </p>
      </CardContent>
    </Card>
  );
}
