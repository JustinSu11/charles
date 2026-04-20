<#
.SYNOPSIS
    One-time developer setup: downloads Python 3.11 Windows embeddable package,
    bootstraps pip, installs all API and voice dependencies, and places the result
    in resources/python/ for electron-builder to bundle.

.DESCRIPTION
    Run this script once before building the Windows installer with `npm run dist`.
    The resulting resources/python/ directory is gitignored (binary/large) but gets
    bundled into the installer via the extraResources field in launcher/package.json.

    After this runs, the packaged Charles installer works on a fresh Windows OS
    without requiring the user to pre-install Python or any dependencies.

    Expected output size: ~1.5 GB (dominated by torch CPU wheels for Whisper STT).

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File scripts/setup-embedded-python.ps1
#>

$ErrorActionPreference = "Stop"

$version = "3.11.9"
$zipUrl  = "https://www.python.org/ftp/python/$version/python-$version-embed-amd64.zip"
$dest    = Join-Path $PSScriptRoot "..\resources\python"
$dest    = [System.IO.Path]::GetFullPath($dest)
$zipFile = Join-Path $PSScriptRoot "py-embed.zip"

Write-Host "Charles — Embedded Python Setup" -ForegroundColor Cyan
Write-Host "Target: $dest"
Write-Host ""

# Clean up any prior run
if (Test-Path $dest) {
    Write-Host "Removing existing $dest ..."
    Remove-Item $dest -Recurse -Force
}

# ── 1. Download ────────────────────────────────────────────────────────────────
Write-Host "Downloading Python $version embeddable package..." -ForegroundColor Yellow
Invoke-WebRequest $zipUrl -OutFile $zipFile -UseBasicParsing
Write-Host "Downloaded." -ForegroundColor Green

# ── 2. Extract ────────────────────────────────────────────────────────────────
Write-Host "Extracting..." -ForegroundColor Yellow
Expand-Archive $zipFile -DestinationPath $dest -Force
Remove-Item $zipFile
Write-Host "Extracted to $dest" -ForegroundColor Green

# ── 3. Enable site-packages (uncomment '#import site' in python311._pth) ─────
$pthFile = Join-Path $dest "python311._pth"
if (Test-Path $pthFile) {
    Write-Host "Enabling site-packages in python311._pth ..." -ForegroundColor Yellow
    $pthContent = Get-Content $pthFile -Raw
    $pthContent = $pthContent -replace "#import site", "import site"
    Set-Content $pthFile $pthContent -NoNewline
    Write-Host "Done." -ForegroundColor Green
} else {
    Write-Warning "python311._pth not found — site-packages may not be on sys.path."
}

# ── 4. Bootstrap pip ──────────────────────────────────────────────────────────
$pythonExe = Join-Path $dest "python.exe"
$getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$getPipFile = Join-Path $dest "get-pip.py"

Write-Host "Bootstrapping pip..." -ForegroundColor Yellow
Invoke-WebRequest $getPipUrl -OutFile $getPipFile -UseBasicParsing
& $pythonExe $getPipFile --quiet
Remove-Item $getPipFile
Write-Host "pip installed." -ForegroundColor Green

# ── 5. Install API dependencies ───────────────────────────────────────────────
$apiReqs = Join-Path $PSScriptRoot "..\api\requirements.txt"
$apiReqs = [System.IO.Path]::GetFullPath($apiReqs)
Write-Host "Installing API dependencies from $apiReqs ..." -ForegroundColor Yellow
& $pythonExe -m pip install `
    --requirement $apiReqs `
    --quiet `
    --no-warn-script-location
Write-Host "API dependencies installed." -ForegroundColor Green

# ── 6. Install voice dependencies ────────────────────────────────────────────
$voiceReqs = Join-Path $PSScriptRoot "..\voice\requirements.txt"
$voiceReqs = [System.IO.Path]::GetFullPath($voiceReqs)
Write-Host "Installing voice dependencies from $voiceReqs ..." -ForegroundColor Yellow
Write-Host "(This will take several minutes — torch CPU wheels are ~700 MB)" -ForegroundColor DarkYellow

# Install torch CPU-only first to avoid pulling in large CUDA builds.
# The +cpu variant is a PyTorch index extra that selects the CPU-only wheel.
& $pythonExe -m pip install `
    torch torchaudio `
    --index-url https://download.pytorch.org/whl/cpu `
    --quiet `
    --no-warn-script-location

# Install the rest of the voice requirements.
# torch/torchaudio are already satisfied by the CPU build above — pip will
# skip them because the installed version meets the >= constraint.
& $pythonExe -m pip install `
    --requirement $voiceReqs `
    --quiet `
    --no-warn-script-location

Write-Host "Voice dependencies installed." -ForegroundColor Green

# ── 7. Verify ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Verifying..." -ForegroundColor Yellow
$pyVer = & $pythonExe --version
$pipVer = & $pythonExe -m pip --version
Write-Host "  Python : $pyVer" -ForegroundColor Green
Write-Host "  pip    : $pipVer" -ForegroundColor Green

# Smoke-test key imports
Write-Host "  Smoke-testing imports..." -ForegroundColor Yellow
$imports = @("fastapi", "uvicorn", "sqlalchemy", "openwakeword", "whisper", "pyaudio", "edge_tts", "miniaudio")
foreach ($mod in $imports) {
    $result = & $pythonExe -c "import $mod; print('ok')" 2>&1
    if ($result -eq "ok") {
        Write-Host "    $mod : ok" -ForegroundColor Green
    } else {
        Write-Warning "    $mod : FAILED — $result"
    }
}

Write-Host ""
Write-Host "Embedded Python ready at:" -ForegroundColor Cyan
Write-Host "  $dest"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  cd launcher"
Write-Host "  npm run dist"
Write-Host ""
Write-Host "This will produce: launcher/dist/Charles Setup 1.0.0.exe" -ForegroundColor Green
