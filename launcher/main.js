/**
 * main.js — Electron main process.
 * Manages the window, system tray, and FastAPI + voice subprocesses.
 *
 * Lifecycle:
 *   App opens → API starts automatically → text chat enabled ("ready")
 *   Start button → voice wake-word service starts ("voice-active")
 *   Stop button  → voice service stops, text chat stays enabled ("ready")
 *   Quit         → both subprocesses killed
 */

const { app, BrowserWindow, ipcMain, nativeImage, Tray, Menu } = require('electron')
const { autoUpdater } = require('electron-updater')
const path   = require('path')
const fs     = require('fs')
const http   = require('http')
const { spawn } = require('child_process')
const { createWizardWindow, setupFlagPath } = require('./wizard')

// ── Auto-updater ──────────────────────────────────────────────────────────────
// Check GitHub Releases silently on launch. If a new version is available,
// it downloads in the background and we notify the renderer to show a banner.
function setupAutoUpdater() {
  autoUpdater.autoDownload    = true   // download silently in background
  autoUpdater.autoInstallOnAppQuit = false // we control when to install

  autoUpdater.on('update-available', () => {
    mainWindow?.webContents.send('update-status', { state: 'downloading' })
  })

  autoUpdater.on('update-downloaded', () => {
    mainWindow?.webContents.send('update-status', { state: 'ready' })
  })

  // Only check for updates in the packaged app — not during development
  if (isPacked) autoUpdater.checkForUpdates()
}

const isPacked    = app.isPackaged
const apiScript   = isPacked
  ? path.join(process.resourcesPath, 'api', 'main.py')
  : path.join(__dirname, '..', 'api', 'main.py')
const voiceScript = isPacked
  ? path.join(process.resourcesPath, 'voice', 'main.py')
  : path.join(__dirname, '..', 'voice', 'main.py')

// Use bundled Python 3.11 in the packaged app (no system Python required).
// Falls back to bare 'python' in dev so devs can use their own environment.
const pythonExe = isPacked
  ? path.join(process.resourcesPath, 'python', 'python.exe')
  : 'python'

let mainWindow   = null
let tray         = null
let apiProcess   = null
let voiceProcess = null
let isVoiceStarting = false

// ── Window ────────────────────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 900, height: 700, minWidth: 600, minHeight: 400,
    frame: false,
    backgroundColor: '#0d0d0d',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'))
  mainWindow.on('close', (e) => {
    if (!app.isQuiting) { e.preventDefault(); mainWindow.hide() }
  })
}

// ── Tray ──────────────────────────────────────────────────────────────────────
function makeTrayIcon() {
  const size = 16
  const buf  = Buffer.alloc(size * size * 4)
  for (let i = 0; i < size * size; i++) {
    buf[i * 4 + 0] = 59;  buf[i * 4 + 1] = 130
    buf[i * 4 + 2] = 246; buf[i * 4 + 3] = 255
  }
  return nativeImage.createFromBuffer(buf, { width: size, height: size })
}

function createTray() {
  tray = new Tray(makeTrayIcon())
  tray.setToolTip('Charles')
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show', click: () => mainWindow?.show() },
    { type: 'separator' },
    {
      label: 'Re-run Setup…',
      click: () => {
        // Delete the setup flag so the wizard opens on next launch,
        // then restart the app so the change takes effect.
        try { fs.unlinkSync(setupFlagPath) } catch {}
        app.isQuiting = true
        stopAll()
        app.relaunch()
        app.quit()
      },
    },
    { type: 'separator' },
    { label: 'Quit', click: () => { app.isQuiting = true; stopAll(); app.quit() } },
  ]))
  tray.on('double-click', () => mainWindow?.show())
}

// ── Health poll ───────────────────────────────────────────────────────────────
function pollHealth(maxAttempts = 15) {
  return new Promise((resolve, reject) => {
    let attempts = 0
    const check = () => {
      attempts++
      if (attempts > maxAttempts) { reject(new Error(`API did not start after ${maxAttempts * 2}s`)); return }
      const req = http.get('http://127.0.0.1:8000/health', (res) => {
        res.resume()
        if (res.statusCode === 200) resolve(); else setTimeout(check, 2000)
      })
      req.on('error', () => setTimeout(check, 2000))
      req.end()
    }
    setTimeout(check, 1000)
  })
}

