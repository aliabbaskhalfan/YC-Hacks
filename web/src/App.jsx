import { useCallback, useRef, useState } from "react";
import Go2Viewer from "./three/Go2Viewer.jsx";
import DebugControls from "./three/DebugControls.jsx";
import { partIdToBodyNode } from "./three/partId.js";
import "./app.css";

const FIXED_HOLD_MS = 2200; // Section 5.3: green flash for ~2s, then back to healthy

// Standalone harness for the 3d-viewer track: exercises the Section 5.3
// status state machine (healthy -> red -> in_repair -> fixed -> healthy)
// against fake input, the same shape a live anomaly / fix-note event will
// eventually drive it with.
export default function App() {
  const [status, setStatus] = useState("healthy");
  const [partId, setPartId] = useState(null);
  const [alertBody, setAlertBody] = useState(null);
  const [alertText, setAlertText] = useState(null);
  const [selectedBody, setSelectedBody] = useState(null);
  const fixedTimer = useRef(null);

  const reset = () => {
    clearTimeout(fixedTimer.current);
    setStatus("healthy");
    setPartId(null);
    setAlertBody(null);
    setAlertText(null);
  };

  const handleInject = (id) => {
    clearTimeout(fixedTimer.current);
    setPartId(id);
    setAlertBody(partIdToBodyNode(id));
    setAlertText(`${id}: reported fault (debug-injected)`);
    setStatus("red");
  };

  const handleOpenForRepair = () => setStatus("in_repair");

  const handleMarkFixed = () => {
    setStatus("fixed");
    fixedTimer.current = setTimeout(reset, FIXED_HOLD_MS);
  };

  // A live anomaly frame reaching the viewer directly over WS (Section 5.2)
  // drives the same state, bypassing the debug panel entirely.
  const handleLiveAlert = useCallback((alert) => {
    if (!alert) return;
    clearTimeout(fixedTimer.current);
    setPartId(alert.part_id ?? null);
    setAlertBody(partIdToBodyNode(alert.part_id));
    setAlertText(alert.what_went_wrong || alert.part_id || "anomaly detected");
    setStatus("red");
  }, []);

  return (
    <div style={{ width: "100vw", height: "100vh" }}>
      <Go2Viewer
        status={status}
        alertBody={alertBody}
        alertText={alertText}
        selectedBody={selectedBody}
        onSelectBody={setSelectedBody}
        onAlert={handleLiveAlert}
      />
      <DebugControls
        status={status}
        partId={partId}
        onInject={handleInject}
        onOpenForRepair={handleOpenForRepair}
        onMarkFixed={handleMarkFixed}
        onClear={reset}
      />
    </div>
  );
}
