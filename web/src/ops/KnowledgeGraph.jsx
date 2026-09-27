import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { SponsorBadge } from "@/components/sponsor-badge.jsx";
import { GRAPH_COLUMNS, GRAPH_EDGES, GRAPH_NODES, NEW_PATH } from "@/demo/fixtures.js";

const COL_X = [10, 225, 440, 675];
const NODE_W = [190, 190, 210, 120];
const NODE_H = 30;
const ROW_H = 46;
const TOP = 34;

const newNodes = new Set(NEW_PATH);
const newEdges = NEW_PATH.slice(1).map((to, i) => [NEW_PATH[i], to]);
const isNewEdge = (a, b) => newEdges.some(([x, y]) => x === a && y === b);

function layout() {
  const rows = [0, 0, 0, 0];
  const pos = {};
  for (const n of GRAPH_NODES) {
    pos[n.id] = { ...n, x: COL_X[n.col], y: TOP + rows[n.col]++ * ROW_H, w: NODE_W[n.col] };
  }
  return { pos, height: TOP + Math.max(...rows) * ROW_H };
}
const { pos, height } = layout();

function edgePath(a, b) {
  const x1 = a.x + a.w, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2;
  const mx = (x1 + x2) / 2;
  return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
}

export function KnowledgeGraph({ className }) {
  const edges = [...GRAPH_EDGES.map(([a, b, n]) => ({ a, b, n, fresh: false })), ...newEdges.map(([a, b]) => ({ a, b, n: 1, fresh: true }))];
  return (
    <Card className={cn("min-h-0 gap-3", className)}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2 font-mono text-sm">
          <span>Procedural knowledge graph</span>
          <SponsorBadge sponsor="memorable" working>fix path added</SponsorBadge>
        </CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1">
        <svg viewBox={`0 0 ${COL_X[3] + NODE_W[3] + 10} ${height}`} className="h-full w-full" preserveAspectRatio="xMidYMid meet">
          {GRAPH_COLUMNS.map((c, i) => (
            <text key={c} x={COL_X[i]} y={16} className="fill-muted-foreground font-mono text-[12px] uppercase tracking-wider">
              {c}
            </text>
          ))}
          {edges.map(({ a, b, n, fresh }, i) => {
            const failure = b === "failure";
            const order = fresh ? newEdges.findIndex(([x, y]) => x === a && y === b) : 0;
            return (
              <path
                key={`${a}-${b}`}
                d={edgePath(pos[a], pos[b])}
                pathLength={1}
                fill="none"
                strokeLinecap="round"
                strokeWidth={fresh ? 3.5 : 1 + Math.sqrt(n) * 0.8}
                strokeDasharray={failure ? "0.02 0.02" : fresh ? "1" : undefined}
                strokeDashoffset={fresh ? 1 : undefined}
                className={cn(fresh ? "stroke-memorable animate-[kg-draw_0.7s_ease-out_forwards]" : failure ? "stroke-destructive/50" : "stroke-primary/35")}
                style={fresh ? { animationDelay: `${0.5 + order * 0.7}s` } : undefined}
              />
            );
          })}
          {Object.values(pos).map((node) => {
            const fresh = newNodes.has(node.id) && !GRAPH_EDGES.some(([a, b]) => a === node.id || b === node.id);
            const onPath = newNodes.has(node.id);
            const idx = NEW_PATH.indexOf(node.id);
            return (
              <g
                key={node.id}
                className={cn(fresh && "animate-in fade-in zoom-in-90 fill-mode-both duration-500")}
                style={fresh ? { animationDelay: `${0.2 + idx * 0.7}s` } : undefined}
              >
                <rect
                  x={node.x}
                  y={node.y}
                  width={node.w}
                  height={NODE_H}
                  rx={7}
                  className={cn(onPath ? "fill-memorable/15 stroke-memorable" : "fill-card stroke-border")}
                  strokeWidth={onPath ? 1.5 : 1}
                />
                <text
                  x={node.x + 10}
                  y={node.y + NODE_H / 2 + 4.5}
                  className={cn("font-mono text-[12.5px]", onPath ? "fill-foreground" : "fill-muted-foreground")}
                >
                  {node.label}
                </text>
              </g>
            );
          })}
        </svg>
      </CardContent>
    </Card>
  );
}
