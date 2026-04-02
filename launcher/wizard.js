/**
 * wizard.js — First-run setup wizard (BrowserWindow + IPC handlers).
 *
 * Called by main.js when no setup_complete flag exists.
 * Walks the user through:
 *   1. Python version check
 *   2. pip dependency install (api + voice requirements)
 *   3. API key entry + validation
 *   4. Writing .env and marking setup complete
 *
 * All IPC handlers are removed after finish() so they cannot
 * interfere with the main window's IPC after setup.
 */

const { BrowserWindow, ipcMain, app } = require('electron')
const path    = require('path')
const fs      = require('fs')
const https   = require('https')
const { spawn } = require('child_process')

// ── Paths ─────────────────────────────────────────────────────────────────────

const projectRoot   = path.join(__dirname, '..')
const setupFlagPath = path.join(app.getPath('userData'), 'setup_complete')

// ── Window ────────────────────────────────────────────────────────────────────

let wizardWindow = null

function createWizardWindow({ onComplete }) {
  wizardWindow = new BrowserWindow({
    width: 700, height: 540,
    frame: false,
    resizable: false,
    backgroundColor: '#0d0d0d',
    webPreferences: {
      preload: path.join(__dirname, 'preload-wizard.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  wizardWindow.loadFile(path.join(__dirname, 'renderer', 'wizard.html'))

  _registerHandlers(onComplete)
}

// ── IPC handlers ──────────────────────────────────────────────────────────────

function _registerHandlers(onComplete) {

  // ── Step 1: Python check ──────────────────────────────────────────────────
  ipcMain.handle('wizard:check-python', () => new Promise((resolve) => {
    const proc = spawn('python', ['--version'], { stdio: ['ignore', 'pipe', 'pipe'] })
    let out = ''
    proc.stdout.on('data', d => { out += d })
    proc.stderr.on('data', d => { out += d })   // Python 2 prints to stderr
    proc.on('error', () => resolve({ ok: false, error: 'Python not found. Download it from python.org.' }))
    proc.on('exit', (code) => {
      if (code !== 0) return resolve({ ok: false, error: 'Python not found. Download it from python.org.' })
      const match = out.trim().match(/Python (\d+)\.(\d+)\.(\d+)/)
      if (!match) return resolve({ ok: false, error: `Unexpected output: ${out.trim()}` })
      const [, major, minor, patch] = match.map(Number)
      const version = `${major}.${minor}.${patch}`
      if (major < 3 || (major === 3 && minor < 10)) {
        return resolve({ ok: false, version, error: `Python ${version} found but 3.10+ is required.` })
      }
      resolve({ ok: true, version })
    })
  }))

  // ── Step 2: pip install (streams progress events to renderer) ─────────────
  ipcMain.handle('wizard:install-deps', async () => {
    const send = (text) => wizardWindow?.webContents.send('wizard:install-progress', { text })

    const runPip = (label, reqFile) => new Promise((resolve, reject) => {
      send(`\n▶  ${label}\n`)
      const proc = spawn('python', ['-m', 'pip', 'install', '-r', reqFile, '--progress-bar', 'off'], {
        stdio: ['ignore', 'pipe', 'pipe'],
      })
      proc.stdout.on('data', d => send(d.toString()))
      proc.stderr.on('data', d => send(d.toString()))
      proc.on('error', reject)
      proc.on('exit', code => code === 0 ? resolve() : reject(new Error(`pip exited with code ${code}`)))
    })

    try {
      await runPip('Installing API dependencies…',   path.join(projectRoot, 'api',   'requirements.txt'))
      await runPip('Installing voice dependencies…', path.join(projectRoot, 'voice', 'requirements.txt'))
      send('\n✓  All dependencies installed successfully.\n')
      return { ok: true }
    } catch (err) {
      send(`\n✗  Error: ${err.message}\n`)
      return { ok: false, error: err.message }
    }
  })

  // ── Step 3: validate API keys ─────────────────────────────────────────────
  //
  // TODO — implement validateKeys() below.
  // This is called before saving to .env so the user gets feedback
  // immediately if they paste a wrong key.
  //
  ipcMain.handle('wizard:validate-keys', async (_, keys) => {
    return validateKeys(keys)
  })

  // ── Step 3: save keys to .env ─────────────────────────────────────────────
  ipcMain.handle('wizard:save-keys', (_, { openrouterKey, picovoiceKey }) => {
    const envPath = path.join(projectRoot, '.env')
    let content = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : ''

    const upsert = (src, key, value) => {
      const re = new RegExp(`^${key}=.*$`, 'm')
      const line = `${key}=${value}`
      return re.test(src) ? src.replace(re, line) : `${src}\n${line}`
    }

    content = upsert(content, 'OPENROUTER_API_KEY',   openrouterKey)
    content = upsert(content, 'PICOVOICE_ACCESS_KEY',  picovoiceKey)
    fs.writeFileSync(envPath, content.trim() + '\n', 'utf8')
    return { ok: true }
  })

  // ── Step 4: mark setup complete and launch main window ────────────────────
  ipcMain.handle('wizard:finish', () => {
    fs.mkdirSync(path.dirname(setupFlagPath), { recursive: true })
    fs.writeFileSync(setupFlagPath, new Date().toISOString(), 'utf8')

    _removeHandlers()
    wizardWindow?.close()
    wizardWindow = null
    onComplete()
  })

  // Window controls (wizard is frameless)
  ipcMain.handle('wizard:close', () => { app.quit() })
}

function _removeHandlers() {
  for (const ch of ['wizard:check-python', 'wizard:install-deps',
                     'wizard:validate-keys', 'wizard:save-keys',
                     'wizard:finish', 'wizard:close']) {
    ipcMain.removeHandler(ch)
  }
}

// ── Key validation ────────────────────────────────────────────────────────────
//
// Validates both API keys before writing .env.
//
// Parameters
// ----------
// keys.openrouterKey  — the OpenRouter API key entered by the user
// keys.picovoiceKey   — the Picovoice access key entered by the user
//
// Returns
// -------
// { ok: true }
//   or
// { ok: false, error: 'human-readable message shown in the wizard UI' }
//
// TODO: implement this function.
//
// Things to consider:
//   OpenRouter  — GET https://openrouter.ai/api/v1/auth/key with
//                 Authorization: Bearer <key>. Returns 200 if valid,
//                 401 if not. No tokens consumed.
//   Picovoice   — No public REST health-check endpoint. Options:
//                 (a) just verify it's non-empty and ~32 chars
//                 (b) spawn `python -c "import pvporcupine; pvporcupine.create(access_key='...')"
//                     and check exit code (slower but definitive)
//
async function validateKeys({ openrouterKey, picovoiceKey }) {
  // Replace this placeholder with your implementation
  return { ok: true }
}

// ── Exports ───────────────────────────────────────────────────────────────────

module.exports = { createWizardWindow, setupFlagPath }
