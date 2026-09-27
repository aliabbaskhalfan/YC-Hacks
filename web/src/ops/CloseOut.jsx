import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { CLOSEOUT } from "@/demo/fixtures.js";

function Stat({ value, label, tone }) {
  return (
    <Card size="sm" className="gap-1">
      <CardContent>
        <div className={cn("font-mono text-4xl font-semibold tabular-nums", tone)}>{value}</div>
        <div className="mt-1 font-mono text-sm text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  );
}

export function CloseOut({ className }) {
  const rows = CLOSEOUT.crackedCovers;
  return (
    <div className={cn("grid grid-cols-[1fr_1fr_1fr_1.6fr] gap-3 animate-in fade-in slide-in-from-bottom-2 duration-500", className)}>
      <Stat value={rows.length} label="thigh cover cracks" tone="text-destructive" />
      <Stat value={new Set(rows.map((r) => r.site)).size} label="sites" />
      <Stat value="1" label="proven fix, reused" tone="text-success" />
      <Card size="sm" className="gap-2">
        <CardHeader>
          <CardTitle className="font-mono text-sm">fr.thigh.cover across the fleet</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 font-mono text-sm">
          {rows.map((r) => (
            <div key={r.unit} className="flex justify-between gap-3">
              <span>{r.unit} · {r.site}</span>
              <span className="text-muted-foreground">{r.how} · {r.fix}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
