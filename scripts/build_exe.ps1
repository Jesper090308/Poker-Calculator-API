$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$systemPython = Get-Command python -ErrorAction SilentlyContinue

if (Test-Path $bundledPython) {
  $python = $bundledPython
} elseif ($systemPython) {
  $python = $systemPython.Source
} else {
  throw "No Python runtime found. Install Python or use the Codex bundled runtime."
}

Push-Location $root
try {
  $specPath = Join-Path $root "build\spec"
  $workPath = Join-Path $root "build\pyinstaller"
  $distPath = Join-Path $root "dist"
  $templatesPath = Join-Path $root "app\templates"
  $staticPath = Join-Path $root "app\static"

  function Invoke-PythonStep {
    param([string[]]$Arguments)

    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
      throw "Python command failed with exit code $LASTEXITCODE."
    }
  }

  Invoke-PythonStep -Arguments @(
    "-m", "pip", "install",
    "-r", ".\requirements-local.txt",
    "-r", ".\requirements-build.txt"
  )

  Invoke-PythonStep -Arguments @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--name", "Pokerbot",
    "--console",
    "--onefile",
    "--specpath", $specPath,
    "--workpath", $workPath,
    "--distpath", $distPath,
    "--paths", $root,
    "--add-data", "$templatesPath;app\templates",
    "--add-data", "$staticPath;app\static",
    "--collect-submodules", "uvicorn",
    "--collect-submodules", "starlette",
    "--collect-submodules", "anyio",
    ".\launch_pokerbot.py"
  )

  Write-Host ""
  Write-Host "Build complete:"
  Write-Host (Join-Path $root "dist\Pokerbot.exe")
} finally {
  Pop-Location
}
