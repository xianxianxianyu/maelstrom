const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('node:child_process');
const http = require('node:http');
const path = require('node:path');

const PROJECT_ROOT = path.join(__dirname, '..');
const FRONTEND_URL = 'http://127.0.0.1:3302';
const BACKEND_HEALTH_URL = 'http://127.0.0.1:3301/health';

const CHILDREN = [];
let isShuttingDown = false;

function buildScriptCommand(scriptName) {
  if (process.platform === 'win32') {
    // 统一切到 UTF-8 代码页，避免 Windows 控制台中文乱码。
    return `chcp 65001>nul && npm.cmd run ${scriptName}`;
  }
  return `npm run ${scriptName}`;
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
  const command = buildScriptCommand(scriptName);
  console.log(`[electron] 启动子进程: ${command}`);

  const child = spawn(command, {
    cwd: PROJECT_ROOT,
    stdio: 'inherit',
    shell: true,
    env: createChildEnv(),
    windowsHide: false,
  });

  child.on('error', (error) => {
    console.error(`[electron] 启动 ${scriptName} 失败:`, error);
  });

  child.on('exit', (code, signal) => {
    if (isShuttingDown) {
      return;
    }
    if (code && code !== 0) {
      console.error(`[electron] 子进程 ${scriptName} 异常退出，code=${code}, signal=${String(signal || '')}`);
      dialog.showErrorBox('服务异常退出', `${scriptName} 退出码: ${code}`);
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

  throw new Error(`等待服务超时: ${url}`);
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
      console.error('[electron] 停止子进程失败:', error);
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
    spawnScript('dev:backend');
    spawnScript('dev:frontend');
    await waitForUrl(BACKEND_HEALTH_URL, 120000);
    await waitForUrl(FRONTEND_URL, 120000);
    createWindow();
  } catch (error) {
    console.error('[electron] 启动失败:', error);
    dialog.showErrorBox('启动失败', String(error.message || error));
    app.quit();
  }
}

app.whenReady().then(bootstrap).catch((error) => {
  console.error('[electron] 初始化失败:', error);
  dialog.showErrorBox('初始化失败', String(error.message || error));
  app.quit();
});

app.on('window-all-closed', () => {
  cleanupChildren();
  app.quit();
});

app.on('before-quit', () => {
  cleanupChildren();
});