// ── Port cleanup ──────────────────────────────────────────────────────────────
// Kill any process already bound to a given port (Windows only).
// Prevents EADDRINUSE when Charles is restarted without a full quit.
function killPortSync(port) {
  try {
    const { execSync } = require('child_process')
    // netstat output: "  TCP  127.0.0.1:8000  ...  <pid>"
    const out = execSync(`netstat -ano -p tcp`, { timeout: 3000 }).toString()
    const re  = new RegExp(`[\\s:]${port}\\s+\\S+\\s+LISTENING\\s+(\\d+)`, 'i')
    const match = out.match(re)
    if (match) {
      const pid = parseInt(match[1], 10)
      try { execSync(`taskkill /PID ${pid} /F`, { timeout: 3000 }) } catch {}
    }
  } catch {}
}

// ── API lifecycle (automatic) ─────────────────────────────────────────────────
async function startApi() {
  // Kill any leftover API process (e.g. from a previous instance that hid to tray)
  if (apiProcess) { try { apiProcess.kill() } catch {} ; apiProcess = null }
  // Kill any orphan process from a prior crash that's still holding the port
  killPortSync(8000)

  mainWindow?.webContents.send('status-update', { state: 'initializing' })

  const proc = spawn(pythonExe, [apiScript], {
    env: { ...process.env, CHARLES_DATA_DIR: app.getPath('userData') },
    stdio: ['ignore', 'ignore', 'pipe'],
  })
  apiProcess = proc
  proc.stderr.on('data', (d) => process.stderr.write(`[API] ${d}`))
  proc.on('error', (err) => {
    if (apiProcess === proc) {
      mainWindow?.webContents.send('status-update', { state: 'error', message: `Failed to start API: ${err.message}` })
      apiProcess = null
    }
  })
  proc.on('exit', (code) => {
    if (code !== 0 && code !== null && apiProcess === proc) {
      mainWindow?.webContents.send('status-update', { state: 'error', message: `API exited (${code})` })
      apiProcess = null
    }
  })

  try {
    await pollHealth()
    mainWindow?.webContents.send('status-update', { state: 'ready' })
  } catch (err) {
    apiProcess?.kill(); apiProcess = null
    mainWindow?.webContents.send('status-update', { state: 'error', message: err.message })
  }
}

// ── Voice lifecycle (user-controlled) ────────────────────────────────────────
async function startVoice() {
  if (isVoiceStarting || voiceProcess) return
  isVoiceStarting = true
  try {
    if (voiceProcess) { voiceProcess.kill(); voiceProcess = null }

    const vproc = spawn(pythonExe, [voiceScript], {
      env: { ...process.env, CHARLES_DATA_DIR: app.getPath('userData') },
      stdio: ['pipe', 'pipe', 'pipe'],  // stdin piped so we can send INTERRUPT
    })
    voiceProcess = vproc

    // In the packaged app stderr isn't visible — tee it to a log file in userData
    // so crashes can be diagnosed. File is overwritten each start attempt.
    const voiceLogPath = path.join(app.getPath('userData'), 'voice-error.log')
    const voiceLog = fs.createWriteStream(voiceLogPath, { flags: 'w' })
    vproc.stderr.on('data', (d) => {
      process.stderr.write(`[Voice] ${d}`)
      voiceLog.write(d)
    })
    vproc.on('exit', () => voiceLog.end())
    vproc.stdout.on('data', (d) => {
      for (const line of d.toString().split('\n')) {
        const t = line.trim()
        if (t.startsWith('VOICE_STATE:')) {
          mainWindow?.webContents.send('voice-state-update', { state: t.replace('VOICE_STATE:', '').toLowerCase() })
        } else if (t.startsWith('VOICE_TRANSCRIPT:')) {
          const text = t.slice('VOICE_TRANSCRIPT:'.length)
          mainWindow?.webContents.send('voice-transcript', { text })
        } else if (t.startsWith('VOICE_DEBUG:')) {
          const payload = {}
          for (const pair of t.slice('VOICE_DEBUG:'.length).split(',')) {
            const [k, v] = pair.split('=')
            if (k && v !== undefined) payload[k] = parseFloat(v)
          }
          mainWindow?.webContents.send('voice-debug', payload)
        }
      }
    })
    vproc.on('error', () => {
      if (voiceProcess === vproc) {
        mainWindow?.webContents.send('voice-state-update', { state: 'error' })
        voiceProcess = null
      }
    })
    vproc.on('exit', (code) => {
      if (voiceProcess === vproc) {
        // On error exit: show voice error badge
        if (code !== 0 && code !== null) {
          mainWindow?.webContents.send('voice-state-update', { state: 'error' })
        }
        // Always transition back to ready — covers clean exits (stop command)
        // and error exits alike so the Stop button and voice pill always reset.
        mainWindow?.webContents.send('status-update', { state: 'ready' })
        voiceProcess = null
      }
    })

    mainWindow?.webContents.send('status-update', { state: 'voice-active' })
  } finally {
    isVoiceStarting = false
  }
}

