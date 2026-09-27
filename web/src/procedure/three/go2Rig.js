import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { AXES, BASE_HEIGHT, LEGS, OFFSETS, POSES } from './kinematics.js';

// go2.glb carries one node per MuJoCo body, geometry baked into that body's frame.
// The rig below rebuilds the joint chain around those nodes, so anything parented to
// a joint node (the cover, the screws, the driver) follows the leg for free.

// The Go2's MuJoCo materials are mostly literal black (rgba 0 0 0), which reads as
// a silhouette in a close-up. A service viewer needs to show form, not livery, so
// the body gets one neutral CAD grey and the exported vertex colours are ignored.
const MAT = { body: { color: 0x5f6979, roughness: 0.52, metalness: 0.3 } };

export class Go2Rig {
  constructor() {
    this.root = new THREE.Group();
    this.root.name = 'go2-root';
    // MuJoCo Z-up -> three.js Y-up.
    this.root.rotation.x = -Math.PI / 2;

    this.joints = {}; // 'FR_thigh' -> Object3D whose rotation is that joint
    this.bodies = {}; // 'FR_thigh' -> Object3D holding the mesh
    this.meshes = {}; // 'FR_thigh' -> Mesh
    this._originalMats = new Map();
    this.pose = structuredClone(POSES.stand);
  }

  async load(url) {
    const gltf = await new GLTFLoader().loadAsync(url);

    // trimesh exports a flat scene: one child node per body, named after the body.
    const byName = new Map();
    gltf.scene.traverse((o) => {
      if (o.isMesh) byName.set(o.parent?.name || o.name, o);
    });

    const base = new THREE.Group();
    base.name = 'base';
    base.position.set(0, 0, BASE_HEIGHT);
    this.root.add(base);
    this.bodies.base = base;
    this._attach(base, byName.get('base'), 'base');

    for (const leg of LEGS) {
      const off = OFFSETS[leg];
      let parent = base;
      for (const seg of ['hip', 'thigh', 'calf']) {
        const name = `${leg}_${seg}`;
        const joint = new THREE.Group();
        joint.name = name;
        joint.position.set(...off[seg]);
        parent.add(joint);
        this.joints[name] = joint;
        this.bodies[name] = joint;
        this._attach(joint, byName.get(name), name);
        parent = joint;
      }
    }

    this.applyPose(this.pose);
    return this;
  }

  _attach(parent, mesh, name) {
    if (!mesh) {
      console.warn(`go2.glb has no node named ${name}`);
      return;
    }
    // Detach from the loaded scene graph; geometry is already in body frame.
    mesh.position.set(0, 0, 0);
    mesh.quaternion.identity();
    mesh.scale.set(1, 1, 1);
    mesh.name = `${name}_mesh`;
    mesh.userData.bodyName = name;

    // Guard: a glTF without a NORMAL attribute renders with the default normal,
    // i.e. completely flat. Derive them rather than trusting the exporter.
    if (!mesh.geometry.attributes.normal) mesh.geometry.computeVertexNormals();

    mesh.material = new THREE.MeshStandardMaterial(MAT.body);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    this._originalMats.set(name, mesh.material);
    this.meshes[name] = mesh;
    parent.add(mesh);
  }

  /** pose: { FR: {hip, thigh, calf}, ... } in radians. */
  applyPose(pose) {
    this.pose = pose;
    for (const leg of LEGS) {
      for (const seg of ['hip', 'thigh', 'calf']) {
        const joint = this.joints[`${leg}_${seg}`];
        if (!joint) continue;
        joint.rotation.set(0, 0, 0);
        joint.rotation[AXES[seg]] = pose[leg][seg];
      }
    }
    this.root.updateMatrixWorld(true);
  }

  /**
   * Fade everything except the named bodies, so the work area reads clearly.
   * `focus` of null restores the whole robot.
   */
  setFocus(focus) {
    // Called every frame, so bail unless the focus actually changed: touching
    // material flags each frame forces needless shader churn.
    const key = focus ? focus.join(',') : '*';
    if (key === this._focusKey) return;
    this._focusKey = key;

    // Ghosted, not hidden: against the white stage a translucent body reads as a
    // faint outline, so the whole robot stays on screen while the camera still
    // sees through the hip block to the cover behind it.
    const keep = focus ? new Set(focus) : null;
    for (const [name, mesh] of Object.entries(this.meshes)) {
      const solid = !keep || keep.has(name);
      mesh.visible = true;
      mesh.material.transparent = !solid;
      mesh.material.opacity = solid ? 1 : 0.1;
      mesh.material.depthWrite = solid;
      mesh.castShadow = solid;
      mesh.material.needsUpdate = true;
    }
  }

  /** Pickable meshes for raycasting. */
  get pickables() {
    return Object.values(this.meshes);
  }
}
