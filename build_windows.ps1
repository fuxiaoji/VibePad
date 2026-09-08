param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed --uac-admin --name VibePad --add-data 'config.yaml;.' --collect-all pygame --collect-all uiautomation controller_gui.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    Copy-Item -LiteralPath 'config.yaml' -Destination 'dist/VibePad/config.yaml'
    Compress-Archive -Path 'dist/VibePad' -DestinationPath 'dist/VibePad-v1.0.2.zip' -Force
    Get-FileHash -Algorithm SHA256 'dist/VibePad-v1.0.2.zip'
} finally {
    Pop-Location
}
