import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment, Grid } from "@react-three/drei";
import Go2Rig from "./Go2Rig.jsx";
import { usePoseSource } from "./usePoseSource.js";

const SIM_PORT = import.meta.env.VITE_SIM_PORT ?? "8100";

// Scene props that ride along in a replay (in MuJoCo world coordinates, like the body poses).
function ReplayProps({ props }) {
  return (
    <group rotation={[-Math.PI / 2, 0, 0]}>
      {props.map((prop, i) =>
        prop.type === "toolbox" ? (
          <mesh key={i} position={prop.p} castShadow receiveShadow>
            <boxGeometry args={prop.size.map((h) => h * 2)} />
            <meshStandardMaterial color="#c81c12" metalness={0.3} roughness={0.45} />
          </mesh>
        ) : null
      )}
    </group>
  );
}

export default function Go2Viewer({
  status,
  alertBody,
  alertText,
  selectedBody,
  onSelectBody,
  onAlert,
  replayUrl = "/replays/idle_stand_crouch.json",
  live = true,
  playKey = 0,
  onReplayEvent,
  environment = true,
  showSource = true,
  camera = { position: [1.1, 0.7, 1.1], fov: 45 },
  target = [0, 0.15, 0],
  labels = true,
  grid = true,
  background = "#0a0d12",
  children,
}) {
  const { poseRef, source, props } = usePoseSource({
    wsUrl: live ? `ws://${location.hostname}:${SIM_PORT}/sim/stream` : null,
    replayUrl,
    onAlert,
    onReplayEvent,
    playKey,
  });

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Canvas camera={camera} shadows>
        <color attach="background" args={[background]} />
        <ambientLight intensity={environment ? 0.5 : 0.9} />
        <directionalLight position={[2, 3, 2]} intensity={1.2} castShadow />
        {!environment && <hemisphereLight args={["#cfe0ff", "#1b2432", 0.8]} />}
        <Suspense fallback={null}>
          {environment && <Environment preset="city" />}
          <Go2Rig
            poseRef={poseRef}
            status={status}
            alertBody={alertBody}
            alertText={alertText}
            selectedBody={selectedBody}
            onSelectBody={onSelectBody ?? (() => {})}
            labels={labels}
          />
          <ReplayProps props={props} />
          {children}
        </Suspense>
        {grid && <Grid args={[10, 10]} cellColor="#1b2432" sectionColor="#2a3648" fadeDistance={8} infiniteGrid />}
        <OrbitControls target={target} />
      </Canvas>
      {showSource && <div className="source-pill">{source === "live" ? "live sim" : "replay (no live sim)"}</div>}
    </div>
  );
}
