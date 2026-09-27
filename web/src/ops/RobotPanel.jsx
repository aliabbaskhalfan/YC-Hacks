import { TriangleAlertIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { RobotView } from "@/components/robot-view.jsx";
import { LIVE_UNIT, RECORD, REPLAYS, WHAT_WENT_WRONG, WORK_ORDERS, siteLabel, UNITS } from "@/demo/fixtures.js";
import { useDemo } from "@/demo/DemoContext.jsx";
import { STATUS } from "./status.js";

// go2-02 lives in the data center aisle; go2-17 (a construction site) stays in the plain studio view.
const DC_VIEW = { [REPLAYS.walk]: "dc-walk", [REPLAYS.tripFall]: "dc-aisle" };

export function RobotPanel({ unitId, caption, className }) {
  const { units, robot, onReplayEvent } = useDemo();
  const status = units[unitId];
  const s = STATUS[status];
  const wo = WORK_ORDERS[unitId];
  const site = wo?.site ?? siteLabel(UNITS.find((u) => u.unit_id === unitId)?.site);
  const alerting = status === "red" || status === "in_repair";
  const dataCenter = unitId === LIVE_UNIT;

  return (
    <Card className={cn("relative gap-0 overflow-hidden p-0", alerting && "ring-destructive/60", className)}>
      <div className="absolute inset-0">
        <RobotView
          status={status}
          replay={robot.replay}
          playKey={robot.playKey}
          onReplayEvent={onReplayEvent}
          env={dataCenter ? "datacenter" : null}
          view={dataCenter ? DC_VIEW[robot.replay] ?? "dc-close" : "close"}
        />
      </div>

      <div className="pointer-events-none relative flex items-start justify-between gap-3 p-4">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="h-7 gap-2 bg-background/70 px-2.5 font-mono text-sm backdrop-blur">
            <span className={cn("size-2 rounded-full", s.dot)} />
            {unitId} · {site}
          </Badge>
          {caption && <span className="font-mono text-sm text-muted-foreground">{caption}</span>}
        </div>
        <Badge variant="outline" className={cn("h-7 bg-background/70 px-2.5 font-mono text-sm backdrop-blur", s.text)}>
          {s.label}
        </Badge>
      </div>

      {alerting && (
        <div className="pointer-events-none absolute inset-x-4 bottom-4">
          <Alert variant="destructive" className="border-destructive/60 bg-background/85 backdrop-blur animate-in fade-in slide-in-from-bottom-2">
            <TriangleAlertIcon />
            <AlertTitle className="text-base">{WHAT_WENT_WRONG}</AlertTitle>
            <AlertDescription className="font-mono">
              {wo?.cause ?? "Fall detected"}
              {unitId === RECORD.unit_id && ` · impact ${RECORD.reported_by_robot.impact_force_n} N (sim value)`} · part{" "}
              {RECORD.reported_by_robot.part_id}
            </AlertDescription>
          </Alert>
        </div>
      )}
    </Card>
  );
}
