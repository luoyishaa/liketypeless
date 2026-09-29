$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    uv python install 3.12.13
    if ($LASTEXITCODE -ne 0) { throw 'Unable to prepare Python 3.12.13' }
    if (-not (Test-Path '.venv-release/Scripts/python.exe')) {
        uv venv --python 3.12.13 .venv-release
        if ($LASTEXITCODE -ne 0) { throw 'Unable to create release environment' }
    }
    uv pip sync --python .venv-release/Scripts/python.exe --require-hashes apps/local-api/requirements-release.lock
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install locked release dependencies' }
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install desktop dependencies' }
} finally { Pop-Location }
