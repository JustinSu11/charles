<#
.SYNOPSIS
    One-time developer setup: downloads Python 3.11 Windows embeddable package,
    bootstraps pip, and places it in resources/python/ for electron-builder to bundle.

.DESCRIPTION
    Run this script once before building the Windows installer with `npm run dist`.
    The resulting resources/python/ directory is gitignored (binary/large) but gets
    bundled into the installer via the extraResources field in launcher/package.json.

    After this runs, the packaged Charles installer works on a fresh Windows OS
    without requiring the user to pre-install Python.

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

# ── 5. Verify ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Verifying..." -ForegroundColor Yellow
$pyVer = & $pythonExe --version
$pipVer = & $pythonExe -m pip --version
Write-Host "  Python : $pyVer" -ForegroundColor Green
Write-Host "  pip    : $pipVer" -ForegroundColor Green
Write-Host ""
Write-Host "Embedded Python ready at:" -ForegroundColor Cyan
Write-Host "  $dest"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  cd launcher"
Write-Host "  npm run dist"
Write-Host ""
Write-Host "This will produce: launcher/dist/Charles Setup 1.0.0.exe" -ForegroundColor Green
