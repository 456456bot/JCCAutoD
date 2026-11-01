param([switch]$SkipShortcuts)

$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Install 64-bit Python 3.12 or newer with the Windows Python launcher first.'
}
& py -3 -c "import struct,sys; assert sys.version_info >= (3,12) and struct.calcsize('P') == 8, '64-bit Python 3.12+ required'"
if ($LASTEXITCODE -ne 0) { throw 'Python version or architecture is not supported.' }

$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & py -3 -m venv (Join-Path $projectPath '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $pythonPath -m pip install -r (Join-Path $projectPath 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the network and retry.' }

if (-not $SkipShortcuts) {
    & (Join-Path $PSScriptRoot 'install-shortcuts.ps1')
}
Write-Host 'Setup complete. Start the lineup tool to download portrait resources, then start the shop assistant.'
