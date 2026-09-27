import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment, Grid } from "@react-three/drei";
import Go2Rig from "./Go2Rig.jsx";
import { usePoseSource } from "./usePoseSource.js";

const SIM_PORT = import.meta.env.VITE_SIM_PORT ?? "8100";

export default function Go2Viewer({ status, alertBody, alertText, selectedBody, onSelectBody, onAlert }) {
  const { poseRef, source } = usePoseSource({
    wsUrl: `ws://${location.hostname}:${SIM_PORT}/sim/stream`,
    replayUrl: "/replays/idle_stand_crouch.json",
    onAlert,
  });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Canvas camera={{ position: [1.1, 0.7, 1.1], fov: 45 }} shadows>
        <color attach="background" args={["#0a0d12"]} />
        <ambientLight intensity={0.5} />
        <directionalLight position={[2, 3, 2]} intensity={1.2} castShadow />
        <Suspense fallback={null}>
          <Environment preset="city" />
          <Go2Rig
            poseRef={poseRef}
            status={status}
            alertBody={alertBody}
            alertText={alertText}
            selectedBody={selectedBody}
            onSelectBody={onSelectBody}
          />
        </Suspense>
        <Grid args={[10, 10]} cellColor="#1b2432" sectionColor="#2a3648" fadeDistance={8} infiniteGrid />
        <OrbitControls target={[0, 0.15, 0]} />
      </Canvas>
      <div className="source-pill">{source === "live" ? "live sim" : "replay (no live sim)"}</div>
    </div>
  );
}
