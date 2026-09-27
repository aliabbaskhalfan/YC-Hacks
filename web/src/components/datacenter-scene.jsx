import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";

// The data center aisle from sim/build_datacenter.py, exported by `go2_fault_demo.py --export-replays`
// into the same shifted MuJoCo frame as the replays. ~6.8k geoms, drawn as a handful of instanced meshes.
const SCENE_URL = "/scenes/datacenter.json";
let scenePromise;
const loadScene = () => (scenePromise ??= fetch(SCENE_URL).then((r) => r.json()));

const UNIT_GEOMETRY = {
  box: () => new THREE.BoxGeometry(2, 2, 2),
  cylinder: () => new THREE.CylinderGeometry(1, 1, 2, 16).rotateX(Math.PI / 2), // MuJoCo cylinders run along local z
  sphere: () => new THREE.SphereGeometry(1, 16, 12),
};

// Emissive geoms (LEDs, light strips, the lit ceiling, exit sign) are unlit so they read as glowing.
function materialFor(mode) {
  if (mode === "glow") return new THREE.MeshBasicMaterial({ toneMapped: false });
  if (mode === "glowAlpha") return new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.35, depthWrite: false, toneMapped: false });
  if (mode === "glass") return new THREE.MeshStandardMaterial({ transparent: true, opacity: 0.14, roughness: 0.05, metalness: 0.2, depthWrite: false });
  return new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.25 });
}

function buildInstances(scene) {
  const groups = new Map();
  for (const [type, rows] of Object.entries(scene.geoms)) {
    for (const row of rows) {
      const a = row[13], emission = row[14];
      const mode = emission >= 0.3 ? (a < 1 ? "glowAlpha" : "glow") : a < 1 ? "glass" : "std";
      const key = `${type}|${mode}`;
      if (!groups.has(key)) groups.set(key, { type, mode, rows: [] });
      groups.get(key).rows.push(row);
    }
  }
  const m4 = new THREE.Matrix4(), p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3(), c = new THREE.Color();
  return [...groups.values()].map(({ type, mode, rows }) => {
    const mesh = new THREE.InstancedMesh(UNIT_GEOMETRY[type](), materialFor(mode), rows.length);
    rows.forEach((r, i) => {
      p.set(r[0], r[1], r[2]);
      q.set(r[7], r[8], r[9], r[6]);
      s.set(r[3], type === "box" ? r[4] : r[3], type === "box" ? r[5] : type === "cylinder" ? r[4] : r[3]);
      mesh.setMatrixAt(i, m4.compose(p, q, s));
      const k = mode.startsWith("glow") ? Math.min(1, 0.35 + r[14]) : 1;
      mesh.setColorAt(i, c.setRGB(r[10] * k, r[11] * k, r[12] * k, THREE.SRGBColorSpace));
    });
    mesh.frustumCulled = false;
    if (mode === "glass") mesh.renderOrder = 2;
    return mesh;
  });
}

function tileTexture({ rgb1, rgb2, mark }) {
  const n = 256, canvas = document.createElement("canvas");
  canvas.width = canvas.height = n * 2;
  const ctx = canvas.getContext("2d");
  const css = (rgb) => `rgb(${rgb.map((v) => Math.round(v * 255)).join(",")})`;
  for (let i = 0; i < 2; i++)
    for (let j = 0; j < 2; j++) {
      ctx.fillStyle = css((i + j) % 2 ? rgb2 : rgb1);
      ctx.fillRect(i * n, j * n, n, n);
      ctx.strokeStyle = css(mark);
      ctx.lineWidth = 3;
      ctx.strokeRect(i * n + 1.5, j * n + 1.5, n - 3, n - 3);
    }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 8;
  return tex;
}

export function DataCenterScene() {
  const [scene, setScene] = useState(null);
  useEffect(() => {
    let live = true;
    loadScene().then((s) => live && setScene(s)).catch((err) => console.warn("datacenter scene failed to load", err));
    return () => {
      live = false;
    };
  }, []);

  const meshes = useMemo(() => (scene ? buildInstances(scene) : []), [scene]);
  const floor = useMemo(() => {
    if (!scene) return null;
    const size = [40, 12], tex = tileTexture(scene.floor);
    tex.repeat.set(size[0] / (2 * scene.floor.tile_m), size[1] / (2 * scene.floor.tile_m));
    return { size, tex };
  }, [scene]);
  useEffect(
    () => () =>
      meshes.forEach((m) => {
        m.geometry.dispose();
        m.material.dispose();
      }),
    [meshes],
  );

  if (!scene) return null;
  return (
    <group rotation={[-Math.PI / 2, 0, 0]}>
      <mesh position={[4, 0, -0.001]} receiveShadow>
        <planeGeometry args={floor.size} />
        <meshStandardMaterial map={floor.tex} roughness={0.28} metalness={0.05} />
      </mesh>
      {meshes.map((m) => (
        <primitive key={m.uuid} object={m} />
      ))}
      {[-2.4, 0, 2.4, 4.8].map((x) => (
        <pointLight key={x} position={[x, 0.3, 3.0]} intensity={6} distance={9} decay={1.6} color="#eef3ff" />
      ))}
    </group>
  );
}
