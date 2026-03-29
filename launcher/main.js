/**
 * main.js — Electron main process.
 * Manages the window, system tray, and FastAPI + voice subprocesses.
 */

const { app, BrowserWindow, ipcMain, Tray, Menu } = require('electron')
const path   = require('path')
const http   = require('http')
const { spawn } = require('child_process')

const isPacked    = app.isPackaged
const apiScript   = isPacked
  ? path.join(process.resourcesPath, 'api', 'main.py')
  : path.join(__dirname, '..', 'api', 'main.py')
const voiceScript = isPacked
  ? path.join(process.resourcesPath, 'voice', 'main.py')
  : path.join(__dirname, '..', 'voice', 'main.py')

let mainWindow   = null
let tray         = null
let apiProcess   = null
let voiceProcess = null

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
function createTray() {
  tray = new Tray(path.join(__dirname, 'assets', 'tray-icon.png'))
  tray.setToolTip('Charles')
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show', click: () => mainWindow.show() },
    { type: 'separator' },
    { label: 'Quit', click: () => { app.isQuiting = true; stopServices(); app.quit() } },
  ]))
  tray.on('double-click', () => mainWindow.show())
}

// ── Health poll ───────────────────────────────────────────────────────────────
function pollHealth(maxAttempts = 15) {
  return new Promise((resolve, reject) => {
    let attempts = 0
    const check = () => {
      attempts++
      if (attempts > maxAttempts) { reject(new Error(`API did not start after ${maxAttempts * 2}s`)); return }
      const req = http.get('http://localhost:8000/health', (res) => {
        res.resume()
        if (res.statusCode === 200) resolve(); else setTimeout(check, 2000)
      })
      req.on('error', () => setTimeout(check, 2000))
      req.end()
    }
    setTimeout(check, 1000)
  })
}

// ── Service lifecycle ─────────────────────────────────────────────────────────
async function startServices() {
  mainWindow.webContents.send('status-update', { state: 'starting' })

  apiProcess = spawn('python', [apiScript], {
    env: { ...process.env },
    stdio: ['ignore', 'ignore', 'pipe'],
  })
  apiProcess.stderr.on('data', (d) => process.stderr.write(`[API] ${d}`))
  apiProcess.on('exit', (code) => {
    if (code !== 0 && code !== null && apiProcess !== null) {
      mainWindow?.webContents.send('status-update', { state: 'error', message: `API exited (${code})` })
      apiProcess = null
    }
  })

  try { await pollHealth() }
  catch (err) {
    apiProcess?.kill(); apiProcess = null
    mainWindow.webContents.send('status-update', { state: 'error', message: err.message })
    throw err
  }

  voiceProcess = spawn('python', [voiceScript, '--no-preload'], {
    env: { ...process.env },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  voiceProcess.stdout.on('data', (d) => {
    for (const line of d.toString().split('\n')) {
      const t = line.trim()
      if (t.startsWith('VOICE_STATE:')) {
        mainWindow?.webContents.send('voice-state-update', { state: t.replace('VOICE_STATE:', '').toLowerCase() })
      }
    }
  })
  voiceProcess.on('exit', (code) => {
    if (code !== 0 && code !== null && voiceProcess !== null) {
      mainWindow?.webContents.send('status-update', { state: 'error', message: 'Voice service crashed' })
      voiceProcess = null
    }
  })

  mainWindow.webContents.send('status-update', { state: 'running' })
}

function stopServices() {
  if (voiceProcess) { voiceProcess.kill(); voiceProcess = null }
  if (apiProcess)   { apiProcess.kill();   apiProcess   = null }
  mainWindow?.webContents.send('status-update', { state: 'stopped' })
}

// ── IPC ───────────────────────────────────────────────────────────────────────
function registerIPC() {
  ipcMain.handle('start-services',  async () => {
    try { await startServices(); return { ok: true } }
    catch (err) { return { ok: false, error: err.message } }
  })
  ipcMain.handle('stop-services',  () => { stopServices(); return { ok: true } })
  ipcMain.handle('minimize-window', () => mainWindow.minimize())
  ipcMain.handle('close-window',    () => mainWindow.close())  // triggers hide-to-tray handler
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(() => { createWindow(); createTray(); registerIPC() })
app.on('before-quit', () => stopServices())
app.on('window-all-closed', (e) => e.preventDefault())
