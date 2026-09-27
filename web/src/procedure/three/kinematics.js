// Go2 kinematic tree, transcribed from mujoco_menagerie/unitree_go2/go2.xml.
// MuJoCo is Z-up; the viewer rotates the whole rig -90deg about X to get three.js Y-up.

export const LEGS = ['FL', 'FR', 'RL', 'RR'];

export const BASE_HEIGHT = 0.445; // <body name="base" pos="0 0 0.445">

// Per-leg body offsets in the parent body's frame (metres, MuJoCo axes).
export const OFFSETS = {
  FL: { hip: [0.1934, 0.0465, 0], thigh: [0, 0.0955, 0], calf: [0, 0, -0.213] },
  FR: { hip: [0.1934, -0.0465, 0], thigh: [0, -0.0955, 0], calf: [0, 0, -0.213] },
  RL: { hip: [-0.1934, 0.0465, 0], thigh: [0, 0.0955, 0], calf: [0, 0, -0.213] },
  RR: { hip: [-0.1934, -0.0465, 0], thigh: [0, -0.0955, 0], calf: [0, 0, -0.213] },
};

// Joint axes in the child body's frame: abduction about X, hip pitch and knee about Y.
export const AXES = { hip: 'x', thigh: 'y', calf: 'y' };

// Joint limits from go2.xml, used to clamp anything the UI or a pose feeds in.
export const LIMITS = {
  hip: [-1.0472, 1.0472],
  thigh_front: [-1.5708, 3.4907],
  thigh_back: [-0.5236, 4.5379],
  calf: [-2.7227, -0.83776],
};

const clamp = (v, [lo, hi]) => Math.min(hi, Math.max(lo, v));

/** Build a full joint map from per-leg [hip, thigh, calf] triples. */
export function pose(spec) {
  const out = {};
  for (const leg of LEGS) {
    const [hip, thigh, calf] = spec[leg] ?? spec.default;
    const thighLimit = leg.startsWith('F') ? LIMITS.thigh_front : LIMITS.thigh_back;
    out[leg] = {
      hip: clamp(hip, LIMITS.hip),
      thigh: clamp(thigh, thighLimit),
      calf: clamp(calf, LIMITS.calf),
    };
  }
  return out;
}

export const POSES = {
  // Normal standing stance.
  stand: pose({ default: [0, 0.9, -1.8] }),
  // On the bench: the front-right leg is splayed out and pitched forward so the
  // thigh actuator cover is clear of the belly and the other three legs.
  service_fr: pose({
    default: [0, 0.82, -1.65],
    FR: [-0.62, 0.3, -1.15],
  }),
};

/** Linear blend between two joint maps, for animating between poses. */
export function blendPose(a, b, t) {
  const out = {};
  for (const leg of LEGS) {
    out[leg] = {
      hip: a[leg].hip + (b[leg].hip - a[leg].hip) * t,
      thigh: a[leg].thigh + (b[leg].thigh - a[leg].thigh) * t,
      calf: a[leg].calf + (b[leg].calf - a[leg].calf) * t,
    };
  }
  return out;
}
