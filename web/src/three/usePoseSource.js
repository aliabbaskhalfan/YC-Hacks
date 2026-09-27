import { useEffect, useMemo, useRef, useState } from "react";

const RECONNECT_DELAY_MS = 3000;

/**
 * Feeds the viewer world-frame body poses every frame, per BUILD_SPEC.md
 * Section 6.2: try the live `WS /sim/stream` first, and fall back to the
 * baked replay JSON (Section 6.2's "replay mode") whenever it's unavailable
 * — which, until the sim track ships the live server, is always. Returns a
 * ref rather than React state: Go2Rig reads it inside its own useFrame, so
 * a 30-60Hz pose update never triggers a React re-render.
 */
export function usePoseSource({ wsUrl, replayUrl, onAlert }) {
  const poseRef = useRef({ bodies: null });
  const [source, setSource] = useState("connecting");
  const replay = useRef(null);
  const lastAlertKey = useRef(null);

  const fireAlert = (alert) => {
    const key = alert ? JSON.stringify(alert) : null;
    if (key !== lastAlertKey.current) {
      lastAlertKey.current = key;
      onAlert?.(alert ?? null);
    }
  };

  // ---- replay fallback: fetched once, looped by wall-clock time ----
  useEffect(() => {
    let cancelled = false;
    fetch(replayUrl)
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) replay.current = data;
      })
      .catch((err) => console.warn("usePoseSource: replay load failed", err));
    return () => {
      cancelled = true;
    };
  }, [replayUrl]);

  useEffect(() => {
    let raf;
    const start = performance.now();
    const tick = () => {
      if (source !== "live" && replay.current) {
        const { frames, period } = replay.current;
        const elapsed = ((performance.now() - start) / 1000) % period;
        const idx = Math.min(
          frames.length - 1,
          Math.floor((elapsed / period) * frames.length)
        );
        poseRef.current = { bodies: frames[idx].bodies };
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [source]);

  // ---- live WS: reconnects with a fixed backoff, never throws ----
  useEffect(() => {
    if (!wsUrl) return undefined;
    let socket;
    let retryTimer;
    let stopped = false;

    const connect = () => {
      if (stopped) return;
      try {
        socket = new WebSocket(wsUrl);
      } catch {
        retryTimer = setTimeout(connect, RECONNECT_DELAY_MS);
        return;
      }

      socket.onopen = () => setSource("live");
      socket.onmessage = (event) => {
        try {
          const frame = JSON.parse(event.data);
          poseRef.current = { bodies: frame.bodies, t: frame.t, unitId: frame.unit_id };
          fireAlert(frame.alert ?? null);
        } catch (err) {
          console.warn("usePoseSource: bad frame", err);
        }
      };
      socket.onclose = socket.onerror = () => {
        setSource((prev) => (prev === "live" ? "replay" : prev));
        if (!stopped) retryTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, [wsUrl]);

  return useMemo(() => ({ poseRef, source }), [poseRef, source]);
}
