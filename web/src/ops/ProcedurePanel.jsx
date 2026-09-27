import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { RobotView } from "@/components/robot-view.jsx";
import { COVER_NODE, PROCEDURE, REPLAYS } from "@/demo/fixtures.js";

// Stand-in for Ali's 3D procedure player (web/src/three): highlights the cover and walks the steps.
export function ProcedurePanel({ className, stepMs = 2600 }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setStep((s) => (s + 1) % PROCEDURE.steps.length), stepMs);
    return () => clearInterval(id);
  }, [stepMs]);

  return (
    <Card className={cn("relative gap-0 overflow-hidden p-0", className)}>
      <div className="absolute inset-0">
        <RobotView status="healthy" replay={REPLAYS.standing} playKey={0} view="part" highlight={COVER_NODE} labels={false} />
      </div>
      <CardHeader className="pointer-events-none relative p-4">
        <CardTitle className="flex items-center justify-between font-mono text-sm">
          <span>{PROCEDURE.title}</span>
          <Badge variant="outline" className="bg-background/70 font-mono">v1.0 · {PROCEDURE.source}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pointer-events-none relative mt-auto p-4">
        <ol className="space-y-1.5 rounded-lg border bg-background/80 p-3 backdrop-blur">
          {PROCEDURE.steps.map((s, i) => (
            <li
              key={s.title}
              className={cn(
                "flex gap-3 rounded-md px-2 py-1.5 font-mono text-sm transition-colors",
                i === step ? "bg-primary/15 text-foreground" : "text-muted-foreground",
              )}
            >
              <span className={cn("w-5 shrink-0 text-right", i === step && "text-primary")}>{i + 1}</span>
              <span>
                {s.title}
                {i === step && <span className="block text-xs text-muted-foreground">{s.detail}</span>}
              </span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
