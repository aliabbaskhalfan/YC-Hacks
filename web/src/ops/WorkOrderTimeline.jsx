import { BellRingIcon, CircleCheckIcon, ClipboardListIcon, MicIcon, TriangleAlertIcon, WrenchIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Item, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { SponsorBadge } from "@/components/sponsor-badge.jsx";
import { LIVE_UNIT, PIPELINE, WORK_ORDERS } from "@/demo/fixtures.js";
import { useDemo } from "@/demo/DemoContext.jsx";

function Entry({ icon: Icon, tone, title, children, sponsor, working }) {
  return (
    <Item variant="outline" size="sm" className="animate-in fade-in slide-in-from-right-2 duration-300">
      <ItemMedia variant="icon" className={cn("border-transparent bg-transparent", tone)}>
        {working ? <Spinner /> : <Icon />}
      </ItemMedia>
      <ItemContent>
        <ItemTitle className="text-sm">{title}</ItemTitle>
        {children && <ItemDescription className="font-mono text-xs">{children}</ItemDescription>}
      </ItemContent>
      {sponsor && <SponsorBadge sponsor={sponsor} working={working} className="h-6 text-xs" />}
    </Item>
  );
}

export function WorkOrderTimeline({ className }) {
  const { units, workOrders, fix } = useDemo();
  const wo = WORK_ORDERS[LIVE_UNIT];
  const state = workOrders[LIVE_UNIT];
  const unit = units[LIVE_UNIT];
  const repairing = unit === "in_repair" || fix.phase !== "idle";
  const stage = PIPELINE[Math.min(fix.stage, PIPELINE.length - 1)];

  return (
    <Card className={cn("gap-3", className)}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between font-mono text-sm">
          <span>Work order {state ? wo.work_order_id : ""}</span>
          <span className="text-muted-foreground">{state ? state : "none open"}</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!state ? (
          <p className="font-mono text-sm text-muted-foreground">All units healthy. Nobody has filed anything.</p>
        ) : (
          <ItemGroup className="gap-2">
            <Entry icon={TriangleAlertIcon} tone="text-destructive" title="go2-02 reported a hard impact">
              front-right · thigh cover likely cracked · {wo.opened_at}
            </Entry>
            <Entry icon={ClipboardListIcon} tone="text-qm" title={`Work order ${wo.work_order_id} opened`} sponsor="qm">
              {wo.title}
            </Entry>
            <Entry icon={BellRingIcon} tone="text-qm" title="Paged tech-01">
              work order + 3D view of the part sent to phone
            </Entry>
            {repairing && (
              <Entry icon={WrenchIcon} tone="text-warning" title="tech-01 is on the robot">
                closing requires a voice note
              </Entry>
            )}
            {fix.phase !== "idle" && fix.phase !== "recording" && (
              <Entry
                icon={MicIcon}
                tone="text-qm"
                title={fix.phase === "done" ? "Fix note processed" : stage.label}
                sponsor="qm"
                working={fix.phase === "processing"}
              >
                transcribe · extract steps · check against SOP
              </Entry>
            )}
            {state === "closed" && (
              <Entry icon={CircleCheckIcon} tone="text-success" title="Work order closed">
                go2-02 back on its feet, no alerts
              </Entry>
            )}
          </ItemGroup>
        )}
      </CardContent>
    </Card>
  );
}
