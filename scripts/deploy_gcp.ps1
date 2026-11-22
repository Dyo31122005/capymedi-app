<#
Deploy CapyMedi len Google Cloud Run (ADR-0014). Thay cho scripts/deploy.ps1 (Railway).

Ha tang (Cloud SQL, bucket, Artifact Registry, service account, secret) phai
duoc tao truoc - xem docs/DEPLOY.md muc "Dung ha tang lan dau".

Cach dung (chay tu root repo):
  ./scripts/deploy_gcp.ps1                  # ca backend + frontend
  ./scripts/deploy_gcp.ps1 -Target api      # chi backend
  ./scripts/deploy_gcp.ps1 -Target web      # chi frontend

Frontend can NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY luc BUILD.
Truyen qua tham so hoac bien moi truong cung ten; de trong thi dang nhap Google
(Supabase) se khong hoat dong nhung phan con lai van chay.
#>
param(
    [ValidateSet("all", "api", "web")]
    [string]$Target = "all",
    [string]$Project = "capymedi-513714",
    [string]$Region = "asia-southeast1",
    [string]$SupabaseUrl = $env:NEXT_PUBLIC_SUPABASE_URL,
    [string]$SupabaseAnonKey = $env:NEXT_PUBLIC_SUPABASE_ANON_KEY
)

