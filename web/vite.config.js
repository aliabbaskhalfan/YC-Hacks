import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { copyFileSync, mkdirSync, readFileSync, existsSync } from "node:fs";

const repo = path.resolve(__dirname, "..");

// The procedure store and the part registry live outside web/ so the server and
// the procedure viewer read the same files. Rather than copying them into
// public/ (where they go stale the moment the agent updates a step), serve them
// straight off disk in dev and emit them at build time.
const STATIC = {
  "data/procedures/replace-thigh-cover.json": "server/procedures/replace-thigh-cover.json",
  "data/procedures/replace-knee-motor.json": "server/procedures/replace-knee-motor.json",
  "data/registry/parts.json": "data/registry/parts.json",
};

function repoData() {
  return {
    name: "repo-data",

    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const key = req.url?.split("?")[0].replace(/^\//, "");
        const src = STATIC[key];
        if (!src) return next();
        const file = path.resolve(repo, src);
        if (!existsSync(file)) {
          res.statusCode = 404;
          return res.end(`not found: ${src}`);
        }
        res.setHeader("Content-Type", "application/json");
        res.setHeader("Cache-Control", "no-store");
        res.end(readFileSync(file));
      });
    },

    closeBundle() {
      for (const [dest, src] of Object.entries(STATIC)) {
        const from = path.resolve(repo, src);
        if (!existsSync(from)) continue;
        const to = path.resolve(__dirname, "dist", dest);
        mkdirSync(path.dirname(to), { recursive: true });
        copyFileSync(from, to);
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), repoData()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@data": path.resolve(__dirname, "../data"),
    },
  },
  server: { fs: { allow: [".."] } },
  build: {
    // index.html is the stage frontend; procedure.html is the 4d-viewer repair
    // maintenance procedure. They share three but nothing else.
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "index.html"),
        procedure: path.resolve(__dirname, "procedure.html"),
      },
    },
    chunkSizeWarningLimit: 1200,
  },
});
