const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};

/** Torque gauge: an arc that fills to spec, with over-torque shown as a red band. */
export class TorqueGauge {
  constructor(root, targetNm, tolerance) {
    this.target = targetNm;
    this.tolerance = tolerance;
    // Hidden until the torque step asks for it.
    this.node = el('div', 'gauge hidden');
    this.canvas = el('canvas', 'gauge-canvas');
    this.canvas.width = 260;
    this.canvas.height = 150;
    this.node.appendChild(this.canvas);

    this.readout = el('div', 'gauge-readout', `<span class="nm">0.00</span><em>N·m</em>`);
    this.node.appendChild(this.readout);
    this.node.appendChild(
      el('div', 'gauge-spec', `spec ${targetNm.toFixed(1)} ±${tolerance.toFixed(1)} N·m`),
    );
    root.appendChild(this.node);
    this.draw(0);
  }

  draw(nm) {
    const g = this.canvas.getContext('2d');
    const W = this.canvas.width;
    const cx = W / 2;
    const cy = 128;
    const r = 96;
    const A0 = Math.PI * 0.86;
    const A1 = Math.PI * 2.14;
    const max = this.target * 1.45;

    g.clearRect(0, 0, W, this.canvas.height);
    g.lineCap = 'butt';

    // Track
    g.strokeStyle = '#e3e8ee';
    g.lineWidth = 15;
    g.beginPath();
    g.arc(cx, cy, r, A0, A1);
    g.stroke();

    // In-spec band
    const at = (v) => A0 + (A1 - A0) * Math.min(1, v / max);
    g.strokeStyle = 'rgba(22,163,74,0.30)';
    g.lineWidth = 15;
    g.beginPath();
    g.arc(cx, cy, r, at(this.target - this.tolerance), at(this.target + this.tolerance));
    g.stroke();

    // Over-torque band
    g.strokeStyle = 'rgba(217,45,32,0.28)';
    g.beginPath();
    g.arc(cx, cy, r, at(this.target + this.tolerance), A1);
    g.stroke();

    // Needle fill
    const over = nm > this.target + this.tolerance;
    const inSpec = nm >= this.target - this.tolerance && !over;
    g.strokeStyle = over ? '#d92d20' : inSpec ? '#16a34a' : '#2563d6';
    g.lineWidth = 15;
    g.beginPath();
    g.arc(cx, cy, r, A0, at(nm));
    g.stroke();

    // Target tick
    g.strokeStyle = '#344054';
    g.lineWidth = 2;
    const a = at(this.target);
    g.beginPath();
    g.moveTo(cx + Math.cos(a) * (r - 11), cy + Math.sin(a) * (r - 11));
    g.lineTo(cx + Math.cos(a) * (r + 11), cy + Math.sin(a) * (r + 11));
    g.stroke();

    this.readout.querySelector('.nm').textContent = nm.toFixed(2);
    this.readout.classList.toggle('in-spec', inSpec);
    this.readout.classList.toggle('over', over);
  }

  setVisible(v) {
    this.node.classList.toggle('hidden', !v);
  }
}

/** Compact caption over the stage: which step it is and what to do. */
export class Caption {
  constructor(root, procedure) {
    this.total = procedure.steps.length;
    this.node = root;
    this.node.innerHTML = `
      <div class="cap-head">
        <span class="cap-count"></span>
        <span class="cap-title"></span>
      </div>
      <p class="cap-text"></p>`;
    this.count = root.querySelector('.cap-count');
    this.title = root.querySelector('.cap-title');
    this.text = root.querySelector('.cap-text');
  }

  render(state) {
    const step = state?.step;
    if (!step || step.step_id === this._shown) return;
    this._shown = step.step_id;
    this.count.textContent = `${step.step_id} / ${this.total}`;
    this.title.textContent = step.title;
    this.text.textContent = step.text;
  }
}
