# Збирає Rhythmos.exe (PyInstaller) та інсталятор RhythmosSetup-<версія>.exe (Inno Setup).
# Використання:  .\build.ps1            — версія береться з src\rhythmos.py
#                .\build.ps1 -Version 1.2.0
param([string]$Version)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $Version) {
    $Version = (Select-String -Path "src\rhythmos.py" -Pattern '^__version__ = "(.+)"').Matches[0].Groups[1].Value
}
Write-Host "Rhythmos $Version" -ForegroundColor Cyan

function Invoke-Step([string]$Name, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name завершився з кодом $LASTEXITCODE" }
}

Invoke-Step "pip" { python -m pip install --disable-pip-version-check -q -r requirements.txt -r requirements-build.txt }
Invoke-Step "make_icon" { python tools\make_icon.py }

# --specpath змінює базу відносних шляхів, тому іконка — абсолютним шляхом
Invoke-Step "PyInstaller" {
    python -m PyInstaller --noconfirm --clean --windowed `
        --name Rhythmos `
        --icon "$PSScriptRoot\assets\rhythmos.ico" `
        --hidden-import pystray._win32 `
        --distpath dist --workpath build --specpath build `
        src\rhythmos.py
}

$iscc = @(
    $env:ISCC,
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Не знайдено Inno Setup (ISCC.exe). Встановіть: winget install JRSoftware.InnoSetup" }

& $iscc /Qp "/DAppVersion=$Version" installer\rhythmos.iss
if ($LASTEXITCODE -ne 0) { throw "ISCC завершився з кодом $LASTEXITCODE" }

Write-Host "Готово: dist\RhythmosSetup-$Version.exe" -ForegroundColor Green
