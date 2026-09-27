import { useEffect, useRef, useState } from "react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { PROCEDURE } from "@/demo/fixtures.js";

// The 4D repair procedure (web/procedure.html, src/procedure/) plays the fix; this panel embeds it
// and draws the step list, kept in sync over postMessage. Steps come from the same procedure JSON
// the viewer plays, so the two can't drift.
const PROCEDURE_JSON = "/data/procedures/replace-thigh-cover.json";
const VIEWER_URL = "/procedure.html?embed=1&speed=1.4";

const fallbackSteps = PROCEDURE.steps.map((s) => ({ title: s.title, detail: s.detail }));

export function ProcedurePanel({ className }) {
  const frame = useRef(null);
  const [steps, setSteps] = useState(fallbackSteps);
  const [title, setTitle] = useState(PROCEDURE.title);
  const [pos, setPos] = useState({ index: 0, progress: 0, running: false });

  useEffect(() => {
    let live = true;
    fetch(PROCEDURE_JSON)
      .then((r) => r.json())
      .then((p) => {
        if (!live) return;
        setTitle(p.title);
        setSteps(p.steps.map((s) => ({ title: s.title, detail: s.text, tip: s.tips?.[0]?.text })));
      })
      .catch((err) => console.warn("procedure JSON unavailable, using the fixture steps", err));
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    const onMessage = (e) => {
      if (e.origin !== location.origin || e.data?.source !== "fleetbrain-procedure") return;
      const { index, t, running } = e.data;
      // Rounded so a 60 fps stream of messages only re-renders when something visible changes.
      setPos((p) => {
        const next = { index, progress: Math.round(t * 50) / 50, running };
        return p.index === next.index && p.progress === next.progress && p.running === next.running ? p : next;
      });
    };
    addEventListener("message", onMessage);
    return () => removeEventListener("message", onMessage);
  }, []);

  const goTo = (index) =>
    frame.current?.contentWindow?.postMessage({ source: "fleetbrain-stage", type: "goToStep", index }, location.origin);

  return (
    <Card className={cn("relative gap-0 overflow-hidden bg-white p-0", className)}>
      {/* Not focusable: presenter keys (1-6, arrows) must keep reaching the stage. */}
      <iframe
        ref={frame}
        src={VIEWER_URL}
        title="4D repair procedure"
        tabIndex={-1}
        className="pointer-events-none absolute inset-0 size-full border-0"
      />
      <CardHeader className="pointer-events-none relative p-4">
        <CardTitle className="flex items-center justify-between gap-2 font-mono text-sm">
          <Badge variant="outline" className="h-7 bg-background/85 px-2.5 font-mono text-sm backdrop-blur">
            {title} · front-right
          </Badge>
          <Badge variant="outline" className="h-7 bg-background/85 px-2.5 font-mono backdrop-blur">
            v1.0 · {PROCEDURE.source}
          </Badge>
        </CardTitle>
      </CardHeader>
      <div className="relative mt-auto p-4">
        <ol className="space-y-1 rounded-lg border bg-background/85 p-2.5 backdrop-blur">
          {steps.map((s, i) => {
            const active = i === pos.index && pos.running;
            const done = pos.running && i < pos.index;
            return (
              <li key={s.title}>
                <button
                  type="button"
                  onClick={() => goTo(i)}
                  className={cn(
                    "relative flex w-full gap-3 overflow-hidden rounded-md px-2 py-1.5 text-left font-mono text-sm transition-colors",
                    active ? "bg-primary/15 text-foreground" : done ? "text-foreground/70" : "text-muted-foreground",
                    "hover:bg-accent/60",
                  )}
                >
                  {active && (
                    <span
                      className="absolute inset-y-0 left-0 bg-primary/10 transition-[width] duration-150"
                      style={{ width: `${pos.progress * 100}%` }}
                    />
                  )}
                  <span className={cn("relative w-5 shrink-0 text-right", (active || done) && "text-primary")}>
                    {done ? "✓" : i + 1}
                  </span>
                  <span className="relative">
                    {s.title}
                    {active && <span className="block text-xs text-muted-foreground">{s.detail}</span>}
                    {active && s.tip && <span className="mt-0.5 block text-xs text-warning">{s.tip}</span>}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>
    </Card>
  );
}
