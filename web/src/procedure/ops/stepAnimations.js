// One function per procedure step. Each is a pure function of local time t in [0,1]
// so the timeline can be scrubbed backwards and forwards without accumulating state.
// Positions are in the cover assembly's local frame, where +Y is the cover axis and
// dims.MOUNT_Y is the seated height of the cover's inner face.

const clamp01 = (v) => Math.min(1, Math.max(0, v));
const ease = (t) => t * t * (3 - 2 * t);
const lerp = (a, b, t) => a + (b - a) * t;
const TAU = Math.PI * 2;

/** Map global t onto a sub-window, e.g. screw 2 of 4. */
const window_ = (t, start, end) => clamp01((t - start) / (end - start));

// Removed parts are set down to the SIDE of the cover, never up its axis: the
// close-up shots look straight down that axis, so anything parked along it lands
// in front of the lens and hides the work.
const PARK = { x: -0.1, y: 0.022, z: 0.045 };

/** Where a removed screw ends up, laid out in a row off to the side. */
function traySlot(rig, i) {
  const { R, MOUNT_Y } = rig.dims;
  return { x: -R * 0.6 + i * R * 0.4, y: MOUNT_Y + 0.012, z: R * 1.9 };
}

/** Where the removed cover is set down, in the assembly frame. */
function parkPose(rig) {
  const { MOUNT_Y } = rig.dims;
  return { x: PARK.x, y: MOUNT_Y + PARK.y, z: PARK.z };
}

/**
 * Step 1 — back the four screws out, then lift the cracked cover off.
 * Screws come out in plain order; the cross pattern only matters going back on.
 */
export function removeScrews(t, rig) {
  const { screws, oldCover, newCover, driver, dims } = rig;
  const { MOUNT_Y } = dims;

  newCover.visible = false;
  oldCover.visible = true;

  const PER = 0.16; // each screw owns 16% of the step
  const LIFT_AT = 0.7;

  let active = null;
  screws.forEach((s, i) => {
    const w = window_(t, i * PER, i * PER + PER);
    const home = s.userData.home;
    s.visible = true;

    if (w <= 0) {
      s.position.copy(home);
      s.rotation.y = 0;
      s.userData.headMat.color.setHex(rig.colors.screw);
      return;
    }
    if (w < 1) active = i;

    // Back out along +Y while spinning counter-clockwise, then drift to the tray.
    const out = ease(clamp01(w / 0.75));
    const toTray = ease(window_(w, 0.72, 1));
    const slot = traySlot(rig, i);

    s.rotation.y = -w * TAU * 3.5;
    s.userData.headMat.color.setHex(w > 0.08 ? rig.colors.screwLoose : rig.colors.screw);
    s.position.set(
      lerp(home.x, slot.x, toTray),
      lerp(home.y + out * 0.028, slot.y, toTray),
      lerp(home.z, slot.z, toTray),
    );
  });

  // Driver rides the screw it is turning.
  if (active !== null) {
    const s = screws[active];
    driver.visible = true;
    driver.position.set(s.position.x, s.position.y + 0.004, s.position.z);
    driver.rotation.y = s.rotation.y;
  } else {
    driver.visible = false;
  }

  // Cover comes off in two beats: straight up the axis far enough to clear the
  // lip, then aside to where it is set down.
  const lift = ease(window_(t, LIFT_AT, 1));
  const clear = ease(clamp01(lift / 0.4)); // axial, clears the groove
  const aside = ease(window_(lift, 0.35, 1)); // lateral, out of shot
  const park = parkPose(rig);

  oldCover.position.set(
    park.x * aside,
    MOUNT_Y + clear * 0.03 + (park.y - MOUNT_Y - 0.03) * aside,
    park.z * aside,
  );
  oldCover.rotation.set(0, 0, aside * 0.55);
  oldCover.userData.shell.material.opacity = 1;

  return { activeScrew: active === null ? null : active + 1, coverOff: lift > 0.85 };
}

/** Park the removed hardware where step 1 left it. */
function parkRemoved(rig) {
  const park = parkPose(rig);
  rig.oldCover.visible = true;
  rig.oldCover.position.set(park.x, park.y, park.z);
  rig.oldCover.rotation.set(0, 0, 0.55);
  rig.oldCover.userData.shell.material.opacity = 1;
  rig.screws.forEach((s, i) => {
    const slot = traySlot(rig, i);
    s.visible = true;
    s.position.set(slot.x, slot.y, slot.z);
    s.userData.headMat.color.setHex(rig.colors.screwLoose);
  });
}

