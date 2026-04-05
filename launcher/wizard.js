/**
 * wizard.js — First-run setup wizard (BrowserWindow + IPC handlers).
 *
 * Walks the user through:
 *   1. Python version check
 *   2. pip dependency install (api + voice requirements)
 *   3. Connect OpenRouter via OAuth + enter Picovoice key
 *   4. Writing .env and marking setup complete
 *
 * All IPC handlers are removed after finish() so they cannot
 * interfere with the main window's IPC after setup.
 */

const { BrowserWindow, ipcMain, app, shell } = require('electron')
const path    = require('path')
const fs      = require('fs')
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
    proc.stderr.on('data', d => { out += d })
    proc.on('error', () => resolve({ ok: false, error: 'Python not found. Download it from python.org.' }))
    proc.on('exit', (code) => {
      if (code !== 0) return resolve({ ok: false, error: 'Python not found. Download it from python.org.' })
      const match = out.trim().match(/Python (\d+)\.(\d+)\.(\d+)/)
      if (!match) return resolve({ ok: false, error: `Unexpected output: ${out.trim()}` })
      const [, major, minor, patch] = match.map(Number)
      const version = `${major}.${minor}.${patch}`
      if (major < 3 || (major === 3 && minor < 10)) {
        return resolve({ ok: false, version, error: `Python ${version} found but 3.10–3.12 is required.` })
      }
      if (major > 3 || (major === 3 && minor > 12)) {
        return resolve({
          ok: false, version,
          error: `Python ${version} is not yet supported. Please install Python 3.11 or 3.12 from python.org.`,
        })
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
      send('\n⚠  Installing voice dependencies — torch (~2 GB) will download on first run.\n    This step can take several minutes on a slow connection. Please wait…\n')
      await runPip('Installing voice dependencies…', path.join(projectRoot, 'voice', 'requirements.txt'))
      send('\n✓  All dependencies installed successfully.\n')
      return { ok: true }
    } catch (err) {
      send(`\n✗  Error: ${err.message}\n`)
      return { ok: false, error: err.message }
    }
  })

  // ── Step 3b: validate Picovoice key ───────────────────────────────────────
  ipcMain.handle('wizard:validate-picovoice', async (_, { picovoiceKey }) => {
    return validatePicovoiceKey(picovoiceKey)
  })

  // ── Step 3c: save keys to .env ────────────────────────────────────────────
  ipcMain.handle('wizard:save-keys', (_, { openrouterKey, picovoiceKey, virustotalKey }) => {
    const envPath = path.join(projectRoot, '.env')
    let content = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : ''

    const upsert = (src, key, value) => {
      const re = new RegExp(`^${key}=.*$`, 'm')
      const line = `${key}=${value}`
      return re.test(src) ? src.replace(re, line) : `${src}\n${line}`
    }

    content = upsert(content, 'OPENROUTER_API_KEY',   openrouterKey)
    content = upsert(content, 'PICOVOICE_ACCESS_KEY',  picovoiceKey)
    // Only write VirusTotal key if the user provided one
    if (virustotalKey) {
      content = upsert(content, 'VIRUSTOTAL_API_KEY', virustotalKey)
    }
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

  ipcMain.handle('wizard:close', () => { app.quit() })

  // Utility: open a URL in the system browser from renderer code
  ipcMain.handle('wizard:open-external', (_, url) => {
    const allowed = [
      'https://console.picovoice.ai/',
      'https://openrouter.ai/keys',
      'https://www.virustotal.com/gui/sign-in',
    ]
    if (allowed.some(prefix => url.startsWith(prefix))) shell.openExternal(url)
  })
}

function _removeHandlers() {
  for (const ch of ['wizard:check-python', 'wizard:install-deps',
                     'wizard:validate-picovoice',
                     'wizard:save-keys', 'wizard:finish', 'wizard:close',
                     'wizard:open-external']) {
    ipcMain.removeHandler(ch)
  }
}

// ── Picovoice key validation ──────────────────────────────────────────────────
//
// Called when the user enters their Picovoice access key.
// The key is needed at runtime for the pvporcupine SDK licence check
// (even though the .ppn wake word model files are already in the repo).
//
// Parameters
// ----------
// picovoiceKey  — string entered by the user
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
//   Option A — format check only (fast, ~0ms):
//     Picovoice keys are long base64 strings, typically 128–512 chars.
//     Reject if empty or clearly too short, accept otherwise.
//     Downside: a valid-looking but revoked key won't be caught until
//     the user tries to use voice features.
//
//   Option B — live SDK check (slow, ~3s):
//     Spawn: python -c "import pvporcupine; pvporcupine.create(access_key='<key>').delete()"
//     Exit code 0 = key is valid and the SDK accepted it.
//     Downside: requires pvporcupine to already be installed (it will be,
//     since this runs after Step 2), and adds a few seconds of wait time.
//
async function validatePicovoiceKey(picovoiceKey) {
  if (!picovoiceKey || !picovoiceKey.trim()) {
    return { ok: false, error: 'Picovoice key cannot be empty.' }
  }

  return new Promise((resolve) => {
    // Key is passed via environment variable — never injected into the script
    // string — so quotes or special characters in the key can't break anything.
    const script = [
      'import pvporcupine, os',
      'pv = pvporcupine.create(access_key=os.environ["PV_KEY"], keywords=["porcupine"])',
      'pv.delete()',
    ].join('; ')

    const proc = spawn('python', ['-c', script], {
      stdio: ['ignore', 'ignore', 'pipe'],
      env: { ...process.env, PV_KEY: picovoiceKey },
    })

    let stderr = ''
    proc.stderr.on('data', d => { stderr += d })

    // 10-second timeout — SDK init should be near-instant
    const timer = setTimeout(() => {
      proc.kill()
      resolve({ ok: false, error: 'Validation timed out. Check your internet connection.' })
    }, 10_000)

    proc.on('exit', (code) => {
      clearTimeout(timer)
      if (code === 0) {
        resolve({ ok: true })
      } else {
        // pvporcupine prints a descriptive error to stderr — surface it
        const hint = stderr.includes('invalid') || stderr.includes('Invalid')
          ? 'Key not recognised — double-check at console.picovoice.ai'
          : 'Picovoice validation failed — check your key and internet connection.'
        resolve({ ok: false, error: hint })
      }
    })

    proc.on('error', () => {
      clearTimeout(timer)
      resolve({ ok: false, error: 'Could not run Python to validate key.' })
    })
  })
}

// ── Exports ───────────────────────────────────────────────────────────────────

module.exports = { createWizardWindow, setupFlagPath }
