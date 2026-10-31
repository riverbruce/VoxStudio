# VoxStudio installer - everything stays inside this folder (Python, packages, models, caches).
# Safe to run again: finished steps are skipped (use it to repair an installation).
param([switch]$NoPause)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force -Path "$Root\logs", "$Root\runtime", "$Root\cache", "$Root\models" | Out-Null
$Log = "$Root\logs\install.log"
$Status = "$Root\logs\install_status.txt"
$VoxCommit = "cce58a5b59303c9bd63d12f23afe6a49a4a80c59"   # VoxCPM version tested with VoxStudio

$env:UV_CACHE_DIR = "$Root\cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "$Root\runtime\python"
$env:UV_LINK_MODE = "copy"
$env:UV_PYTHON_BIN_DIR = "$Root\runtime\bin"
$env:UV_TOOL_DIR = "$Root\runtime\tools"
$env:UV_NO_MODIFY_PATH = "1"
$env:HF_HOME = "$Root\cache\hf"
$env:MODELSCOPE_CACHE = "$Root\cache\modelscope"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:SETUPTOOLS_SCM_PRETEND_VERSION_FOR_VOXCPM = "2.1.0"
$env:SETUPTOOLS_SCM_PRETEND_VERSION = "2.1.0"

function Say($m) { $l = "$(Get-Date -Format 'HH:mm:ss') $m"; Write-Host $l -ForegroundColor Cyan; Add-Content -Path $Log -Value $l -Encoding UTF8 }
function Step($n, $m) { Set-Content -Path $Status -Value "STEP $n/8 $m" -Encoding UTF8; Write-Host ""; Say "===== [$n/8] $m =====" }
function Run($exe, [string[]]$a) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $exe @a 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $Log -Append | Write-Host
    $code = $LASTEXITCODE; $ErrorActionPreference = $old
    if ($code -ne 0) { throw "Command failed ($code): $exe $($a -join ' ')" }
}
function Download($url, $out) {
    for ($i = 1; $i -le 4; $i++) {
        try { Invoke-WebRequest $url -OutFile $out -UseBasicParsing; return } catch { Say "  retry $i : $_"; Start-Sleep 3 }
    }
    throw "Cannot download $url (check internet connection)"
}

