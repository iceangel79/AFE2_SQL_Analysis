# Einrichtung der Python-Umgebung (.venv) für Windows
# Aufruf: setup.bat (Doppelklick) oder  powershell -ExecutionPolicy Bypass -File setup.ps1
# Optional: -Recreate  löscht eine bestehende .venv und baut sie neu auf.

param([switch]$Recreate)

# Fehler von Python/pip werden ueber $LASTEXITCODE geprueft (pip schreibt Warnungen nach stderr)
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

function Find-Python {
    # Bevorzugt den Python-Launcher "py" mit 3.12, sonst 3.13/3.11, sonst "python".
    # Rueckgabe als Objekt (Exe + Args): PowerShell wuerde ein Array mit nur einem
    # Element beim return in einen einfachen String umwandeln.
    foreach ($v in @("3.12", "3.13", "3.11")) {
        try {
            & py "-$v" -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { return [pscustomobject]@{ Exe = "py"; Args = @("-$v") } }
        } catch { }
    }
    try {
        $ok = & python -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
        if ($ok -eq "True") { return [pscustomobject]@{ Exe = "python"; Args = @() } }
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
    $pyArgs = @($py.Args)
    Write-Host "Erstelle .venv mit: $($py.Exe) $($pyArgs -join ' ')" -ForegroundColor Cyan
    & $py.Exe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "Erstellen der .venv fehlgeschlagen." -ForegroundColor Red
        exit 1
    }
}

$venvPy = ".venv\Scripts\python.exe"
Write-Host "Installiere Pakete ..." -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "Installation der Pakete fehlgeschlagen." -ForegroundColor Red; exit 1 }
& $venvPy -m pip install -e . --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "Installation des Projekts fehlgeschlagen." -ForegroundColor Red; exit 1 }

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
