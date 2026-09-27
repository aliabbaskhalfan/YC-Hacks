import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { Go2Rig } from './three/go2Rig.js';
import { buildCoverAssembly } from './three/coverAssembly.js';
import { CameraDirector } from './three/cameraDirector.js';
import { POSES, blendPose } from './three/kinematics.js';
import { ProcedurePlayer } from './ops/player.js';
import { Caption, TorqueGauge } from './ui/overlay.js';

const PROCEDURE_URL = '/data/procedures/replace-thigh-cover.json';
const PARTS_URL = '/data/registry/parts.json';
const MODEL_URL = '/go2_procedure.glb';

const stage = document.getElementById('stage');
const caption = document.getElementById('caption');
const hud = document.getElementById('hud');
const status = document.getElementById('status');

const setStatus = (msg, bad) => {
  status.textContent = msg;
  status.classList.toggle('bad', !!bad);
  status.classList.toggle('hidden', !msg);
};

// ---------------------------------------------------------------- scene setup
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.NoToneMapping;
stage.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xffffff);
scene.fog = new THREE.Fog(0xffffff, 3.0, 7.5);

const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 50);

// Metal needs something to reflect. Without an environment the metallic part of
// every material returns black, which at a distance turned the whole robot into
// a flat silhouette even though the close-ups looked fine.
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.55;

// Lit like a technical illustration on white: broad ambient so no face goes black,
// one key for form, and rim/bounce to keep edges off the background.
scene.add(new THREE.HemisphereLight(0xffffff, 0xb4c0d0, 0.85));

const key = new THREE.DirectionalLight(0xffffff, 1.5);
key.position.set(1.4, 2.0, 1.1);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.near = 0.5;
key.shadow.camera.far = 8;
key.shadow.camera.left = key.shadow.camera.bottom = -1.2;
key.shadow.camera.right = key.shadow.camera.top = 1.2;
key.shadow.bias = -0.0009;
scene.add(key);

const rim = new THREE.DirectionalLight(0xdbe6f5, 0.6);
rim.position.set(-1.6, 0.9, -1.4);
scene.add(rim);

const bounce = new THREE.DirectionalLight(0xffffff, 0.35);
bounce.position.set(0.2, -1.0, 0.8); // stops undersides going solid black
scene.add(bounce);

// Headlight: rides the camera so the face being worked on is never backlit.
const headlight = new THREE.DirectionalLight(0xffffff, 0.5);
headlight.position.set(0, 0, 1);
camera.add(headlight);
scene.add(camera);

// Inspection lamp, parked on the work area once the assembly exists.
const fill = new THREE.PointLight(0xffffff, 1.1, 1.2, 1.6);
scene.add(fill);

// Bench floor.
const floor = new THREE.Mesh(
  new THREE.CircleGeometry(3, 64),
  new THREE.MeshStandardMaterial({ color: 0xf2f5f8, roughness: 0.95, metalness: 0 }),
);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

const grid = new THREE.GridHelper(4, 40, 0xc3ccd8, 0xdfe5ec);
grid.material.transparent = true;
grid.material.opacity = 0.85;
grid.position.y = 0.001;
scene.add(grid);

