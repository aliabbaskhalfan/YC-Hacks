import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

// The cover itself is the real disc lifted out of data/cad/UnitreeGo2.stl by
// sim/extract_cover_from_stl.py, already expressed in the FR_thigh frame with its
// inner face at y=0. Everything the STL does not model as separate solids — the
// housing face, the groove the lip seats into, the threaded bosses, the M3 screws
// and the driver — is synthesized here and stacked on the actuator boss.
//
// Local layout inside the assembly (all +Y, the cover axis):
//   0                      boss face (assembly origin)
//   0 .. housing_thickness  housing face disc, with the groove on top
//   MOUNT_Y                 cover inner face
//   MOUNT_Y + T             cover outer face, where the screw heads land

export const COLORS = {
  cover: 0x8c96a6,
  coverCracked: 0x9c8288,
  coverNew: 0x8c96a6,
  housing: 0x515b69,
  groove: 0x272d36,
  boss: 0x7a8593,
  screw: 0x5e6773,
  screwSeated: 0x4ade80,
  screwLoose: 0xf5a524,
  driver: 0x2563d6,
  accent: 0x6aa6ff,
  alert: 0xff5555,
};

const deg = (d) => (d * Math.PI) / 180;

function crackTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const g = c.getContext('2d');
  g.clearRect(0, 0, 512, 512);
  g.strokeStyle = '#000';
  g.lineCap = 'round';

  // A crack running from a screw hole out to the rim, the way it actually fails.
  let seed = 7;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);

  const walk = (x, y, angle, len, width) => {
    g.lineWidth = width;
    g.beginPath();
    g.moveTo(x, y);
    let a = angle;
    for (let i = 0; i < 14; i++) {
      a += (rnd() - 0.5) * 0.55;
      x += Math.cos(a) * (len / 14);
      y += Math.sin(a) * (len / 14);
      g.lineTo(x, y);
    }
    g.stroke();
    return [x, y, a];
  };

  const [bx, by, ba] = walk(256 + 86, 256 - 86, deg(-50), 140, 8);
  walk(bx, by, ba + 0.7, 64, 4);
  walk(bx, by, ba - 0.8, 52, 3.5);
  walk(256 + 86, 256 - 86, deg(148), 78, 4.5);

  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 8;
  return tex;
}

function screwMesh() {
  const g = new THREE.Group();
  const headMat = new THREE.MeshStandardMaterial({
    color: COLORS.screw,
    roughness: 0.32,
    metalness: 0.85,
  });

  // M3 socket cap: 5.5 mm head, 3 mm shank, 8 mm long.
  const head = new THREE.Mesh(new THREE.CylinderGeometry(0.00275, 0.00275, 0.003, 24), headMat);
  head.position.y = 0.0015;
  g.add(head);

  const shank = new THREE.Mesh(
    new THREE.CylinderGeometry(0.0015, 0.0015, 0.008, 16),
    new THREE.MeshStandardMaterial({ color: 0x8d97a4, roughness: 0.45, metalness: 0.85 }),
  );
  shank.position.y = -0.004;
  g.add(shank);

  // 2.5 mm hex socket, so the driver visibly engages something.
  const socket = new THREE.Mesh(
    new THREE.CylinderGeometry(0.00125, 0.00125, 0.0016, 6),
    new THREE.MeshStandardMaterial({ color: 0x0b0d11, roughness: 1 }),
  );
  socket.position.y = 0.0027;
  g.add(socket);

  g.userData.headMat = headMat;
  return g;
}

function hexDriver() {
  const g = new THREE.Group();

  const bit = new THREE.Mesh(
    new THREE.CylinderGeometry(0.00125, 0.00125, 0.022, 6),
    new THREE.MeshStandardMaterial({ color: 0x8e98a6, roughness: 0.3, metalness: 0.9 }),
  );
  bit.position.y = 0.011;
  g.add(bit);

  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(0.0022, 0.0022, 0.032, 20),
    new THREE.MeshStandardMaterial({ color: 0x707a88, roughness: 0.35, metalness: 0.8 }),
  );
  shaft.position.y = 0.032;
  g.add(shaft);

  const collar = new THREE.Mesh(
    new THREE.CylinderGeometry(0.0062, 0.0062, 0.005, 24),
    new THREE.MeshStandardMaterial({ color: 0x242a33, roughness: 0.8 }),
  );
  collar.position.y = 0.05;
  g.add(collar);

  // Torque handle, tinted with the UI accent so it reads as the tool.
  const handle = new THREE.Mesh(
    new THREE.CylinderGeometry(0.0058, 0.005, 0.036, 24),
    new THREE.MeshStandardMaterial({ color: COLORS.driver, roughness: 0.6, metalness: 0.15 }),
  );
  handle.position.y = 0.071;
  g.add(handle);

  return g;
}

/** Wrap a cover mesh with the lip, hole rings and (optionally) a crack decal. */
function dressCover(geometry, { color, cracked, dims }) {
  const { R, T, LR, LD, BCR, angles } = dims;
  const g = new THREE.Group();

  const shell = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      color,
      roughness: 0.6,
      metalness: 0.3,
      transparent: true,
      opacity: 1,
    }),
  );
  g.add(shell);
  g.userData.shell = shell;

  // The disc in the STL is an annulus, open to about r=32 mm, so on its own you
  // see straight through to the motor and "lift the cover off" reveals nothing.
  // Cap the centre with the shell's own material so it reads as one part.
  const centre = new THREE.Mesh(
    new THREE.CylinderGeometry(LR + 0.0008, LR + 0.0008, T, 64),
    shell.material,
  );
  centre.position.y = T / 2;
  g.add(centre);

  // The inner lip that must land in the groove before any screw goes in.
  const lip = new THREE.Mesh(
    new THREE.CylinderGeometry(LR, LR, LD, 48, 1, true),
    new THREE.MeshStandardMaterial({
      color: 0x656f7d,
      roughness: 0.7,
      metalness: 0.3,
      side: THREE.DoubleSide,
    }),
  );
  lip.position.y = -LD / 2;
  g.add(lip);
  g.userData.lip = lip;

  if (cracked) {
    const decal = new THREE.Mesh(
      new THREE.CircleGeometry(R * 0.985, 64),
      new THREE.MeshBasicMaterial({
        map: crackTexture(),
        transparent: true,
        opacity: 0.95,
        depthWrite: false,
        color: 0x000000,
      }),
    );
    decal.rotation.x = -Math.PI / 2;
    decal.position.y = T + 0.0005;
    g.add(decal);
    g.userData.decal = decal;
  }
  return g;
}

