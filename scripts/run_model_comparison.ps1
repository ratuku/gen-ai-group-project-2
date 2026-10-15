param(
    [switch]$Resume,
    [string]$OutputDirectory = '',
    [string]$ConfigPath = '',
    [int]$TokensPerMinute = 7000
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Project virtual environment is missing. Follow the README setup first.'
}
if (-not $env:GROQ_API_KEY) {
    $env:GROQ_API_KEY = [Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'User')
}
if (-not $env:GROQ_API_KEY) {
    $env:GROQ_API_KEY = [Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'Machine')
}
if (-not $env:GROQ_API_KEY) {
    throw 'Set GROQ_API_KEY in Windows Environment Variables before running.'
}
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $projectRoot 'evaluations\model_comparison\local\free-tier-validation-live'
}
if (-not $ConfigPath) {
    $metadataPath = Join-Path $OutputDirectory 'metadata.json'
    if ($Resume -and (Test-Path -LiteralPath $metadataPath)) {
        $savedMetadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
        $ConfigPath = $savedMetadata.config_path
    }
    else {
        $ConfigPath = Join-Path $projectRoot 'config\mcp.json'
    }
}

$runArguments = @(
    '-m', 'evaluations.model_comparison.run',
    '--models', 'openai/gpt-oss-20b', 'openai/gpt-oss-120b',
    '--output', $OutputDirectory,
    '--config', $ConfigPath,
    '--repeats', '1',
    '--tokens-per-minute', "$TokensPerMinute"
)
if ($Resume) { $runArguments += '--resume' }

Push-Location -LiteralPath $projectRoot
try {
    & $taskPython @runArguments
    $resultCode = $LASTEXITCODE
    if ($resultCode -eq 3) {
        Write-Host 'Capacity unavailable. Wait for allowance, then run this script again with -Resume.'
    }
    elseif ($resultCode -eq 2) {
        Write-Host 'Check setup. If the output directory already exists, use -Resume or a new -OutputDirectory.'
    }
}
finally {
    Pop-Location
}
exit $resultCode
