param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$originalPath = $env:PATH
Push-Location $PSScriptRoot
try {
    $pythonExe = (Get-Command $Python).Source
    # Do not collect unrelated DLLs (e.g. Poppler's ICU) from the host PATH.
    $env:PATH = "$(Split-Path $pythonExe);$env:SystemRoot\System32;$env:SystemRoot"
    & $pythonExe -m PyInstaller --noconfirm --clean --onedir --windowed --distpath dist/v1.0.3 --name VibePad --add-data 'config.yaml;.' --collect-all pygame --collect-all uiautomation launcher.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    Copy-Item -LiteralPath 'config.yaml' -Destination 'dist/v1.0.3/VibePad/config.yaml'
    $reportPath = Join-Path $PSScriptRoot 'build/packaged-startup.json'
    if (Test-Path -LiteralPath $reportPath) { Remove-Item -LiteralPath $reportPath }
    $process = Start-Process -FilePath (Join-Path $PSScriptRoot 'dist/v1.0.3/VibePad/VibePad.exe') -ArgumentList @('--self-test', ('"{0}"' -f $reportPath)) -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(30000)) {
        $process.Kill()
        throw 'Packaged startup check timed out'
    }
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $reportPath)) { throw 'Packaged startup check failed' }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if (-not $report.ok -or -not $report.frozen) { throw 'Packaged startup check failed' }
    Compress-Archive -Path 'dist/v1.0.3/VibePad' -DestinationPath 'dist/VibePad-v1.0.3.zip' -Force
    Get-FileHash -Algorithm SHA256 'dist/VibePad-v1.0.3.zip'
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