function stopVoice() {
  if (voiceProcess) { voiceProcess.kill(); voiceProcess = null }
  mainWindow?.webContents.send('status-update', { state: 'ready' })
}

function stopAll() {
  if (voiceProcess) { voiceProcess.kill(); voiceProcess = null }
  if (apiProcess)   { apiProcess.kill();   apiProcess   = null }
}

// ── IPC ───────────────────────────────────────────────────────────────────────
function registerIPC() {
  ipcMain.handle('start-services',  async () => {
    try { await startVoice(); return { ok: true } }
    catch (err) { return { ok: false, error: err.message } }
  })
  ipcMain.handle('stop-services',    () => { stopVoice(); return { ok: true } })
  ipcMain.handle('interrupt-voice',  () => {
    if (voiceProcess?.stdin?.writable) {
      voiceProcess.stdin.write('INTERRUPT\n')
    }
    return { ok: true }
  })
  ipcMain.handle('minimize-window',  () => mainWindow?.minimize())
  ipcMain.handle('close-window',     () => mainWindow?.close())
  ipcMain.handle('quit-app',         () => { app.isQuiting = true; stopAll(); app.quit() })
  ipcMain.handle('install-update',   () => { stopAll(); autoUpdater.quitAndInstall() })

  // In the packaged app, resources/ is read-only — store .env in userData instead.
  const envPath = path.join(app.getPath('userData'), '.env')

  ipcMain.handle('settings:get-keys', () => {
    const content = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : ''
    const getVal = (key) => {
      const match = content.match(new RegExp(`^${key}=(.*)$`, 'm'))
      return match ? match[1].trim() : ''
    }
    return {
      openrouterKey: getVal('OPENROUTER_API_KEY'),
      virustotalKey: getVal('VIRUSTOTAL_API_KEY'),
    }
  })

  ipcMain.handle('settings:save-keys', async (_, { openrouterKey, virustotalKey }) => {
    let content = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : ''
    const upsert = (src, key, value) => {
      const re = new RegExp(`^${key}=.*$`, 'm')
      const line = `${key}=${value}`
      return re.test(src) ? src.replace(re, line) : `${src}\n${line}`
    }
    if (openrouterKey) content = upsert(content, 'OPENROUTER_API_KEY', openrouterKey)
    if (virustotalKey !== undefined) content = upsert(content, 'VIRUSTOTAL_API_KEY', virustotalKey)
    fs.writeFileSync(envPath, content.trim() + '\n', 'utf8')
    await startApi()
    return { ok: true }
  })
}

// ── App lifecycle ─────────────────────────────────────────────────────────────

function launchMain() {
  createWindow()
  createTray()
  registerIPC()
  // Defer startApi and update check until the renderer has finished loading
  // so IPC events aren't dropped before listeners are registered.
  mainWindow.webContents.once('did-finish-load', () => {
    startApi()
    setupAutoUpdater()
  })
}

// Prevent multiple instances — if a second instance is launched, focus
// the existing window instead of starting a new one.
if (!app.requestSingleInstanceLock()) {
  app.quit()
}
app.on('second-instance', () => { mainWindow?.show(); mainWindow?.focus() })

app.whenReady().then(() => {
  if (fs.existsSync(setupFlagPath)) {
    launchMain()
  } else {
    createWizardWindow({ onComplete: launchMain })
  }
})
app.on('before-quit', () => stopAll())
app.on('window-all-closed', (e) => e.preventDefault())
