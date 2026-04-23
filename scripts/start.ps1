$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$systemPython = (Get-Command python -ErrorAction SilentlyContinue)

if (Test-Path $bundledPython) {
  $python = $bundledPython
} elseif ($systemPython) {
  $python = $systemPython.Source
} else {
  throw "No Python runtime found. Install Python or use the Codex bundled runtime."
}

& $python (Join-Path $root "run_server.py")

