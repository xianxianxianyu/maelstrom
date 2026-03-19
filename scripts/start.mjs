import { exec, spawn } from "node:child_process";
import { writeFileSync, unlinkSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const PID_FILE = resolve(ROOT, ".maelstrom.pid");
const PORTS = [8000, 3000];

// ── Helpers ──────────────────────────────────────────────────────────

function run(cmd) {
  return new Promise((resolve) => {
    exec(cmd, (err, stdout) => resolve(err ? "" : stdout));
  });
}

async function findPidsOnPort(port) {
  const out = await run(`netstat -ano | findstr :${port} | findstr LISTENING`);
  const pids = new Set();
  for (const line of out.split("\n")) {
    const parts = line.trim().split(/\s+/);
    const pid = parseInt(parts[parts.length - 1], 10);
    if (pid && pid !== 0) pids.add(pid);
  }
  return [...pids];
}

async function killPid(pid) {
  await run(`taskkill /F /PID ${pid}`);
}

async function cleanStalePorts() {
  for (const port of PORTS) {
    const pids = await findPidsOnPort(port);
    if (pids.length) {
      console.log(`[cleanup] Port ${port} occupied by PID ${pids.join(", ")} — killing...`);
      for (const pid of pids) await killPid(pid);
      console.log(`[cleanup] Port ${port} freed.`);
    }
  }
}

// ── Prefixed output ──────────────────────────────────────────────────

function prefixStream(stream, tag) {
  stream.on("data", (chunk) => {
    const lines = chunk.toString().split("\n");
    for (const line of lines) {
      if (line.trim()) process.stdout.write(`${tag} ${line}\n`);
    }
  });
}

// ── Main ─────────────────────────────────────────────────────────────

async function main() {
  console.log("[maelstrom] Checking for stale processes...");
  await cleanStalePorts();

  console.log("[maelstrom] Starting backend (uvicorn :8000)...");
  const backend = spawn(
    "uvicorn",
    ["maelstrom.main:app", "--reload", "--port", "8000"],
    { cwd: ROOT, shell: true, stdio: ["ignore", "pipe", "pipe"] }
  );

  console.log("[maelstrom] Starting frontend (pnpm dev :3000)...");
  const frontend = spawn("pnpm", ["dev"], {
    cwd: resolve(ROOT, "frontend"),
    shell: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  prefixStream(backend.stdout, "[backend]");
  prefixStream(backend.stderr, "[backend]");
  prefixStream(frontend.stdout, "[frontend]");
  prefixStream(frontend.stderr, "[frontend]");

  // Write PID file
  const pidData = { backend: backend.pid, frontend: frontend.pid };
  writeFileSync(PID_FILE, JSON.stringify(pidData, null, 2));
  console.log(`[maelstrom] PIDs written to .maelstrom.pid (backend=${backend.pid}, frontend=${frontend.pid})`);

  // Handle child exits
  backend.on("exit", (code) => {
    console.log(`[backend] exited with code ${code}`);
  });
  frontend.on("exit", (code) => {
    console.log(`[frontend] exited with code ${code}`);
  });

  // Graceful shutdown
  function shutdown() {
    console.log("\n[maelstrom] Shutting down...");
    if (!backend.killed) {
      try { exec(`taskkill /F /T /PID ${backend.pid}`); } catch {}
    }
    if (!frontend.killed) {
      try { exec(`taskkill /F /T /PID ${frontend.pid}`); } catch {}
    }
    try { unlinkSync(PID_FILE); } catch {}
    console.log("[maelstrom] Goodbye.");
    process.exit(0);
  }

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  // On Windows, handle the console close event
  if (process.platform === "win32") {
    const rl = await import("node:readline");
    const i = rl.createInterface({ input: process.stdin });
    i.on("close", shutdown);
  }
}

main().catch((err) => {
  console.error("[maelstrom] Fatal error:", err);
  process.exit(1);
});
