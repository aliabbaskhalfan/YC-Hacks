import Go2Viewer from "@/three/Go2Viewer.jsx";
import { COVER_NODE, COVER_PART } from "@/demo/fixtures.js";
import { DataCenterScene } from "./datacenter-scene.jsx";
import { ViewBoundary } from "./view-boundary.jsx";

// three.js +x is the aisle (the Go2's nose); +z is MuJoCo -y, the robot's right, where the cover hits the floor.
const VIEWS = {
  // Studio (no environment): go2-17, and the phone / procedure close-ups of the part.
  close: { camera: { position: [0.25, 0.85, 2.0], fov: 38 }, target: [0.0, 0.12, 0.25] },
  part: { camera: { position: [0.85, 0.55, 1.45], fov: 38 }, target: [0.05, 0.14, 0.3] },
  // Inside the data center aisle, like the MuJoCo render: behind the dog, looking down the rows.
  "dc-walk": { camera: { position: [-3.6, 0.95, -0.3], fov: 45 }, target: [-1.2, 0.3, -0.3] },
  // Chase cam for the patrol: starts behind the dog at the back of the aisle and follows it along x.
  "dc-follow": {
    camera: { position: [-12.9, 1.0, -0.3], fov: 45 },
    target: [-10.5, 0.3, -0.3],
    follow: { cam: [-2.2], target: [0.25] },
  },
  "dc-aisle": { camera: { position: [-3.3, 1.05, -0.28], fov: 45 }, target: [0.2, 0.25, -0.1] },
  "dc-close": { camera: { position: [1.45, 0.95, 0.1], fov: 45 }, target: [0.0, 0.12, 0.25] },
};

export function RobotView({ status, replay, playKey, onReplayEvent, view = "close", env = null, highlight = null, labels = true }) {
  const alerting = status === "red" || status === "in_repair" || status === "fixed";
  const inDataCenter = env === "datacenter";
  const { camera, target, follow = null } = VIEWS[view];
  return (
    <ViewBoundary>
    <Go2Viewer
      status={status}
      alertBody={alerting ? COVER_NODE : null}
      alertText={COVER_PART}
      selectedBody={highlight}
      labels={labels}
      replayUrl={replay}
      playKey={playKey}
      onReplayEvent={onReplayEvent}
      live={false}
      environment={false}
      showSource={false}
      grid={!inDataCenter}
      background={inDataCenter ? "#1d2026" : "#0a0d12"}
      camera={camera}
      target={target}
      follow={follow}
    >
      {inDataCenter && <DataCenterScene />}
    </Go2Viewer>
    </ViewBoundary>
  );
}
