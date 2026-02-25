const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('node:child_process');
const http = require('node:http');
const path = require('node:path');

const PROJECT_ROOT = path.join(__dirname, '..');
const FRONTEND_URL = 'http://127.0.0.1:3302';
const BACKEND_HEALTH_URL = 'http://127.0.0.1:3301/health';
const SHOW_CHILD_LOGS = process.env.MAELSTROM_CHILD_LOGS === '1';
const SHOW_ERROR_DIALOGS = process.env.MAELSTROM_SHOW_ERROR_DIALOG === '1';
const CHILD_LOG_TAIL_LIMIT = 120;
const SCRIPT_READY_URL = Object.freeze({
  'dev:backend': BACKEND_HEALTH_URL,
  'dev:frontend': FRONTEND_URL,
});
const PORT_IN_USE_PATTERN = /EADDRINUSE|10048|address already in use|attempting to bind on address/i;

const CHILDREN = [];
let isShuttingDown = false;

function buildScriptSpawnSpec(scriptName) {
  if (process.platform === 'win32') {
    // Keep UTF-8 code page inside child shell.
    return {
      command: 'cmd.exe',
      args: ['/d', '/s', '/c', `chcp 65001>nul && npm.cmd run ${scriptName}`],
    };
  }
  return {
    command: 'npm',
    args: ['run', scriptName],
  };
}

function appendChildLogTail(state, text) {
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    state.tail.push(trimmed);
    if (state.tail.length > CHILD_LOG_TAIL_LIMIT) {
      state.tail.shift();
    }
  }
}

function handleChildOutput(state, chunk, stream) {
  const text = Buffer.isBuffer(chunk) ? chunk.toString('utf8') : String(chunk);
  if (!text) {
    return;
  }

  appendChildLogTail(state, text);

  if (PORT_IN_USE_PATTERN.test(text)) {
    state.sawPortInUse = true;
  }

  // Default to quiet mode to avoid Windows terminal mojibake.
  if (SHOW_CHILD_LOGS) {
    stream.write(`[${state.scriptName}] ${text}`);
  }
}

function pipeChildLogs(state, child) {
  if (child.stdout) {
    child.stdout.on('data', (chunk) => {
      handleChildOutput(state, chunk, process.stdout);
    });
  }

  if (child.stderr) {
    child.stderr.on('data', (chunk) => {
      handleChildOutput(state, chunk, process.stderr);
    });
  }
}

async function shouldReuseExistingService(scriptName, state) {
  if (!state.sawPortInUse) {
    return false;
  }

  const readyUrl = SCRIPT_READY_URL[scriptName];
  if (!readyUrl) {
    return false;
  }

  const reachable = await ping(readyUrl);
  if (!reachable) {
    return false;
  }

  console.warn(`[electron] ${scriptName} exited with port-in-use, reusing existing service at ${readyUrl}`);
  return true;
}

function createChildEnv() {
  const env = { ...process.env };
  if (process.platform === 'win32') {
    env.PYTHONUTF8 = env.PYTHONUTF8 || '1';
    env.PYTHONIOENCODING = env.PYTHONIOENCODING || 'utf-8';
  }
  return env;
}

function spawnScript(scriptName) {
  const { command, args } = buildScriptSpawnSpec(scriptName);
  const state = {
    scriptName,
    tail: [],
    sawPortInUse: false,
  };

  console.log(`[electron] starting child process: ${scriptName}`);

  const child = spawn(command, args, {
    cwd: PROJECT_ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
    env: createChildEnv(),
    windowsHide: true,
  });

  pipeChildLogs(state, child);

  child.on('error', (error) => {
    console.error(`[electron] failed to start ${scriptName}:`, error);
  });

  child.on('exit', async (code, signal) => {
    if (isShuttingDown) {
      return;
    }
    if (code && code !== 0) {
      if (await shouldReuseExistingService(scriptName, state)) {
        return;
      }

      console.error(`[electron] child ${scriptName} exited unexpectedly, code=${code}, signal=${String(signal || '')}`);
      if (state.tail.length > 0) {
        const recent = state.tail.slice(-10).join('\n');
        console.error(`[electron] recent logs for ${scriptName}:\n${recent}`);
      }
      showErrorDialogIfNeeded('Service exited unexpectedly', `${scriptName} exited with code ${code}`);
      app.quit();
    }
  });

  CHILDREN.push(child);
  return child;
}

function ping(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });

    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForUrl(url, timeoutMs) {
  const start = Date.now();

  while (Date.now() - start < timeoutMs) {
    const ready = await ping(url);
    if (ready) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 700));
  }

  throw new Error(`service startup timeout: ${url}`);
}

function showErrorDialogIfNeeded(title, message) {
  if (SHOW_ERROR_DIALOGS) {
    dialog.showErrorBox(title, message);
  }
}

async function ensureService(scriptName, readyUrl, timeoutMs) {
  if (await ping(readyUrl)) {
    console.log(`[electron] reusing existing service for ${scriptName}: ${readyUrl}`);
    return;
  }

  spawnScript(scriptName);
  await waitForUrl(readyUrl, timeoutMs);
}

function cleanupChildren() {
  isShuttingDown = true;
  for (const child of CHILDREN) {
    if (!child || child.killed) {
      continue;
    }

    try {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
      } else {
        child.kill('SIGTERM');
      }
    } catch (error) {
      console.error('[electron] failed to stop child process:', error);
    }
  }
}

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  let shown = false;
  mainWindow.once('ready-to-show', () => {
    shown = true;
    mainWindow.show();
  });

  setTimeout(() => {
    if (!shown && !mainWindow.isDestroyed()) {
      mainWindow.show();
    }
  }, 8000);

  mainWindow.loadURL(FRONTEND_URL);
}

async function bootstrap() {
  try {
    await ensureService('dev:backend', BACKEND_HEALTH_URL, 120000);
    await ensureService('dev:frontend', FRONTEND_URL, 120000);
    createWindow();
  } catch (error) {
    console.error('[electron] bootstrap failed:', error);
    showErrorDialogIfNeeded('Bootstrap failed', String(error.message || error));
    app.quit();
  }
}

app.whenReady().then(bootstrap).catch((error) => {
  console.error('[electron] initialization failed:', error);
  showErrorDialogIfNeeded('Initialization failed', String(error.message || error));
  app.quit();
});

app.on('window-all-closed', () => {
  cleanupChildren();
  app.quit();
});

app.on('before-quit', () => {
  cleanupChildren();
});