// ---------------------------------------------------------------------- boot
async function boot() {
  setStatus('loading procedure…');
  const [procedure, parts] = await Promise.all([
    fetch(PROCEDURE_URL).then((r) => r.json()),
    fetch(PARTS_URL)
      .then((r) => r.json())
      .catch(() => []),
  ]);

  setStatus('loading go2.glb…');
  const robot = await new Go2Rig().load(MODEL_URL);
  scene.add(robot.root);
  robot.applyPose(POSES.service_fr);

  setStatus('building service hardware…');
  const geom = procedure.geometry;
  const rig = await buildCoverAssembly(geom);
  const host = robot.bodies[geom.host_node];
  if (!host) throw new Error(`go2.glb has no node ${geom.host_node}`);
  host.add(rig.root);
  robot.root.updateMatrixWorld(true);

  // Drop the robot onto the floor rather than trusting the MJCF base height,
  // which assumes a standing pose.
  const box = new THREE.Box3().setFromObject(robot.root);
  robot.root.position.y -= box.min.y;
  robot.root.updateMatrixWorld(true);
  const robotCentre = new THREE.Box3().setFromObject(robot.root).getCenter(new THREE.Vector3());

  const partsById = new Map(parts.map((p) => [p.part_id, p]));

  // ------------------------------------------------------------- player + ui
  const player = new ProcedurePlayer(procedure, rig);
  const director = new CameraDirector(camera);
  // Handles for debugging and for driving the viewer from a test harness.
  Object.assign(window, { __player: player, __rig: rig, __robot: robot,
    __scene: scene, __camera: camera, __three: THREE, __director: director });
  const gauge = new TorqueGauge(hud, procedure.hardware.torque_nm, procedure.hardware.torque_tolerance_nm);
  const cap = new Caption(caption, procedure);

  // The cover faces inboard, so the hip block and the body sit between the camera
  // and the work. On a white background those can be ghosted rather than hidden:
  // the whole robot stays readable and you still see through to the cover.
  const FOCUS = ['FR_thigh', 'FR_calf'];

  // The opening runs in three beats, and the timeline is frozen on step 1 frame 0
  // for the first two so nothing moves before you can see what you are looking at:
  //   settle    wide shot, the leg swings out to the service pose
  //   approach  camera flies down onto the cover, hardware still untouched
  //   run       the procedure plays
  const LEAD_IN = { settle: 2.6, approach: 2.4 };
  let phase = 'settle';
  let phaseT = 0;

  player.onChange((state) => {
    cap.render(state);
    const shot = phase === 'settle' ? 'hero' : state.camera;
    director.setShot(shot, rig.root, robotCentre);
    robot.setFocus(shot === 'hero' ? null : FOCUS);

    const r = state.result ?? {};
    const torquing = r.torques != null;
    gauge.setVisible(torquing);
    if (torquing) gauge.draw(r.liveNm ?? 0);

  });

  addEventListener('keydown', (e) => {
    if (!['Space', 'ArrowRight', 'ArrowLeft'].includes(e.code)) return;
    phase = 'run'; // any manual input skips the opening lead-in
    if (e.code === 'Space') {
      e.preventDefault();
      player.toggle();
    }
    if (e.code === 'ArrowRight') player.next();
    if (e.code === 'ArrowLeft') player.prev();
  });

  // ---------------------------------------------------------------- picking
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const chip = document.getElementById('picked');

  renderer.domElement.addEventListener('pointerdown', (e) => {
    const rect = renderer.domElement.getBoundingClientRect();
    ndc.set(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    ray.setFromCamera(ndc, camera);

    // Service hardware first: it sits on top of the body meshes.
    const hwHits = ray.intersectObjects([rig.root], true);
    if (hwHits.length) {
      let o = hwHits[0].object;
      while (o && !o.name?.startsWith('screw-') && o.name !== 'cover-new' && o.name !== 'cover-old') {
        o = o.parent;
        if (o === rig.root) break;
      }
      if (o?.name?.startsWith('screw-')) return showPick('fr.thigh.cover_screws', o.name);
      if (o?.name === 'cover-new' || o?.name === 'cover-old') return showPick('fr.thigh.cover');
      return showPick('fr.thigh.motor', 'housing');
    }

    const hits = ray.intersectObjects(robot.pickables, false);
    if (!hits.length) return showPick(null);
    const body = hits[0].object.userData.bodyName;
    const match = parts.find((p) => p.mesh_nodes?.includes(body));
    showPick(match?.part_id ?? body, body);
  });

  function showPick(partId, detail) {
    if (!partId) {
      chip.classList.add('hidden');
      return;
    }
    const p = partsById.get(partId);
    chip.classList.remove('hidden');
    chip.innerHTML = `<b>${partId}</b>${p ? `<span>${p.name}</span>` : ''}${
      detail ? `<i>${detail}</i>` : ''
    }`;
  }

  // ------------------------------------------------------------------- loop
  const size = { w: 0, h: 0 };
  function resize() {
    const rect = stage.getBoundingClientRect();
    size.w = rect.width;
    size.h = rect.height;
    renderer.setSize(size.w, size.h, false);
    camera.aspect = size.w / size.h;
    camera.updateProjectionMatrix();
  }
  addEventListener('resize', resize);
  resize();

  const clockSrc = new THREE.Clock();
  setStatus('');
  player.play();

  renderer.setAnimationLoop(() => {
    const dt = Math.min(0.05, clockSrc.getDelta());

    if (phase === 'settle') {
      phaseT = Math.min(LEAD_IN.settle, phaseT + dt);
      const k = phaseT / LEAD_IN.settle;
      robot.applyPose(blendPose(POSES.stand, POSES.service_fr, k * k * (3 - 2 * k)));
      if (phaseT >= LEAD_IN.settle) {
        phase = 'approach';
        phaseT = 0;
      }
    } else if (phase === 'approach') {
      phaseT += dt;
      if (phaseT >= LEAD_IN.approach) phase = 'run';
    }

    // Frozen on step 1 frame 0 until the camera has arrived, so the first screw
    // does not start turning before you can see what it is attached to.
    if (phase === 'run') player.tick(dt);
    else player.apply();
    director.update(dt, Math.sin(performance.now() / 9000) * 0.05);

    // Work light follows the cover.
    scene.updateMatrixWorld();
    fill.position.setFromMatrixPosition(rig.root.matrixWorld);
    fill.position.y += 0.12;

    renderer.render(scene, camera);
  });
}

boot().catch((err) => {
  console.error(err);
  setStatus(`failed: ${err.message}`, true);
});
