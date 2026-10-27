# Einrichtung der Python-Umgebung (.venv) für Windows
# Aufruf: setup.bat (Doppelklick) oder  powershell -ExecutionPolicy Bypass -File setup.ps1
# Optional: -Recreate  löscht eine bestehende .venv und baut sie neu auf.

param([switch]$Recreate)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Find-Python {
    # Bevorzugt den Python-Launcher "py" mit 3.12, sonst 3.13/3.11, sonst "python"
    foreach ($v in @("3.12", "3.13", "3.11")) {
        try {
            $out = & py "-$v" -c "import sys; print(sys.version)" 2>$null
            if ($LASTEXITCODE -eq 0) { return @("py", "-$v") }
        } catch { }
    }
    try {
        $ok = & python -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
        if ($ok -eq "True") { return @("python") }
    } catch { }
    return $null
}

if ($Recreate -and (Test-Path ".venv")) {
    Write-Host "Loesche bestehende .venv ..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".venv"
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $py = Find-Python
    if (-not $py) {
        Write-Host "Kein Python >= 3.11 gefunden." -ForegroundColor Red
        Write-Host "Bitte Python 3.12 installieren: https://www.python.org/downloads/ (Haken bei 'Add python.exe to PATH' setzen)"
        exit 1
    }
    Write-Host "Erstelle .venv mit: $($py -join ' ')" -ForegroundColor Cyan
    $exe = $py[0]
    $pyArgs = @()
    if ($py.Length -gt 1) { $pyArgs += $py[1..($py.Length - 1)] }
    & $exe @pyArgs -m venv .venv
}

$venvPy = ".venv\Scripts\python.exe"
Write-Host "Installiere Pakete ..." -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r requirements.txt --quiet
& $venvPy -m pip install -e . --quiet

Write-Host "Registriere Jupyter-Kernel 'afe' ..." -ForegroundColor Cyan
& $venvPy -m ipykernel install --user --name afe --display-name "Python (AFE)" | Out-Null

# Ordner anlegen, die nicht im Repo sind
foreach ($d in @("data\raw", "data\processed", "data\manual", "output")) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

Write-Host ""
Write-Host "Fertig." -ForegroundColor Green
Write-Host "Naechste Schritte:"
Write-Host "  1. SQL-Export nach data\raw\ kopieren"
Write-Host "  2. afe.bat all            (Import, Aufbereitung, Bericht)"
Write-Host "  3. afe.bat notebook       (Jupyter Lab starten)"
