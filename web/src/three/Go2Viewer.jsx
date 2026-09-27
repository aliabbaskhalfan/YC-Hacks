import { Suspense, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Environment, Grid } from "@react-three/drei";
import Go2Rig from "./Go2Rig.jsx";
import { usePoseSource } from "./usePoseSource.js";

const SIM_PORT = import.meta.env.VITE_SIM_PORT ?? "8100";

// Chase camera: keeps the camera and orbit target a fixed distance behind the Go2 along the aisle
// (three.js x = MuJoCo x), easing so the gait's sway doesn't shake the shot. y and z stay put.
function FollowCamera({ poseRef, controls, follow }) {
  const placed = useRef(false);
  useFrame(({ camera }, dt) => {
    const base = poseRef.current?.bodies?.base;
    const c = controls.current;
    if (!base || !c) return;
    const x = base.p[0];
    // Jump into place on the first frame, then ease at a rate that holds at any frame rate.
    const k = placed.current ? 1 - Math.exp(-4 * dt) : 1;
    c.target.x += (x + follow.target[0] - c.target.x) * k;
    camera.position.x += (x + follow.cam[0] - camera.position.x) * k;
    placed.current = true;
    c.update();
  });
  return null;
}

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
  follow = null,
  background = "#0a0d12",
  children,
}) {
  const controls = useRef(null);
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
        <OrbitControls ref={controls} target={target} />
        {follow && <FollowCamera poseRef={poseRef} controls={controls} follow={follow} />}
      </Canvas>
      {showSource && <div className="source-pill">{source === "live" ? "live sim" : "replay (no live sim)"}</div>}
    </div>
  );
}
