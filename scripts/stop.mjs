import { exec } from "node:child_process";
import { readFileSync, unlinkSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const PID_FILE = resolve(ROOT, ".maelstrom.pid");
const PORTS = [8000, 3000];

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
  const result = await run(`taskkill /F /T /PID ${pid}`);
  return result;
}

async function main() {
  let killedFromFile = false;

  // 1. Try PID file first
  if (existsSync(PID_FILE)) {
    try {
      const data = JSON.parse(readFileSync(PID_FILE, "utf-8"));
      console.log(`[stop] Found PID file: backend=${data.backend}, frontend=${data.frontend}`);
      if (data.backend) await killPid(data.backend);
      if (data.frontend) await killPid(data.frontend);
      killedFromFile = true;
    } catch (e) {
      console.log("[stop] Could not parse PID file, falling back to port scan.");
    }
    try { unlinkSync(PID_FILE); } catch {}
    console.log("[stop] PID file removed.");
  }

  // 2. Fallback: scan ports for any remaining processes
  for (const port of PORTS) {
    const pids = await findPidsOnPort(port);
    if (pids.length) {
      console.log(`[stop] Port ${port} still occupied by PID ${pids.join(", ")} — killing...`);
      for (const pid of pids) await killPid(pid);
      console.log(`[stop] Port ${port} freed.`);
    } else if (!killedFromFile) {
      console.log(`[stop] Port ${port} is already free.`);
    }
  }

  console.log("[stop] Done.");
}

main().catch((err) => {
  console.error("[stop] Error:", err);
  process.exit(1);
});
