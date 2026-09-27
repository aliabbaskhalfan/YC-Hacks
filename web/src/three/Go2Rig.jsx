import { useEffect, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { useGLTF, Html } from "@react-three/drei";
import * as THREE from "three";

// One entry per node exported by sim/export_go2_gltf.py (BUILD_SPEC.md
// Section 4.1) — the contract the whole 3D pipeline is built on.
const BODY_NAMES = [
  "base",
  "FL_hip", "FL_thigh", "FL_calf",
  "FR_hip", "FR_thigh", "FR_calf",
  "RL_hip", "RL_thigh", "RL_calf",
  "RR_hip", "RR_thigh", "RR_calf",
];

const RED = new THREE.Color("#ff3b3b");
const FAINT_RED = new THREE.Color("#5a1414");
const GREEN = new THREE.Color("#2bd97a");
const SELECT = new THREE.Color("#4aa8ff");
const BLACK = new THREE.Color("#000000");
const FIXED_FLASH_SECONDS = 2;

/**
 * Renders the Go2 and drives it from `poseRef` every frame (Section 6.2).
 * `status`/`alertBody` implement the shared healthy/red/in_repair/fixed
 * state machine (Section 5.3); `selectedBody` is independent tap-to-inspect
 * state a tech can change even mid-alert ("the tech can tap a different part
 * if the real cause was elsewhere", Section 7.2).
 */
export default function Go2Rig({
  poseRef,
  status,
  alertBody,
  alertText,
  selectedBody,
  onSelectBody,
}) {
  const { nodes } = useGLTF("/go2.glb");
  const flashStart = useRef(null);
  const baseColors = useRef({});

  // Clone materials so tinting one body can never bleed into a sibling that
  // happens to share the loader's default vertex-colored material, and keep
  // each one's original baked color — the model is mostly white/silver, and
  // emissive-only tinting is additive, so on a bright surface it washes out
  // to nearly nothing. Blending the base color itself is what makes "faint
  // red tint" (Section 5.3) and the solid-red alert body actually read.
  useEffect(() => {
    for (const name of BODY_NAMES) {
      const mesh = nodes[name];
      if (!mesh?.material) continue;
      mesh.material = mesh.material.clone();
      baseColors.current[name] = mesh.material.color.clone();
    }
  }, [nodes]);

  useEffect(() => {
    if (status === "fixed") flashStart.current = performance.now();
  }, [status]);

  useFrame(() => {
    const bodies = poseRef.current?.bodies;
    if (bodies) {
      for (const name of BODY_NAMES) {
        const mesh = nodes[name];
        const b = bodies[name];
        if (!mesh || !b) continue;
        mesh.position.set(b.p[0], b.p[1], b.p[2]);
        // MuJoCo quats are (w, x, y, z); three.js Quaternion is (x, y, z, w).
        mesh.quaternion.set(b.q[1], b.q[2], b.q[3], b.q[0]);
      }
    }

    const pulse = 0.55 + 0.45 * Math.sin(performance.now() / 180);
    const fixedElapsed = flashStart.current === null
      ? Infinity
      : (performance.now() - flashStart.current) / 1000;
    const fixedActive = status === "fixed" && fixedElapsed < FIXED_FLASH_SECONDS;
    const alerting = status === "red" || status === "in_repair";

    for (const name of BODY_NAMES) {
      const mat = nodes[name]?.material;
      const base = baseColors.current[name];
      if (!mat || !base) continue;
      const isAlertBody = name === alertBody;

      if (fixedActive && isAlertBody) {
        mat.color.copy(base).lerp(GREEN, 0.85);
        mat.emissive.copy(GREEN);
        mat.emissiveIntensity = 0.8;
      } else if (alerting && isAlertBody) {
        mat.color.copy(base).lerp(RED, 0.85);
        mat.emissive.copy(RED);
        mat.emissiveIntensity = pulse;
      } else if (alerting) {
        mat.color.copy(base).lerp(FAINT_RED, 0.35);
        mat.emissive.copy(FAINT_RED);
        mat.emissiveIntensity = 0.3;
      } else if (name === selectedBody) {
        mat.color.copy(base).lerp(SELECT, 0.35);
        mat.emissive.copy(SELECT);
        mat.emissiveIntensity = 0.4;
      } else {
        mat.color.copy(base);
        mat.emissive.copy(BLACK);
        mat.emissiveIntensity = 0;
      }
    }
  });

  return (
    <group rotation={[-Math.PI / 2, 0, 0]}>
      {BODY_NAMES.map((name) => {
        const mesh = nodes[name];
        if (!mesh) return null;
        const showAlertBadge = name === alertBody && (status === "red" || status === "in_repair");
        const showSelectBadge = name === selectedBody && name !== alertBody;
        return (
          <primitive
            key={name}
            object={mesh}
            onPointerDown={(e) => {
              e.stopPropagation();
              onSelectBody(name);
            }}
          >
            {showAlertBadge && (
              <Html distanceFactor={2} occlude={false}>
                <div className="badge badge-alert">{alertText || name}</div>
              </Html>
            )}
            {showSelectBadge && (
              <Html distanceFactor={2} occlude={false}>
                <div className="badge badge-select">{name}</div>
              </Html>
            )}
          </primitive>
        );
      })}
    </group>
  );
}

useGLTF.preload("/go2.glb");
