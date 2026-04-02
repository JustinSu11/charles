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
const http    = require('http')
const https   = require('https')
const crypto  = require('crypto')
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

  // ── Step 3a: OpenRouter OAuth (PKCE) ──────────────────────────────────────
  //
  // Flow:
  //   1. Generate a random PKCE verifier + SHA-256 challenge
  //   2. Start a temporary localhost server to catch the redirect
  //   3. Open the system browser to OpenRouter's auth page
  //   4. Wait for the redirect (2-minute timeout)
  //   5. Exchange the auth code for an API key
  //   6. Return the key to the renderer — it is saved to .env on Next click
  //
  ipcMain.handle('wizard:start-openrouter-oauth', async () => {
    // 1. PKCE
    const verifier  = crypto.randomBytes(32).toString('base64url')
    const challenge = crypto.createHash('sha256').update(verifier).digest('base64url')

    // 2. Local redirect server on a random available port
    let resolveCode, rejectCode
    const codePromise = new Promise((res, rej) => { resolveCode = res; rejectCode = rej })

    const server = http.createServer((req, res) => {
      const url  = new URL(req.url, 'http://localhost')
      const code = url.searchParams.get('code')
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
      res.end(`<!DOCTYPE html><html><body style="font-family:sans-serif;
        background:#0d0d0d;color:#e8e8e8;display:flex;align-items:center;
        justify-content:center;height:100vh;margin:0;text-align:center">
        <div><div style="font-size:3rem">✅</div>
        <h2>Connected! You can close this tab.</h2></div></body></html>`)
      server.close()
      if (code) resolveCode(code)
      else rejectCode(new Error('No authorization code in redirect'))
    })

    await new Promise((res, rej) => server.listen(0, '127.0.0.1', res).on('error', rej))
    const port = server.address().port

    // 3. Open browser
    const callbackUrl = `http://127.0.0.1:${port}`
    const authUrl = `https://openrouter.ai/auth?callback_url=${encodeURIComponent(callbackUrl)}`
      + `&code_challenge=${challenge}&code_challenge_method=S256`
    shell.openExternal(authUrl)

    // 4. Wait for redirect (2-minute timeout)
    const timer = setTimeout(() => {
      server.close()
      rejectCode(new Error('Authentication timed out. Please try again.'))
    }, 120_000)

    try {
      const code = await codePromise
      clearTimeout(timer)

      // 5. Exchange code → API key
      const key = await _exchangeCodeForKey(code, verifier)
      return { ok: true, key }
    } catch (err) {
      clearTimeout(timer)
      server.close()
      return { ok: false, error: err.message }
    }
  })

  // ── Step 3b: validate Picovoice key ───────────────────────────────────────
  ipcMain.handle('wizard:validate-picovoice', async (_, { picovoiceKey }) => {
    return validatePicovoiceKey(picovoiceKey)
  })

  // ── Step 3c: save both keys to .env ───────────────────────────────────────
  ipcMain.handle('wizard:save-keys', (_, { openrouterKey, picovoiceKey }) => {
    const envPath = path.join(projectRoot, '.env')
    let content = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : ''

    const upsert = (src, key, value) => {
      const re = new RegExp(`^${key}=.*$`, 'm')
      const line = `${key}=${value}`
      return re.test(src) ? src.replace(re, line) : `${src}\n${line}`
    }

    content = upsert(content, 'OPENROUTER_API_KEY',  openrouterKey)
    content = upsert(content, 'PICOVOICE_ACCESS_KEY', picovoiceKey)
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
}

function _removeHandlers() {
  for (const ch of ['wizard:check-python', 'wizard:install-deps',
                     'wizard:start-openrouter-oauth', 'wizard:validate-picovoice',
                     'wizard:save-keys', 'wizard:finish', 'wizard:close']) {
    ipcMain.removeHandler(ch)
  }
}

// ── OpenRouter code → key exchange ────────────────────────────────────────────

function _exchangeCodeForKey(code, verifier) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ code, code_verifier: verifier })
    const req  = https.request({
      hostname: 'openrouter.ai',
      path:     '/api/v1/auth/keys',
      method:   'POST',
      headers:  {
        'Content-Type':   'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    }, (res) => {
      let data = ''
      res.on('data', d => { data += d })
      res.on('end', () => {
        try {
          const json = JSON.parse(data)
          if (json.key) resolve(json.key)
          else reject(new Error(json.error || 'OpenRouter did not return a key'))
        } catch {
          reject(new Error('Invalid response from OpenRouter'))
        }
      })
    })
    req.on('error', reject)
    req.write(body)
    req.end()
  })
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
  // Replace this placeholder with your implementation
  return { ok: true }
}

// ── Exports ───────────────────────────────────────────────────────────────────

module.exports = { createWizardWindow, setupFlagPath }
