import { useState } from "react";
import { CheckIcon, ClipboardCheckIcon, TriangleAlertIcon, WrenchIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { RobotView } from "@/components/robot-view.jsx";
import { SponsorBadge } from "@/components/sponsor-badge.jsx";
import { DEMO_DATE, LIVE_UNIT, PIPELINE, PROCEDURE, REPLAYS, WHAT_WENT_WRONG, WORK_ORDERS } from "@/demo/fixtures.js";
import { useDemo } from "@/demo/DemoContext.jsx";
import { STATUS } from "@/ops/status.js";
import { FixNoteDrawer } from "./FixNoteDrawer.jsx";

const WO_STATE = {
  red: { label: "Open", variant: "destructive" },
  in_repair: { label: "In repair", variant: "outline" },
  fixed: { label: "Closed", variant: "secondary" },
  healthy: { label: "Closed", variant: "secondary" },
};

function WorkOrderCard({ wo, status }) {
  const st = WO_STATE[status];
  return (
    <Card size="sm" className="gap-2">
      <CardHeader>
        <CardTitle className="flex items-center justify-between font-mono text-sm">
          <span>{wo.work_order_id}</span>
          <Badge variant={st.variant} className={cn("font-mono", status === "in_repair" && "border-warning/60 text-warning")}>
            {st.label}
          </Badge>
        </CardTitle>
        <CardDescription className="font-mono text-xs">
          {wo.unit_id} · {wo.site} · {wo.opened_at}
        </CardDescription>
      </CardHeader>
      <CardContent className="text-sm">{wo.title}</CardContent>
    </Card>
  );
}

function PipelineCard({ stage }) {
  return (
    <Card size="sm" className="gap-3">
      <CardHeader>
        <SponsorBadge sponsor="qm" working>Processing fix note</SponsorBadge>
      </CardHeader>
      <CardContent className="space-y-2">
        {PIPELINE.map((p, i) => (
          <div key={p.id} className={cn("flex items-center gap-2 font-mono text-sm", i > stage && "text-muted-foreground/50")}>
            {i < stage ? <CheckIcon className="size-4 text-success" /> : i === stage ? <Spinner className="size-4" /> : <span className="size-4" />}
            {p.label}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ResultCard({ record }) {
  return (
    <Card size="sm" className="gap-3 animate-in fade-in slide-in-from-bottom-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <CheckIcon className="size-4 text-success" /> Fix saved · go2-02 is back up
        </CardTitle>
        <CardDescription className="italic">“{record.fix.transcript}”</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ol className="space-y-1 font-mono text-sm">
          {record.fix.steps.map((s, i) => (
            <li key={s} className="flex gap-2">
              <span className="w-4 text-right text-primary">{i + 1}</span>
              {s}
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="border-warning/60 font-mono text-warning">SOP: ADDITION</Badge>
          <span className="text-xs text-muted-foreground">{record.sop_check.reason}</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <SponsorBadge sponsor="gbrain" className="h-6 text-xs">memory</SponsorBadge>
          <SponsorBadge sponsor="memorable" className="h-6 text-xs">graph</SponsorBadge>
        </div>
      </CardContent>
    </Card>
  );
}

function AttachedProcedure() {
  return (
    <Card size="sm" className="gap-3 ring-primary/40">
      <CardHeader>
        <CardTitle className="text-sm">3D procedure attached</CardTitle>
        <CardDescription className="font-mono text-xs">{PROCEDURE.source}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="rounded-md border border-warning/50 bg-warning/10 px-3 py-2 font-mono text-sm text-warning">
          IMPORTANT: {PROCEDURE.important}
        </div>
        <ol className="space-y-1 font-mono text-sm">
          {PROCEDURE.steps.map((s, i) => (
            <li key={s.title} className="flex gap-2">
              <span className="w-4 text-right text-primary">{i + 1}</span>
              {s.title}
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap gap-1.5">
          <SponsorBadge sponsor="memorable" className="h-6 text-xs">Recalled proven fix</SponsorBadge>
          <SponsorBadge sponsor="gbrain" className="h-6 text-xs">go2-02, {DEMO_DATE}</SponsorBadge>
        </div>
      </CardContent>
    </Card>
  );
}

function PhoneBody({ container }) {
  const { techUnit, units, fix, record, startRepair, submitFix } = useDemo();
  const [closing, setClosing] = useState(false);

  if (!techUnit)
    return (
      <Empty className="h-full">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ClipboardCheckIcon />
          </EmptyMedia>
          <EmptyTitle>No open work orders</EmptyTitle>
          <EmptyDescription>Robots page you here when something breaks.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );

  const wo = WORK_ORDERS[techUnit];
  const status = units[techUnit];
  const isLive = techUnit === LIVE_UNIT;
  const open = status === "red" || status === "in_repair";

  return (
    <div className="flex flex-col gap-3 p-3">
      <WorkOrderCard wo={wo} status={status} />
      {open && (
        <Alert variant="destructive" className="border-destructive/60">
          <TriangleAlertIcon />
          <AlertTitle>{WHAT_WENT_WRONG}</AlertTitle>
          <AlertDescription className="text-xs">Reported by {wo.unit_id}: {wo.cause.toLowerCase()}.</AlertDescription>
        </Alert>
      )}
      <div className="relative h-52 overflow-hidden rounded-xl border bg-background">
        <RobotView status={status} replay={REPLAYS.standing} playKey={0} view="part" labels={false} />
      </div>

      {!isLive && <AttachedProcedure />}

      {isLive && fix.phase === "processing" && <PipelineCard stage={fix.stage} />}
      {isLive && fix.phase === "done" && record && <ResultCard record={record} />}

      {open && fix.phase === "idle" && (
        <div className="flex flex-col gap-2">
          {status === "red" ? (
            <Button size="lg" onClick={() => startRepair(techUnit)}>
              <WrenchIcon /> Start repair
            </Button>
          ) : isLive ? (
            <Button size="lg" variant="destructive" onClick={() => setClosing(true)}>
              Close work order
            </Button>
          ) : (
            <p className="text-center font-mono text-xs text-muted-foreground">Follow the attached procedure.</p>
          )}
        </div>
      )}

      {isLive && (
        <FixNoteDrawer
          open={closing}
          onOpenChange={setClosing}
          container={container}
          workOrder={wo}
          onSubmit={submitFix}
        />
      )}
    </div>
  );
}

export function TechPhone() {
  const [screen, setScreen] = useState(null);
  const { techUnit, units } = useDemo();
  const status = techUnit ? units[techUnit] : "healthy";
  return (
    <div className="flex h-full items-center justify-center bg-[#05070a] p-6">
      <div className="relative aspect-[9/19.5] h-full max-h-[900px] rounded-[3rem] border-[10px] border-black shadow-2xl ring-1 ring-border">
        {/* transform makes the drawer's fixed overlay position inside the phone instead of the page */}
        <div ref={setScreen} className="absolute inset-0 flex flex-col overflow-hidden rounded-[2.4rem] bg-background [transform:translateZ(0)]">
          <div className="flex h-9 shrink-0 items-center justify-between px-6 pt-1 font-mono text-xs">
            <span>4:21</span>
            <span className="h-5 w-20 rounded-full bg-black" />
            <span className="flex items-center gap-1">
              <span className={cn("size-2 rounded-full", STATUS[status].dot)} /> 5G
            </span>
          </div>
          <div className="flex items-center justify-between px-4 pb-2">
            <span className="font-mono text-sm font-semibold">Fleetbrain · Field</span>
            <Badge variant="secondary" className="font-mono">tech-01</Badge>
          </div>
          <Separator />
          <ScrollArea className="min-h-0 flex-1">
            <PhoneBody container={screen} />
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}
