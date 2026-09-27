import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { OpsConsole } from "@/ops/OpsConsole.jsx";
import { TechPhone } from "@/tech/TechPhone.jsx";

// Laptop split screen for the demo: the tech's phone on the left, the ops console on the right.
export default function Stage() {
  return (
    <div className="h-screen w-screen overflow-hidden">
      <ResizablePanelGroup orientation="horizontal">
        <ResizablePanel defaultSize="27" minSize="18">
          <TechPhone />
        </ResizablePanel>
        <ResizableHandle />
        <ResizablePanel defaultSize="73" minSize="50">
          <OpsConsole />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
