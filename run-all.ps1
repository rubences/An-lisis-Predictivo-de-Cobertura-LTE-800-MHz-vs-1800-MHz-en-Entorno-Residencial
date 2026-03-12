param(
  [string]$PythonExe = "python"
)

$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

$candidateInterpreters = @()

if (Test-Path $venvPython) {
  $candidateInterpreters += $venvPython
}

$pythonCommand = Get-Command $PythonExe -ErrorAction SilentlyContinue
if ($pythonCommand) {
  $candidateInterpreters += $pythonCommand.Source
}

$localPythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
if (Test-Path $localPythonRoot) {
  $localPythons = Get-ChildItem -Path $localPythonRoot -Directory |
    Sort-Object Name -Descending |
    ForEach-Object { Join-Path $_.FullName "python.exe" } |
    Where-Object { Test-Path $_ }
  $candidateInterpreters += $localPythons
}

$selectedPython = $null
foreach ($candidate in $candidateInterpreters | Select-Object -Unique) {
  & $candidate -c "import pytest" 2>$null
  if ($LASTEXITCODE -eq 0) {
    $selectedPython = $candidate
    break
  }
}

if (-not $selectedPython) {
  Write-Host "No se encontró un intérprete Python con pytest instalado." -ForegroundColor Red
  Write-Host "Instala pytest o ejecuta: .\run-all.ps1 -PythonExe <ruta_python.exe>" -ForegroundColor Yellow
  exit 1
}

Push-Location $projectRoot
try {
  Write-Host "[1/3] Compilando archivos del proyecto..." -ForegroundColor Cyan
  & $selectedPython -m py_compile cobertura_lte.py app.py tests/test_cobertura_lte.py
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

  Write-Host "[2/3] Ejecutando tests..." -ForegroundColor Cyan
  & $selectedPython -m pytest tests -v
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

  Write-Host "[3/3] Lanzando servidor Flask en http://127.0.0.1:5000 ..." -ForegroundColor Green
  & $selectedPython app.py
  exit $LASTEXITCODE
}
finally {
  Pop-Location
}