$code = 0
try {
    Write-Host "=================================================================" -ForegroundColor Yellow
    Write-Host "  VoxStudio - dang cai dat. Lan dau mat 15-40 phut (tai ~8GB)." -ForegroundColor Yellow
    Write-Host "  Vui long KHONG dong cua so nay." -ForegroundColor Yellow
    Write-Host "=================================================================" -ForegroundColor Yellow
    Say "VoxStudio install started in $Root"

    # ---- GPU check
    $gpu = "cpu"
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $smi -and (Test-Path "C:\Windows\System32\nvidia-smi.exe")) { $smi = "C:\Windows\System32\nvidia-smi.exe" }
    if ($smi) {
        try {
            $info = & $smi --query-gpu=name,memory.total --format=csv,noheader 2>$null | Select-Object -First 1
            if ($info) { $gpu = "cuda"; Say "GPU: $info" }
        } catch {}
    }
    if ($gpu -eq "cpu") {
        Say "WARNING: no NVIDIA GPU found -> CPU mode (very slow, only for short texts)."
        Write-Host "  [!] Khong thay card NVIDIA. VoxStudio se chay bang CPU (rat cham)." -ForegroundColor Red
    }

    Step 1 "uv (package manager, local copy)"
    $Uv = "$Root\runtime\uv\uv.exe"
    if (!(Test-Path $Uv)) {
        $zip = "$Root\runtime\uv.zip"
        Download "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" $zip
        Expand-Archive $zip -DestinationPath "$Root\runtime\uv" -Force
        Remove-Item $zip
    }
    Run $Uv @("--version")

    Step 2 "VoxCPM source (github.com/OpenBMB/VoxCPM)"
    if (!(Test-Path "$Root\VoxCPM-src\pyproject.toml")) {
        $zip = "$Root\runtime\voxcpm.zip"
        Download "https://codeload.github.com/OpenBMB/VoxCPM/zip/$VoxCommit" $zip
        if (Test-Path "$Root\runtime\vsrc") { Remove-Item "$Root\runtime\vsrc" -Recurse -Force }
        Expand-Archive $zip -DestinationPath "$Root\runtime\vsrc" -Force
        $inner = Get-ChildItem "$Root\runtime\vsrc" -Directory | Select-Object -First 1
        Move-Item $inner.FullName "$Root\VoxCPM-src"
        Remove-Item $zip; Remove-Item "$Root\runtime\vsrc" -Recurse -Force
    }

    Step 3 "Private Python 3.11 + virtual env (.venv)"
    if (!(Test-Path "$Root\.venv\Scripts\python.exe")) {
        Run $Uv @("python", "install", "3.11")
        Run $Uv @("venv", "$Root\.venv", "--python", "3.11", "--python-preference", "only-managed")
    }
    $Py = "$Root\.venv\Scripts\python.exe"

    Step 4 "PyTorch 2.7.1 ($gpu)"
    if ($gpu -eq "cuda") {
        Run $Uv @("pip", "install", "--python", $Py, "torch==2.7.1", "torchaudio==2.7.1", "--index-url", "https://download.pytorch.org/whl/cu126")
    } else {
        Run $Uv @("pip", "install", "--python", $Py, "torch==2.7.1", "torchaudio==2.7.1", "--index-url", "https://download.pytorch.org/whl/cpu")
    }

    Step 5 "VoxCPM + VoxStudio libraries"
    Run $Uv @("pip", "install", "--python", $Py, "$Root\VoxCPM-src", "-r", "$Root\requirements.txt")
    # torchcodec (pulled by voxcpm) breaks with torch 2.7 on Windows -> remove; VoxStudio reads audio via soundfile/ffmpeg
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $Uv pip uninstall --python $Py torchcodec 2>&1 | Out-Null
    $ErrorActionPreference = $old
    Run $Py @("-c", "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda, torch.cuda.is_available())")

    Step 6 "Download models (VoxCPM2 ~5GB, Whisper ~1.6GB, ZipEnhancer)"
    Run $Py @("$Root\scripts\download_models.py")

    Step 7 "Self test (read one sentence)"
    Run $Py @("$Root\scripts\selftest.py")

    Step 8 "Shortcuts"
    $ws = New-Object -ComObject WScript.Shell
    $targets = @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"))
    foreach ($t in $targets) {
        $lnk = $ws.CreateShortcut((Join-Path $t "VoxStudio.lnk"))
        $lnk.TargetPath = "$env:SystemRoot\System32\wscript.exe"
        $lnk.Arguments = "`"$Root\VoxStudio.vbs`""
        $lnk.WorkingDirectory = $Root
        $lnk.IconLocation = "$Root\assets\icon.ico"
        $lnk.Description = "VoxStudio - clone giong & doc kich ban"
        $lnk.Save()
    }

    Set-Content -Path $Status -Value "DONE" -Encoding UTF8
    Say "INSTALL DONE."
    Write-Host ""
    Write-Host "  CAI DAT XONG! Mo VoxStudio bang icon ngoai Desktop." -ForegroundColor Green
}
catch {
    $code = 1
    Say "INSTALL FAILED: $_"
    Set-Content -Path $Status -Value "FAILED: $_" -Encoding UTF8
    Write-Host ""
    Write-Host "  CAI DAT CHUA XONG. Kiem tra mang Internet roi chay lai 'install.bat' (cac buoc da xong se duoc bo qua)." -ForegroundColor Red
    Write-Host "  Chi tiet loi: logs\install.log" -ForegroundColor Red
}
if (-not $NoPause) { Write-Host ""; Read-Host "Nhan Enter de dong" | Out-Null }
exit $code
