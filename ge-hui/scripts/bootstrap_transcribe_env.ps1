param(
    [string]$EnvPath = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $EnvPath) {
    $EnvPath = Join-Path $ProjectRoot ".runtime\whisper-py311"
}

$Conda = Get-Command conda -ErrorAction SilentlyContinue
if (-not $Conda) {
    throw "conda is required to create the isolated Python 3.11 environment"
}

if (-not (Test-Path (Join-Path $EnvPath "python.exe"))) {
    & $Conda.Source create -y -p $EnvPath python=3.11 pip
}

$Python = Join-Path $EnvPath "python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
& $Python -m pip install openai-whisper==20250625 yt-dlp==2026.6.9 "pyyaml>=6,<7"
& $Python -c "import torch; assert torch.cuda.is_available(), 'CUDA is unavailable'; print(torch.__version__); print(torch.cuda.get_device_name(0)); print(torch.cuda.get_device_capability(0))"

Write-Output "Whisper environment ready: $EnvPath"
