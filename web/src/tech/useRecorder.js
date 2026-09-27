import { useCallback, useEffect, useRef, useState } from "react";

const BARS = 28;
const TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];

// Voice note capture: auto-stops at maxMs, exposes a live level waveform, never throws.
export function useRecorder({ maxMs = 15000, onStop }) {
  const [state, setState] = useState("idle"); // idle | requesting | recording | error
  const [elapsed, setElapsed] = useState(0);
  const [levels, setLevels] = useState(() => Array(BARS).fill(0));
  const [error, setError] = useState(null);
  const rec = useRef(null);
  const onStopRef = useRef(onStop);
  onStopRef.current = onStop;

  const cleanup = () => {
    const r = rec.current;
    if (!r) return;
    cancelAnimationFrame(r.raf);
    clearInterval(r.timer);
    r.stream.getTracks().forEach((t) => t.stop());
    r.audio.close().catch(() => {});
    rec.current = null;
  };

  const stop = useCallback(() => {
    const r = rec.current;
    if (r && r.recorder.state !== "inactive") r.recorder.stop();
  }, []);

  const start = useCallback(async () => {
    if (rec.current) return;
    setError(null);
    setState("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = TYPES.find((t) => window.MediaRecorder?.isTypeSupported?.(t));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks = [];
      recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        cleanup();
        setState("idle");
        onStopRef.current?.(blob);
      };

      const audio = new AudioContext();
      const analyser = audio.createAnalyser();
      analyser.fftSize = 512;
      audio.createMediaStreamSource(stream).connect(analyser);
      const buf = new Uint8Array(analyser.fftSize);
      const t0 = performance.now();
      const r = { stream, recorder, audio, raf: 0, timer: 0, lastBar: 0 };
      rec.current = r;

      const tick = (now) => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += ((v - 128) / 128) ** 2;
        if (now - r.lastBar > 70) {
          r.lastBar = now;
          const rms = Math.min(1, Math.sqrt(sum / buf.length) * 4);
          setLevels((l) => [...l.slice(1), rms]);
        }
        r.raf = requestAnimationFrame(tick);
      };
      r.raf = requestAnimationFrame(tick);
      r.timer = setInterval(() => {
        const ms = performance.now() - t0;
        setElapsed(Math.min(ms, maxMs));
        if (ms >= maxMs) stop();
      }, 100);

      setElapsed(0);
      setLevels(Array(BARS).fill(0));
      recorder.start();
      setState("recording");
    } catch (err) {
      cleanup();
      setState("error");
      setError(err?.name === "NotAllowedError" ? "Microphone blocked. Type the fix note instead." : "No microphone available. Type the fix note instead.");
    }
  }, [maxMs, stop]);

  useEffect(() => cleanup, []);

  return { state, elapsed, levels, error, start, stop, maxMs };
}
