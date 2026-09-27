import * as THREE from 'three';

// Camera shots are defined relative to the cover's own frame rather than in world
// space, so they stay correct whatever pose the leg is in.
//
//   n  the cover axis (+Y in the assembly frame), pointing out of the face
//   u  a tangent that stays roughly world-up, so shots never roll
//   v  n x u, the remaining tangent

const SHOTS = {
  // The whole robot, for context before the work starts.
  hero: { target: 'robot', dist: 1.5, n: 0.45, u: 0.42, v: 1.0, fov: 34 },
  // Looking onto the cover from above and to one side: reads depth.
  cover_three_quarter: { target: 'cover', dist: 0.34, n: 0.78, u: 0.5, v: 0.38, fov: 32 },
  // Near enough to straight down the axis for the cross pattern to read, but
  // offset so the driver is not pointing into the lens.
  cover_face_on: { target: 'cover', dist: 0.3, n: 0.93, u: 0.3, v: 0.2, fov: 30 },
  // Three-quarter from above: enough axial component to actually see the cover
  // face, enough tilt to read the gap closing as the lip drops into the groove.
  // A near edge-on shot looked along the face and showed nothing.
  cover_section: { target: 'cover', dist: 0.3, n: 0.68, u: 0.44, v: 0.55, fov: 32 },
};

const WORLD_UP = new THREE.Vector3(0, 1, 0);

export class CameraDirector {
  constructor(camera) {
    this.camera = camera;
    this.current = { pos: new THREE.Vector3(), look: new THREE.Vector3() };
    this.goal = { pos: new THREE.Vector3(), look: new THREE.Vector3(), fov: 32 };
    this._init = false;
  }

  /** Recompute the goal for a named shot. */
  setShot(name, assembly, robotCentre) {
    const shot = SHOTS[name] ?? SHOTS.cover_three_quarter;
    assembly.updateWorldMatrix(true, false);

    const origin = new THREE.Vector3().setFromMatrixPosition(assembly.matrixWorld);
    const n = new THREE.Vector3(0, 1, 0)
      .applyQuaternion(assembly.getWorldQuaternion(new THREE.Quaternion()))
      .normalize();

    // Build a stable tangent basis that does not roll as the leg moves.
    let u = new THREE.Vector3().crossVectors(n, WORLD_UP);
    if (u.lengthSq() < 1e-6) u = new THREE.Vector3(1, 0, 0);
    u.normalize();
    const v = new THREE.Vector3().crossVectors(u, n).normalize();

    const look = shot.target === 'robot' ? robotCentre.clone() : origin.clone();
    const dir = new THREE.Vector3()
      .addScaledVector(n, shot.n)
      .addScaledVector(u, shot.u)
      .addScaledVector(v, shot.v)
      .normalize();

    this.goal.pos.copy(look).addScaledVector(dir, shot.dist);
    this.goal.look.copy(look);
    this.goal.fov = shot.fov;

    if (!this._init) {
      this.current.pos.copy(this.goal.pos);
      this.current.look.copy(this.goal.look);
      this.camera.fov = shot.fov;
      this._init = true;
    }
  }

  /** Ease toward the goal; `orbit` adds a slow drift so the shot stays alive. */
  update(dt, orbit = 0) {
    // Frame-rate independent smoothing, tuned slow: ~1.1 s to close 90% of the
    // gap, so the move from the wide shot down onto the leg reads as a travel
    // rather than a cut.
    const k = 1 - Math.pow(0.12, dt);
    this.current.pos.lerp(this.goal.pos, k);
    this.current.look.lerp(this.goal.look, k);

    const pos = this.current.pos.clone();
    if (orbit) {
      const offset = pos.clone().sub(this.current.look);
      offset.applyAxisAngle(WORLD_UP, orbit);
      pos.copy(this.current.look).add(offset);
    }

    this.camera.position.copy(pos);
    this.camera.lookAt(this.current.look);
    this.camera.fov += (this.goal.fov - this.camera.fov) * k;
    this.camera.updateProjectionMatrix();
  }
}

export const SHOT_NAMES = Object.keys(SHOTS);
