import { Kbd } from "@/components/ui/kbd";
import { cn } from "@/lib/utils";
import { SponsorBadge } from "@/components/sponsor-badge.jsx";
import { BEATS, useDemo } from "@/demo/DemoContext.jsx";
import { LIVE_UNIT, RECALL_UNIT } from "@/demo/fixtures.js";
import { FleetGrid } from "./FleetGrid.jsx";
import { RobotPanel } from "./RobotPanel.jsx";
import { WorkOrderTimeline } from "./WorkOrderTimeline.jsx";
import { RecordPanel } from "./RecordPanel.jsx";
import { KnowledgeGraph } from "./KnowledgeGraph.jsx";
import { ProcedurePanel } from "./ProcedurePanel.jsx";
import { RecallPanel } from "./RecallPanel.jsx";
import { CloseOut } from "./CloseOut.jsx";

function SponsorTray() {
  const { beat, units, fix } = useDemo();
  const opened = units[LIVE_UNIT] !== "healthy" || fix.phase !== "idle";
  if (beat === 1 || beat === 2) {
    if (fix.phase === "processing")
      return <SponsorBadge sponsor="qm" working>Processing fix note: transcribe, extract steps, check against SOP</SponsorBadge>;
    if (opened) return <SponsorBadge sponsor="qm">Work order opened · tech paged</SponsorBadge>;
  }
  if (beat === 3)
    return (
      <>
        <SponsorBadge sponsor="gbrain">Stored with provenance</SponsorBadge>
        <SponsorBadge sponsor="memorable">Fix path added</SponsorBadge>
      </>
    );
  return null;
}

function Header() {
  const { beat, goBeat } = useDemo();
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b px-5">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg font-semibold tracking-tight">Fleetbrain</span>
        <span className="font-mono text-sm text-muted-foreground">ops</span>
      </div>
      <div className="flex flex-1 items-center gap-2">
        <SponsorTray />
      </div>
      {/* Presenter-only: dim until hovered. */}
      <div className="group flex items-center gap-1.5 opacity-25 transition-opacity hover:opacity-100">
        {BEATS.map((b, i) => (
          <button
            key={b.id}
            onClick={() => goBeat(i)}
            title={`${b.at} ${b.label}`}
            className={cn("size-2.5 rounded-full bg-muted-foreground/40", i === beat && "bg-primary")}
          />
        ))}
        <Kbd className="ml-2 hidden group-hover:inline-flex">1-6</Kbd>
      </div>
    </header>
  );
}

function Scene() {
  const { beat } = useDemo();
  if (beat === 0)
    return (
      <div className="grid h-full grid-cols-[1.35fr_1fr] gap-4">
        <FleetGrid />
        <RobotPanel unitId={LIVE_UNIT} />
      </div>
    );
  if (beat === 1 || beat === 2)
    return (
      <div className="grid h-full grid-cols-[1.6fr_1fr] gap-4">
        <RobotPanel unitId={LIVE_UNIT} />
        <WorkOrderTimeline className="min-h-0 overflow-hidden" />
      </div>
    );
  if (beat === 3)
    return (
      <div className="grid h-full grid-cols-[1.15fr_1fr] gap-4">
        <ProcedurePanel />
        <div className="grid min-h-0 grid-rows-[1.1fr_1fr] gap-4">
          <RecordPanel />
          <KnowledgeGraph />
        </div>
      </div>
    );
  if (beat === 4)
    return (
      <div className="grid h-full grid-cols-[1.35fr_1fr] gap-4">
        <RobotPanel unitId={RECALL_UNIT} />
        <RecallPanel className="min-h-0 overflow-auto" />
      </div>
    );
  return (
    <div className="flex h-full flex-col justify-center gap-6">
      <FleetGrid />
      <CloseOut />
    </div>
  );
}

export function OpsConsole() {
  const { beat } = useDemo();
  return (
    <div className="flex h-full flex-col bg-background">
      <Header />
      <main key={beat} className="min-h-0 flex-1 p-4 animate-in fade-in duration-300">
        <Scene />
      </main>
      <footer className="flex h-11 shrink-0 items-center justify-between gap-3 border-t px-5 font-mono text-xs text-muted-foreground">
        {beat === 5 ? (
          <div className="flex items-center gap-2 text-sm text-foreground animate-in fade-in">
            Built today with
            <SponsorBadge sponsor="gbrain" />
            <SponsorBadge sponsor="memorable" />
            <SponsorBadge sponsor="qm" />
            <SponsorBadge sponsor="superset">parallel coding agents</SponsorBadge>
          </div>
        ) : (
          <span>Own your robot's intelligence.</span>
        )}
        <span>Robot simulated in MuJoCo (Unitree Go2 model) · fleet history is synthetic</span>
      </footer>
    </div>
  );
}
