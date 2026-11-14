$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$configFile = Join-Path $projectRoot '.env'
if (-not (Test-Path -LiteralPath $configFile)) { $configFile = Join-Path $projectRoot '.env.example' }
Get-Content -LiteralPath $configFile | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
}
& (Join-Path $projectRoot '.venv/Scripts/python.exe') -m uvicorn whylab.app:app --host 127.0.0.1 --port 8000 --workers 1