$ErrorActionPreference = "Stop"
$gcloud = (Get-Command gcloud -ErrorAction SilentlyContinue).Source
if (-not $gcloud) { $gcloud = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" }

$projectNumber = (& $gcloud projects describe $Project --format="value(projectNumber)").Trim()
$registry = "$Region-docker.pkg.dev/$Project/capymedi"
$tag = (git rev-parse --short HEAD).Trim()
$sqlConn = "${Project}:${Region}:capymedi-db"
$bucket = "$Project-data"
# URL Cloud Run co dinh theo ten service + project number, nen biet truoc duoc
# truoc khi deploy - FE build voi dung API URL ngay lan dau, BE dat dung CORS.
$beUrl = "https://capymedi-be-$projectNumber.$Region.run.app"
$feUrl = "https://capymedi-fe-$projectNumber.$Region.run.app"

function Invoke-Gcloud([string[]]$GcloudArgs) {
    & $gcloud @GcloudArgs
    if ($LASTEXITCODE -ne 0) { throw "gcloud $($GcloudArgs[0..1] -join ' ') failed (exit $LASTEXITCODE)" }
}

function Deploy-Api {
    $image = "$registry/backend:$tag"
    Write-Host "==> Build backend $image"
    # .gcloudignore o root loc goi upload (giong .railwayignore cu).
    Invoke-Gcloud @("builds", "submit", "--project=$Project", "--region=$Region", "--tag=$image", "--machine-type=e2-highcpu-8", "--timeout=1800s", ".")

    $envVars = @(
        "APP_ENV=production",
        "LOG_LEVEL=INFO",
        "CORS_ORIGINS=$feUrl",
        # db-g1-small: max_connections=100 (flag dat luc tao instance). Pool mac
        # dinh 20+30 cua config.py danh cho Railway, thu nho lai cho 1 instance.
        "DB_POOL_SIZE=5",
        "DB_MAX_OVERFLOW=10",
        # Bucket mount qua Cloud Storage FUSE - code doc/ghi anh qua duong dan
        # thu muc nhu cu, khong doi code storage.
        "PHOTO_STORAGE_DIR=/app/data/gcs/photo_verifications",
        "DRUG_IMAGE_STORAGE_DIR=/app/data/gcs/drug_images",
        "DRUG_IMAGE_CHAT_DOCTOR_STORAGE_DIR=/app/data/gcs/drug_image_chat_doctor_private",
        "CAPYMEDI_RUNTIME_PROFILE=v2_only",
        "AGENT_RUNTIME_ENABLED=true",
        "AGENT_ROLLOUT_PERCENTAGE=100",
        "PRESCRIPTION_V2_MODE=shadow",
        "DOSE_RUNTIME_MODE=shadow",
        "DRUG_IMAGE_CHAT_RECOGNITION_ENABLED=true",
        # VLM dem vien thuoc (xac nhan lieu bang anh): goi thang OpenAI, khong
        # qua endpoint trung gian. Da test that 2026-11-05: 3/3 anh hop thuoc
        # dem dung, 2-5s/anh, json_mode=schema chay duoc.
        "VLM_PROVIDER=openai",
        "VLM_MODEL=gpt-5.4"
    ) -join ","

    $secrets = @(
        "DATABASE_URL=DATABASE_URL:latest",
        "JWT_SECRET=JWT_SECRET:latest",
        "INTERNAL_AUTH_SECRET=INTERNAL_AUTH_SECRET:latest",
        "OPENAI_API_KEY=OPENAI_API_KEY:latest",
        "OPENAI_ROUTER_API_KEY=OPENAI_ROUTER_API_KEY:latest",
        "OPENAI_MAIN_API_KEY=OPENAI_MAIN_API_KEY:latest",
        "OPENAI_FALLBACK_API_KEY=OPENAI_FALLBACK_API_KEY:latest",
        "OPENAI_EMBEDDING_API_KEY=OPENAI_EMBEDDING_API_KEY:latest",
        "VLM_API_KEY=OPENAI_API_KEY:latest"
    ) -join ","

    Write-Host "==> Deploy capymedi-be"
    # min=max=1 + no-cpu-throttling: scheduler nhac thuoc/escalation (APScheduler)
    # chay TRONG tien trinh backend (ADR-0007, ADR-0014) - scale ve 0 thi khong
    # nhac, nhieu instance thi chay trung job.
    Invoke-Gcloud @(
        "run", "deploy", "capymedi-be", "--project=$Project", "--region=$Region",
        "--image=$image",
        "--service-account=capymedi-be@$Project.iam.gserviceaccount.com",
        "--add-cloudsql-instances=$sqlConn",
        "--execution-environment=gen2",
        # 4Gi: luc khoi dong backend tai model OpenCLIP ViT-B-32 (nhan dien anh
        # thuoc) tu HuggingFace - o dia Cloud Run nam trong RAM nen file tai ve
        # + model da nap vuot 2Gi (OOM that o revision 00002).
        "--cpu=1", "--memory=4Gi",
        "--min-instances=1", "--max-instances=1", "--no-cpu-throttling",
        "--timeout=300", "--allow-unauthenticated",
        # Cloud Run mount GCSFuse voi dir-mode 777 / file-mode 666 (da xac nhan qua
        # log revision dau tien) nen appuser ghi duoc anh, khong can uid/gid.
        # `chown` trong docker-entrypoint.sh se in canh bao vo hai tren mount nay.
        "--add-volume=name=data,type=cloud-storage,bucket=$bucket,mount-options=implicit-dirs",
        "--add-volume-mount=volume=data,mount-path=/app/data/gcs",
        "--update-env-vars=$envVars",
        "--update-secrets=$secrets"
    )
    Write-Host "==> Smoke test $beUrl/api/v1/status"
    Invoke-RestMethod -Uri "$beUrl/api/v1/status" -TimeoutSec 60 | Out-Null
    Write-Host "    OK"
}

function Deploy-Web {
    $image = "$registry/frontend:$tag"
    Write-Host "==> Build frontend $image (API_URL=$beUrl)"
    Push-Location frontend
    try {
        Invoke-Gcloud @(
            "builds", "submit", "--project=$Project", "--region=$Region",
            "--config=../deploy/gcp/cloudbuild.frontend.yaml",
            "--substitutions=_IMAGE=$image,_API_URL=$beUrl,_SUPABASE_URL=$SupabaseUrl,_SUPABASE_ANON_KEY=$SupabaseAnonKey",
            "."
        )
    } finally { Pop-Location }

    Write-Host "==> Deploy capymedi-fe"
    Invoke-Gcloud @(
        "run", "deploy", "capymedi-fe", "--project=$Project", "--region=$Region",
        "--image=$image",
        "--service-account=capymedi-fe@$Project.iam.gserviceaccount.com",
        "--cpu=1", "--memory=512Mi",
        "--min-instances=0", "--max-instances=3",
        "--allow-unauthenticated",
        "--update-secrets=INTERNAL_AUTH_SECRET=INTERNAL_AUTH_SECRET:latest"
    )
    Write-Host "==> Smoke test $feUrl"
    Invoke-WebRequest -Uri $feUrl -UseBasicParsing -TimeoutSec 60 | Out-Null
    Write-Host "    OK"
}

if ($Target -in "all", "api") { Deploy-Api }
if ($Target -in "all", "web") { Deploy-Web }
Write-Host "Done. FE: $feUrl  BE: $beUrl"
