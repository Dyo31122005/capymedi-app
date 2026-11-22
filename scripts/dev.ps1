# Chay ca backend (FastAPI, cong 8000) va frontend (Next.js, cong 3000) cho dev local.
# Neu PostgreSQL (cong 5432) chua chay, script tu bat Docker Desktop va
# `docker compose up -d db` truoc.
#
# Cach dung (tu thu muc goc repo):
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -NoBrowser
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Reload    # backend tu nap lai khi sua code
#
# Moi server chay trong mot cua so PowerShell rieng (de xem log); dong cua so
# do de tat server tuong ung. Script cho backend /health va frontend san sang
# roi mo trang chat.
#
# Ghi chu: chi dung ASCII trong file nay - PowerShell 5.1 doc file .ps1 khong
# BOM theo code page he thong, dau tieng Viet se bi loi.

param(
    [switch]$NoBrowser,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$frontend = Join-Path $root "frontend"

if (-not (Test-Path $python)) { throw "Khong thay $python - tao virtualenv .venv va pip install -r requirements.txt truoc." }
if (-not (Test-Path (Join-Path $frontend "node_modules"))) { throw "Chua cai frontend - chay 'pnpm install' trong thu muc frontend truoc." }
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) { throw "Khong tim thay pnpm trong PATH." }

function Test-PortBusy([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

# --- PostgreSQL (service "db" trong docker-compose.yml, cong 5432) -----------
# Backend dung ngay neu khong ket noi duoc DB, nen bat DB truoc.
if (-not (Test-PortBusy 5432)) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Cong 5432 (PostgreSQL) chua mo va khong tim thay docker trong PATH. Bat DB thu cong roi chay lai."
    }
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -ne 0) {
        $dockerDesktop = @(
            (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\Docker Desktop.exe"),
            "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        ) | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $dockerDesktop) { throw "Docker daemon chua chay va khong tim thay Docker Desktop.exe - mo Docker Desktop thu cong." }
        Write-Host "Bat Docker Desktop (lan dau co the mat 30-90 s)..."
        Start-Process $dockerDesktop | Out-Null
        $deadline = (Get-Date).AddSeconds(180)
        do {
            Start-Sleep -Seconds 3
            cmd /c "docker info >nul 2>&1"
        } while ($LASTEXITCODE -ne 0 -and (Get-Date) -lt $deadline)
        if ($LASTEXITCODE -ne 0) { throw "Docker Desktop chua san sang sau 180 s." }
    }
    Write-Host "Khoi dong PostgreSQL (docker compose up -d db)..."
    Push-Location $root
    # qua cmd: docker compose in tien trinh ra stderr, PowerShell 5.1 se coi la loi
    try { cmd /c "docker compose up -d db 2>&1" | Write-Host } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "docker compose up -d db that bai." }
    $deadline = (Get-Date).AddSeconds(60)
    while (-not (Test-PortBusy 5432) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
    if (-not (Test-PortBusy 5432)) { throw "PostgreSQL chua mo cong 5432 sau 60 s." }
    Start-Sleep -Seconds 3  # cho Postgres nhan ket noi sau khi mo cong
    Write-Host "PostgreSQL san sang (cong 5432)."
}

# Server nao da chay (cong dang mo) thi bo qua, khong khoi dong lan hai.
$startBackend = -not (Test-PortBusy 8000)
$startFrontend = -not (Test-PortBusy 3000)
foreach ($item in @(@(8000, $startBackend), @(3000, $startFrontend))) {
    if (-not $item[1]) {
        $owner = (Get-NetTCPConnection -LocalPort $item[0] -State Listen | Select-Object -First 1).OwningProcess
        Write-Host "Cong $($item[0]) da co process $owner chay - bo qua (tat bang: Stop-Process -Id $owner)."
    }
}

$reloadArg = ""
if ($Reload) { $reloadArg = "--reload" }

$backendCmd = "`$host.UI.RawUI.WindowTitle = 'CapyMedi backend :8000'; " +
    "`$env:PYTHONIOENCODING = 'utf-8'; Set-Location '$root'; " +
    "& '$python' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 $reloadArg"
$frontendCmd = "`$host.UI.RawUI.WindowTitle = 'CapyMedi frontend :3000'; " +
    "Set-Location '$frontend'; pnpm dev"

if ($startBackend) {
    Write-Host "Khoi dong backend (cong 8000)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd | Out-Null
}
if ($startFrontend) {
    Write-Host "Khoi dong frontend (cong 3000)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd | Out-Null
}

function Wait-Url([string]$url, [string]$name, [int]$timeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -lt 500) { Write-Host "$name san sang: $url"; return $true }
        } catch { Start-Sleep -Seconds 2 }
    }
    Write-Warning "$name chua san sang sau $timeoutSeconds s - xem log trong cua so cua no."
    return $false
}

# Backend nap san kho thuoc va model nhan dien anh truoc khi nhan request.
$backendOk = Wait-Url "http://127.0.0.1:8000/health" "Backend" 240
$frontendOk = Wait-Url "http://localhost:3000" "Frontend" 180

if ($backendOk -and $frontendOk -and -not $NoBrowser) {
    Start-Process "http://localhost:3000/patient/assistant"
}
Write-Host "Xong. Dong 2 cua so 'CapyMedi backend' / 'CapyMedi frontend' de tat server."