/** Step 2 — the housing is exposed; hold on it while it is checked for cracks. */
export function inspectHousing(t, rig) {
  const { newCover, driver } = rig;

  driver.visible = false;
  newCover.visible = false;
  parkRemoved(rig);

  return { verdict: t > 0.55 ? 'clear' : null };
}

/**
 * Step 3 — bring the new cover in and drop it straight down so the inner lip
 * lands in the groove. The warning about seating it crooked stays in the text;
 * acting it out read as the cover clipping through the housing.
 */
export function seatCover(t, rig) {
  const { oldCover, newCover, driver, dims } = rig;
  const { MOUNT_Y } = dims;

  driver.visible = false;
  oldCover.visible = false;
  newCover.visible = true;
  newCover.rotation.set(0, 0, 0);
  rig.screws.forEach((s) => (s.visible = false));

  const shell = newCover.userData.shell;
  shell.material.color.setHex(rig.colors.coverNew);

  // In from the side (0 - 0.45), then straight down the axis (0.5 - 0.95).
  const across = ease(clamp01(t / 0.45));
  const down = ease(window_(t, 0.5, 0.95));

  newCover.position.set(
    lerp(-0.055, 0, across),
    MOUNT_Y + lerp(0.05, 0, down) + lerp(0.025, 0, across),
    lerp(0.022, 0, across),
  );

  return { seated: down > 0.97, lipEngage: down };
}

/**
 * Step 4 — the money shot: cross pattern 1 -> 3 -> 2 -> 4 to 1.0 N.m.
 * Torque ramps per screw and the gauge reads live.
 */
export function torqueCross(t, rig, ctx) {
  const { screws, newCover, oldCover, driver, dims } = rig;
  const { MOUNT_Y } = dims;
  const order = ctx.sequence;
  const target = ctx.targetNm;

  oldCover.visible = false;
  newCover.visible = true;
  newCover.position.set(0, MOUNT_Y, 0);
  newCover.rotation.set(0, 0, 0);
  newCover.userData.shell.material.color.setHex(rig.colors.coverNew);
  newCover.userData.shell.material.opacity = 1;

  const RUN_DOWN = 0.22; // all four go finger tight first
  const PER = (1 - RUN_DOWN) / order.length;

  const torques = new Array(screws.length).fill(0);
  let active = null;
  let liveNm = 0;

  // Finger tight: every screw drops into its boss.
  const fd = ease(clamp01(t / RUN_DOWN));
  screws.forEach((s) => {
    const home = s.userData.home;
    s.visible = true;
    s.position.set(home.x, lerp(home.y + 0.028, home.y, fd), home.z);
    s.rotation.y = fd * TAU * 2;
    s.userData.headMat.color.setHex(rig.colors.screwLoose);
  });

  if (t > RUN_DOWN) {
    order.forEach((num, k) => {
      const w = window_(t, RUN_DOWN + k * PER, RUN_DOWN + (k + 1) * PER);
      if (w <= 0) return;
      const s = screws[num - 1];

      // Torque ramps over the first 80% of that screw's window, then holds.
      const ramp = ease(clamp01(w / 0.8));
      torques[num - 1] = target * ramp;
      s.rotation.y = TAU * 2 + ramp * TAU * 1.2;
      s.position.y = s.userData.home.y - ramp * 0.0012; // pulls down as it tightens

      if (w < 1) {
        active = num;
        liveNm = target * ramp;
      } else {
        torques[num - 1] = target;
        s.userData.headMat.color.setHex(rig.colors.screwSeated);
      }
    });
  }

  // Driver sits on whichever screw is being pulled up.
  if (active !== null) {
    const s = screws[active - 1];
    driver.visible = true;
    driver.position.set(s.position.x, s.position.y + 0.004, s.position.z);
    driver.rotation.y = s.rotation.y;
  } else {
    driver.visible = false;
    if (t >= 1) liveNm = target;
  }

  const doneCount = torques.filter((v) => v >= target - 1e-9).length;
  return { activeScrew: active, liveNm, torques, doneCount, complete: doneCount === screws.length };
}

export const ANIMATIONS = {
  remove_screws: removeScrews,
  inspect_housing: inspectHousing,
  seat_cover: seatCover,
  torque_cross: torqueCross,
};
