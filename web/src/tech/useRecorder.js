import { useCallback, useEffect, useRef, useState } from "react";

const BARS = 28;
const TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];

// Voice note capture: auto-stops at maxMs and exposes a level waveform. If the browser has no
// microphone (or permission is denied) it records a simulated note instead, so the stage flow
// looks identical; onStop then receives null instead of a Blob.
export function useRecorder({ maxMs = 15000, onStop }) {
  const [state, setState] = useState("idle"); // idle | requesting | recording
  const [elapsed, setElapsed] = useState(0);
  const [levels, setLevels] = useState(() => Array(BARS).fill(0));
  const rec = useRef(null);
  const onStopRef = useRef(onStop);
  onStopRef.current = onStop;

  const cleanup = () => {
    const r = rec.current;
    if (!r) return;
    clearInterval(r.bars);
    clearInterval(r.timer);
    r.stream?.getTracks().forEach((t) => t.stop());
    r.audio?.close().catch(() => {});
    rec.current = null;
  };

  const finish = (blob) => {
    cleanup();
    setState("idle");
    onStopRef.current?.(blob);
  };

  const stop = useCallback(() => {
    const r = rec.current;
    if (!r) return;
    if (r.recorder && r.recorder.state !== "inactive") r.recorder.stop();
    else if (!r.recorder) finish(null);
  }, []);

  const start = useCallback(async () => {
    if (rec.current) return;
    setState("requesting");
    const r = { bars: 0, timer: 0 };
    let sample; // () => level in 0..1

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = TYPES.find((t) => window.MediaRecorder?.isTypeSupported?.(t));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks = [];
      recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      recorder.onstop = () => finish(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
      const audio = new AudioContext();
      const analyser = audio.createAnalyser();
      analyser.fftSize = 512;
      audio.createMediaStreamSource(stream).connect(analyser);
      const buf = new Uint8Array(analyser.fftSize);
      sample = () => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += ((v - 128) / 128) ** 2;
        return Math.min(1, Math.sqrt(sum / buf.length) * 4);
      };
      Object.assign(r, { stream, recorder, audio });
      recorder.start();
    } catch (err) {
      console.warn("useRecorder: no microphone, recording a simulated note", err);
      let t = 0;
      sample = () => {
        t += 0.35;
        const speech = 0.5 + 0.5 * Math.sin(t * 0.9) * Math.sin(t * 0.23);
        return Math.max(0.05, Math.min(1, speech * (0.55 + Math.random() * 0.45)));
      };
    }

    const t0 = performance.now();
    rec.current = r;
    // Timers, not requestAnimationFrame: rAF is throttled in background or embedded tabs.
    r.bars = setInterval(() => {
      const level = sample();
      setLevels((l) => [...l.slice(1), level]);
    }, 70);
    r.timer = setInterval(() => {
      const ms = performance.now() - t0;
      setElapsed(Math.min(ms, maxMs));
      if (ms >= maxMs) stop();
    }, 100);

    setElapsed(0);
    setLevels(Array(BARS).fill(0));
    setState("recording");
  }, [maxMs, stop]);

  useEffect(() => cleanup, []);

  return { state, elapsed, levels, start, stop, maxMs };
}
