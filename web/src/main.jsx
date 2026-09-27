import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import Stage from "./Stage.jsx";
import { OpsConsole } from "@/ops/OpsConsole.jsx";
import { TechPhone } from "@/tech/TechPhone.jsx";
import { DemoProvider } from "@/demo/DemoContext.jsx";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./index.css";

// "/" is the stage split screen; "/ops" and "/tech" show one side; "/viewer" is the 3D debug harness.
const ROUTES = {
  "/": Stage,
  "/ops": () => <div className="h-screen"><OpsConsole /></div>,
  "/tech": () => <div className="h-screen"><TechPhone /></div>,
  "/viewer": lazy(() => import("./App.jsx")),
};
const Page = ROUTES[location.pathname.replace(/\/+$/, "") || "/"] ?? Stage;

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <TooltipProvider>
      <DemoProvider>
        <Suspense fallback={null}>
          <Page />
        </Suspense>
        <Toaster theme="dark" position="top-right" />
      </DemoProvider>
    </TooltipProvider>
  </React.StrictMode>
);
