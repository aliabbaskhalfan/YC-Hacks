import { ANIMATIONS } from './stepAnimations.js';

/**
 * Drives the procedure timeline.
 *
 * Every step animation is a pure function of its local t, so the player can jump,
 * scrub or replay without the scene drifting out of sync. `state` is recomputed
 * each frame and handed to the UI.
 */
export class ProcedurePlayer {
  constructor(procedure, rig) {
    this.procedure = procedure;
    this.rig = rig;
    this.steps = procedure.steps;
    this.durations = this.steps.map((s) => s.duration_s ?? 8);
    this.total = this.durations.reduce((a, b) => a + b, 0);

    this.ctx = {
      sequence: procedure.hardware.sequence,
      targetNm: procedure.hardware.torque_nm,
      tolerance: procedure.hardware.torque_tolerance_nm,
    };

    this.time = 0;
    this.speed = 1;
    this.playing = false;
    this.loop = true;
    this.state = {};
    this.listeners = new Set();
  }

  onChange(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  _emit() {
    for (const fn of this.listeners) fn(this.state);
  }

  /** Global time -> which step, and how far through it. */
  locate(time) {
    let acc = 0;
    for (let i = 0; i < this.durations.length; i++) {
      const d = this.durations[i];
      if (time < acc + d || i === this.durations.length - 1) {
        return { index: i, t: Math.min(1, Math.max(0, (time - acc) / d)), start: acc };
      }
      acc += d;
    }
    return { index: 0, t: 0, start: 0 };
  }

  stepStart(i) {
    return this.durations.slice(0, i).reduce((a, b) => a + b, 0);
  }

  // play/pause go through apply() rather than emitting directly: listeners must
  // never see a state that has not had a step evaluated into it.
  play() {
    if (this.time >= this.total - 1e-6) this.time = 0;
    this.playing = true;
    this.apply();
  }

  pause() {
    this.playing = false;
    this.apply();
  }

  toggle() {
    this.playing ? this.pause() : this.play();
  }

  seek(time) {
    this.time = Math.min(this.total, Math.max(0, time));
    this.apply();
  }

  goToStep(i) {
    const idx = Math.min(this.steps.length - 1, Math.max(0, i));
    this.seek(this.stepStart(idx) + 1e-4);
  }

  next() {
    this.goToStep(this.locate(this.time).index + 1);
  }

  prev() {
    const here = this.locate(this.time);
    // Restart the current step first, jump back only if already at its head.
    this.goToStep(here.t < 0.06 ? here.index - 1 : here.index);
  }

  tick(dt) {
    if (this.playing) {
      this.time += dt * this.speed;
      if (this.time >= this.total) {
        if (this.loop) {
          this.time = 0;
        } else {
          this.time = this.total;
          this.playing = false;
        }
      }
    }
    this.apply();
  }

  /** Evaluate the current step into the scene and rebuild `state`. */
  apply() {
    const { index, t } = this.locate(this.time);
    const step = this.steps[index];
    const fn = ANIMATIONS[step.anim];
    const result = fn ? fn(t, this.rig, this.ctx) : {};

    this.state = {
      index,
      t,
      step,
      time: this.time,
      total: this.total,
      playing: this.playing,
      speed: this.speed,
      camera: step.camera,
      result,
      targetNm: this.ctx.targetNm,
      tolerance: this.ctx.tolerance,
      sequence: this.ctx.sequence,
    };
    this._emit();
    return this.state;
  }
}
