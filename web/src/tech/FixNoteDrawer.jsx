import { useState } from "react";
import { CheckIcon, KeyboardIcon, MicIcon, SquareIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent, DrawerDescription, DrawerFooter, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useRecorder } from "./useRecorder.js";

const RING = 2 * Math.PI * 54;

function RecordButton({ rec }) {
  const recording = rec.state === "recording";
  const left = Math.ceil((rec.maxMs - rec.elapsed) / 1000);
  return (
    <div className="flex flex-col items-center gap-3">
      <button
        type="button"
        onClick={recording ? rec.stop : rec.start}
        disabled={rec.state === "requesting"}
        className="relative grid size-32 place-items-center rounded-full"
        aria-label={recording ? "Stop recording" : "Record fix note"}
      >
        <svg viewBox="0 0 120 120" className="absolute inset-0 -rotate-90">
          <circle cx="60" cy="60" r="54" className="fill-none stroke-border" strokeWidth="6" />
          <circle
            cx="60"
            cy="60"
            r="54"
            className="fill-none stroke-destructive transition-[stroke-dashoffset] duration-100"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={RING}
            strokeDashoffset={RING * (1 - rec.elapsed / rec.maxMs)}
          />
        </svg>
        <span className={cn("grid size-24 place-items-center rounded-full transition-colors", recording ? "bg-destructive" : "bg-destructive/85 hover:bg-destructive")}>
          {recording ? <SquareIcon className="size-9 fill-white text-white" /> : <MicIcon className="size-10 text-white" />}
        </span>
      </button>
      <div className="flex h-10 items-end gap-[3px]">
        {rec.levels.map((l, i) => (
          <span key={i} className="w-1.5 rounded-full bg-destructive/80" style={{ height: `${8 + l * 32}px` }} />
        ))}
      </div>
      <p className="font-mono text-sm text-muted-foreground">
        {recording ? `Recording · ${left}s left` : rec.state === "requesting" ? "Allow the microphone…" : "Tap to record · stops at 15 s"}
      </p>
    </div>
  );
}

export function FixNoteDrawer({ open, onOpenChange, container, workOrder, onSubmit }) {
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const rec = useRecorder({
    maxMs: 15000,
    onStop: (audio) => {
      onOpenChange(false);
      onSubmit({ audio });
    },
  });
  const showText = typing;

  return (
    <Drawer open={open} onOpenChange={onOpenChange} container={container}>
      <DrawerContent className="data-[vaul-drawer-direction=bottom]:max-h-[85%]">
        <DrawerHeader>
          <DrawerTitle className="font-mono">Close {workOrder.work_order_id}</DrawerTitle>
          <DrawerDescription>A voice note is required. How did you fix it?</DrawerDescription>
        </DrawerHeader>
        <div className="flex flex-col gap-4 px-4">
          {showText ? (
            <>
              <Textarea
                autoFocus
                rows={5}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Swapped the right thigh cover. Seat the lip first, cross pattern, one newton-meter."
                className="font-mono"
              />
            </>
          ) : (
            <RecordButton rec={rec} />
          )}
        </div>
        <DrawerFooter>
          {showText ? (
            <Button
              size="lg"
              disabled={!text.trim()}
              onClick={() => {
                onOpenChange(false);
                onSubmit({ text });
              }}
            >
              Close work order
            </Button>
          ) : rec.state === "recording" ? (
            <Button size="lg" onClick={rec.stop}>
              <CheckIcon /> Finish
            </Button>
          ) : (
            <Button variant="ghost" onClick={() => setTyping(true)}>
              <KeyboardIcon /> Type instead
            </Button>
          )}
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
