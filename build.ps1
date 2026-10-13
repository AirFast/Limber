# Збирає Limber.exe (PyInstaller) та інсталятор LimberSetup-<версія>.exe (Inno Setup).
# Використання:  .\build.ps1            — версія береться з src\limber.py
#                .\build.ps1 -Version 1.2.0
param([string]$Version)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $Version) {
    $Version = (Select-String -Path "src\limber.py" -Pattern '^__version__ = "(.+)"').Matches[0].Groups[1].Value
}
Write-Host "Limber $Version" -ForegroundColor Cyan

function Invoke-Step([string]$Name, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name завершився з кодом $LASTEXITCODE" }
}

Invoke-Step "pip" { python -m pip install --disable-pip-version-check -q -r requirements.txt -r requirements-build.txt }
Invoke-Step "make_icon" { python tools\make_icon.py }

# --specpath змінює базу відносних шляхів, тому іконка — абсолютним шляхом
Invoke-Step "PyInstaller" {
    python -m PyInstaller --noconfirm --clean --windowed `
        --name Limber `
        --icon "$PSScriptRoot\assets\limber.ico" `
        --hidden-import pystray._win32 `
        --distpath dist --workpath build --specpath build `
        src\limber.py
}

$iscc = @(
    $env:ISCC,
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Не знайдено Inno Setup (ISCC.exe). Встановіть: winget install JRSoftware.InnoSetup" }

& $iscc /Qp "/DAppVersion=$Version" installer\limber.iss
if ($LASTEXITCODE -ne 0) { throw "ISCC завершився з кодом $LASTEXITCODE" }

Write-Host "Готово: dist\LimberSetup-$Version.exe" -ForegroundColor Green