/**
 * Build the cover assembly in the host body's frame.
 * The cover axis is +Y in that frame, so everything is modelled around +Y and the
 * group is left unrotated — screws drive along -Y into the housing.
 */
export async function buildCoverAssembly(geom) {
  const {
    cover_center: center,
    cover_radius: R,
    cover_thickness: T,
    housing_thickness: HT,
    lip_radius: LR,
    lip_depth: LD,
    bolt_circle_radius: BCR,
    screw_angles_deg: angles,
    cover_mesh: coverUrl,
  } = geom;

  const MOUNT_Y = HT; // cover inner face sits on the housing face
  const dims = { R, T, LR, LD, BCR, HT, MOUNT_Y, angles };

  const root = new THREE.Group();
  root.name = 'cover-assembly';
  root.position.set(...center);

  // ---- Housing face: what you find under the cover -------------------------
  const housing = new THREE.Group();
  housing.name = 'housing';
  root.add(housing);

  const face = new THREE.Mesh(
    new THREE.CylinderGeometry(R * 0.99, R * 0.99, HT, 64),
    new THREE.MeshStandardMaterial({ color: COLORS.housing, roughness: 0.7, metalness: 0.6 }),
  );
  face.position.y = HT / 2;
  housing.add(face);

  // Rotor detail so the exposed housing looks like a motor, not a blank disc.
  const rotor = new THREE.Mesh(
    new THREE.CylinderGeometry(LR * 0.72, LR * 0.72, HT * 0.8, 48),
    new THREE.MeshStandardMaterial({ color: 0x646e7c, roughness: 0.5, metalness: 0.7 }),
  );
  rotor.position.y = HT * 0.5;
  housing.add(rotor);

  const hub = new THREE.Mesh(
    new THREE.CylinderGeometry(0.008, 0.008, HT * 0.9, 24),
    new THREE.MeshStandardMaterial({ color: 0x8a94a2, roughness: 0.35, metalness: 0.9 }),
  );
  hub.position.y = HT * 0.55;
  housing.add(hub);

  // The groove the cover lip has to drop into: the whole point of step 3.
  const groove = new THREE.Mesh(
    new THREE.TorusGeometry(LR, 0.0022, 12, 72),
    new THREE.MeshStandardMaterial({ color: COLORS.groove, roughness: 0.95 }),
  );
  groove.rotation.x = Math.PI / 2;
  groove.position.y = HT;
  housing.add(groove);
  housing.userData.groove = groove;

  // Threaded bosses the screws land in.
  const bosses = angles.map((a) => {
    const boss = new THREE.Mesh(
      new THREE.CylinderGeometry(0.0035, 0.0042, HT * 0.9, 20),
      new THREE.MeshStandardMaterial({ color: COLORS.boss, roughness: 0.5, metalness: 0.8 }),
    );
    boss.position.set(Math.cos(deg(a)) * BCR, HT * 0.55, Math.sin(deg(a)) * BCR);
    housing.add(boss);
    return boss;
  });
  housing.userData.bosses = bosses;

  // ---- Covers: the cracked one comes off, the new one goes on --------------
  let coverGeom = null;
  try {
    const gltf = await new GLTFLoader().loadAsync(coverUrl);
    gltf.scene.traverse((o) => {
      if (o.isMesh && !coverGeom) coverGeom = o.geometry;
    });
  } catch (err) {
    console.warn(`cover mesh ${coverUrl} unavailable, falling back to a disc`, err);
  }
  if (!coverGeom) {
    coverGeom = new THREE.CylinderGeometry(R, R, T, 64);
    coverGeom.translate(0, T / 2, 0);
  }

  const oldCover = dressCover(coverGeom, { color: COLORS.coverCracked, cracked: true, dims });
  oldCover.name = 'cover-old';
  oldCover.position.y = MOUNT_Y;
  root.add(oldCover);

  const newCover = dressCover(coverGeom, { color: COLORS.coverNew, cracked: false, dims });
  newCover.name = 'cover-new';
  newCover.position.y = MOUNT_Y;
  newCover.visible = false;
  root.add(newCover);

  // ---- Screws --------------------------------------------------------------
  // Numbered 1..4 in the order the procedure's cross pattern refers to them.
  const screws = angles.map((a, i) => {
    const s = screwMesh();
    s.name = `screw-${i + 1}`;
    s.userData.index = i + 1;
    s.userData.home = new THREE.Vector3(
      Math.cos(deg(a)) * BCR,
      MOUNT_Y + T + 0.0002,
      Math.sin(deg(a)) * BCR,
    );
    s.position.copy(s.userData.home);
    root.add(s);
    return s;
  });

  const driver = hexDriver();
  driver.name = 'hex-driver';
  driver.visible = false;
  root.add(driver);

  return { root, housing, oldCover, newCover, screws, driver, colors: COLORS, dims };
}
