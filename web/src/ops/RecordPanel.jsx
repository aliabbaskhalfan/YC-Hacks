import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { SponsorBadge } from "@/components/sponsor-badge.jsx";
import { useDemo } from "@/demo/DemoContext.jsx";

const TOKEN = /("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+(?:\.\d+)?)|\b(true|false|null)\b/g;

function JsonLine({ line }) {
  const out = [];
  let last = 0;
  for (const m of line.matchAll(TOKEN)) {
    if (m.index > last) out.push(line.slice(last, m.index));
    const [text, str, colon, num, lit] = m;
    const cls = str ? (colon ? "text-primary" : "text-foreground") : num ? "text-success" : lit ? "text-warning" : "";
    out.push(
      <span key={m.index} className={cls}>
        {str ?? text}
      </span>,
    );
    if (colon) out.push(colon);
    last = m.index + text.length;
  }
  out.push(line.slice(last));
  return <div>{out}</div>;
}

export function RecordPanel({ className }) {
  const { record } = useDemo();
  if (!record) return null;
  const lines = JSON.stringify(record, null, 2).split("\n");
  return (
    <Card className={cn("min-h-0 gap-3 animate-in fade-in slide-in-from-right-3 duration-500", className)}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2 font-mono text-sm">
          <HoverCard openDelay={100}>
            <HoverCardTrigger className="cursor-help underline decoration-dotted underline-offset-4">
              Fix record · {record.incident_id}
            </HoverCardTrigger>
            <HoverCardContent className="w-80 font-mono text-xs">
              <p className="mb-2 text-sm font-medium text-foreground">Provenance</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-muted-foreground">
                <dt>source</dt><dd className="text-foreground">{record.provenance.source}</dd>
                <dt>tech</dt><dd className="text-foreground">{record.fix.tech}</dd>
                <dt>work order</dt><dd className="text-foreground">{record.provenance.work_order}</dd>
                <dt>robot</dt><dd className="text-foreground">{record.unit_id} · {record.site}</dd>
                <dt>audio</dt><dd className="text-foreground">{record.fix.voice_note_audio}</dd>
                <dt>synthetic</dt><dd className="text-foreground">{String(record.provenance.synthetic)}</dd>
              </dl>
              <p className="mt-2">Torque and impact force are sim values.</p>
            </HoverCardContent>
          </HoverCard>
          <SponsorBadge sponsor="gbrain">stored as a memory</SponsorBadge>
        </CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1">
        <ScrollArea className="h-full rounded-md border bg-background/60">
          <pre className="p-3 font-mono text-[12.5px] leading-5 text-muted-foreground">
            {lines.map((line, i) => (
              <JsonLine key={i} line={line} />
            ))}
          </pre>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
