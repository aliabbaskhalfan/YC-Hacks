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
const replayCache = new Map();

// Fetch (once) and cache a replay, so switching between replays mid-demo never waits on the network.
export function loadReplay(url) {
  if (!replayCache.has(url)) {
    replayCache.set(url, fetch(url).then((r) => r.json()).catch((err) => {
      replayCache.delete(url);
      throw err;
    }));
  }
  return replayCache.get(url);
}

/**
 * `replayUrl` / `playKey`: changing either restarts playback from t=0.
 * Replays with `loop: false` play once and hold their last frame; their
 * `events` ([{t, type, ...}]) fire `onReplayEvent` once per play, and their
 * `props` (e.g. a toolbox) are returned for the viewer to draw.
 */
export function usePoseSource({ wsUrl, replayUrl, onAlert, onReplayEvent, playKey = 0 }) {
  const poseRef = useRef({ bodies: null });
  const [source, setSource] = useState("connecting");
  const [props, setProps] = useState([]);
  const replay = useRef(null);
  const lastAlertKey = useRef(null);
  const onEventRef = useRef(onReplayEvent);
  onEventRef.current = onReplayEvent;

  const fireAlert = (alert) => {
    const key = alert ? JSON.stringify(alert) : null;
    if (key !== lastAlertKey.current) {
      lastAlertKey.current = key;
      onAlert?.(alert ?? null);
    }
  };

  // ---- replay fallback: cached fetch; the previous pose stays up until the new replay is ready ----
  useEffect(() => {
    let cancelled = false;
    replay.current = null;
    loadReplay(replayUrl)
      .then((data) => {
        if (cancelled) return;
        replay.current = { ...data, start: performance.now(), fired: new Set() };
        setProps(data.props ?? []);
      })
      .catch((err) => console.warn("usePoseSource: replay load failed", err));
    return () => {
      cancelled = true;
    };
  }, [replayUrl, playKey]);

  useEffect(() => {
    let raf;
    const tick = () => {
      const r = replay.current;
      if (source !== "live" && r) {
        const raw = (performance.now() - r.start) / 1000;
        const elapsed = r.loop === false ? Math.min(raw, r.period) : raw % r.period;
        const idx = Math.min(r.frames.length - 1, Math.floor((elapsed / r.period) * r.frames.length));
        poseRef.current = { bodies: r.frames[idx].bodies };
        for (const ev of r.events ?? []) {
          if (raw >= ev.t && !r.fired.has(ev)) {
            r.fired.add(ev);
            onEventRef.current?.(ev);
          }
        }
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

  return useMemo(() => ({ poseRef, source, props }), [poseRef, source, props]);
}
