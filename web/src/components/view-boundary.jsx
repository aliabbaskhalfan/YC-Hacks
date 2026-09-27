import { Component } from "react";

// Keeps a 3D view crash (lost WebGL context, bad replay) from blanking the whole stage.
export class ViewBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.warn("3D view failed; showing fallback", error);
  }

  render() {
    if (this.state.failed)
      return (
        <div className="grid h-full place-items-center font-mono text-sm text-muted-foreground">3D view unavailable</div>
      );
    return this.props.children;
  }
}
