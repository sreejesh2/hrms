<#
Day Pay HRMS - install on Windows (Windows 10/11, Windows Server 2022+).

Easiest: double-click deploy\windows\install.bat (asks for administrator rights).
Or, in an Administrator PowerShell:
    powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1
    powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1 -Port 8080

Unattended first admin (otherwise you are asked):
    $env:DAYPAY_ADMIN_EMAIL="hr@company.com"; $env:DAYPAY_ADMIN_PASSWORD="..."

Installs Python 3.12 and PostgreSQL 16 with winget when missing, then sets up
C:\DayPay (app, venv, backups, logs), a "DayPay Server" task that starts at boot
without anyone logging in, a nightly "DayPay Backup" task, and a firewall rule.
Safe to re-run: the database, settings (.env), uploads and admin users are kept.
#>
param(
    [int]$Port = 80,
    [string]$AdminEmail = $env:DAYPAY_ADMIN_EMAIL,
    [string]$AdminPassword = $env:DAYPAY_ADMIN_PASSWORD
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
. "$PSScriptRoot\common.ps1"

Assert-Administrator
$SrcDir = (Resolve-Path "$PSScriptRoot\..\..").Path
if (-not (Test-Path "$SrcDir\manage.py")) { Fail "Run this from inside the Day Pay project folder." }
if ($SrcDir -eq $AppDir) { Fail "Run this from the downloaded project folder, not from $AppDir." }

# ---------------------------------------------------------------- Python
Say "Checking Python 3.12+"
$SysPython = Find-Python
if (-not $SysPython) {
    Say "Installing Python 3.12 (winget)"
    Install-WithWinget "Python.Python.3.12" "/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1"
    $SysPython = Find-Python
    if (-not $SysPython) { Fail "Python was installed but not found. Restart the computer and run install again." }
}
Write-Host "Using $SysPython"

# ---------------------------------------------------------------- PostgreSQL
Say "Checking PostgreSQL"
New-Item -ItemType Directory -Force -Path $Base, $SecretsDir | Out-Null
Protect-Folder $SecretsDir
$PgBin = Find-PgBin
if (-not $PgBin) {
    Say "Installing PostgreSQL 16 (winget) - this takes a few minutes"
    $SuperPw = New-Secret
    Write-Utf8NoBom $SuperPwFile $SuperPw
    Install-WithWinget "PostgreSQL.PostgreSQL.16" "--mode unattended --unattendedmodeui none --superpassword $SuperPw --serverport 5432"
    $PgBin = Find-PgBin
    if (-not $PgBin) { Fail "PostgreSQL was installed but not found in C:\Program Files\PostgreSQL." }
}
Write-Host "Using $PgBin"
Start-PostgresService $PgBin

if (Test-Path $SuperPwFile) {
    $SuperPw = (Get-Content $SuperPwFile -Raw).Trim()
} else {
    $secure = Read-Host "Enter the password of the PostgreSQL 'postgres' user (set when PostgreSQL was installed)" -AsSecureString
    $SuperPw = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}

Say "Creating the Day Pay database"
$NewDbPw = $null
if ((Invoke-PgSuper $PgBin $SuperPw "SELECT 1 FROM pg_roles WHERE rolname='daypay'") -ne "1") {
    $NewDbPw = New-Secret
    Invoke-PgSuper $PgBin $SuperPw "CREATE ROLE daypay LOGIN PASSWORD '$NewDbPw'" | Out-Null
}
if ((Invoke-PgSuper $PgBin $SuperPw "SELECT 1 FROM pg_database WHERE datname='daypay'") -ne "1") {
    Invoke-PgSuper $PgBin $SuperPw "CREATE DATABASE daypay OWNER daypay" | Out-Null
}

# ---------------------------------------------------------------- Code
Stop-DayPayServer
Say "Copying application code to $AppDir"
Copy-AppCode $SrcDir

Say "Writing settings (.env)"
if (-not (Test-Path $EnvFile)) {
    if (-not $NewDbPw) { Fail "The database user exists but $EnvFile is missing. Restore the old .env (it holds the database password)." }
    $ips = @(Get-LanIPs)
    $hostName = $env:COMPUTERNAME
    $suffix = ""
    if ($Port -ne 80) { $suffix = ":$Port" }
    $origins = @($ips + @($hostName, "$hostName.local") | ForEach-Object { "http://$_$suffix" }) -join ","
    $hosts = @(@("localhost", "127.0.0.1") + $ips + @($hostName, "$hostName.local")) -join ","
    $siteIp = "localhost"
    if ($ips.Count -gt 0) { $siteIp = $ips[0] }
    $lines = @(
        "DJANGO_SECRET_KEY=$(New-Secret 50)",
        "DJANGO_DEBUG=False",
        "DJANGO_ALLOWED_HOSTS=$hosts",
        "DJANGO_CSRF_TRUSTED_ORIGINS=$origins",
        "DJANGO_HTTPS=False",
        "DJANGO_TIME_ZONE=Asia/Dubai",
        "DATABASE_URL=postgres://daypay:$NewDbPw@localhost:5432/daypay",
        "SITE_URL=http://$siteIp$suffix",
        "EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend",
        "HRMS_EMAIL_NOTIFICATIONS=false"
    )
    Write-Utf8NoBom $EnvFile (($lines -join "`r`n") + "`r`n")
    Write-Host "Created $EnvFile (addresses: $hosts)"
} else {
    Write-Host "Keeping existing $EnvFile"
}
Set-WindowsEnvDefaults $PgBin $Port
Protect-File $EnvFile

# ---------------------------------------------------------------- Python packages + database
Say "Installing Python packages"
if (-not (Test-Path $Python)) { Invoke-Checked $SysPython @("-m", "venv", $Venv) }
Invoke-Checked $Python @("-m", "pip", "install", "-q", "--upgrade", "pip")
Invoke-Checked $Python @("-m", "pip", "install", "-q", "-r", "$AppDir\requirements.txt")

Say "Preparing database and static files"
Invoke-Manage @("migrate", "--noinput")
Invoke-Manage @("collectstatic", "--noinput", "-v", "0")
# Explicit groups: never the dev admin (admin@example.com / admin123) or demo data
Invoke-Manage @("seed", "--only", "rbac", "org", "leave", "expenses", "payroll", "attendance", "ot_rules", "performance")

# ---------------------------------------------------------------- Server, backups, firewall, power
Say "Installing the DayPay Server (starts at boot) and nightly backup tasks"
New-Item -ItemType Directory -Force -Path $BackupDir, $LogDir | Out-Null
Protect-Folder $BackupDir
Assert-PortFree $Port
Register-DayPayTasks
Start-ScheduledTask -TaskName $ServerTask

Say "Allowing port $Port from the local network (Windows Firewall)"
Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $FirewallRule -Direction Inbound -Protocol TCP -LocalPort $Port `
    -Action Allow -RemoteAddress LocalSubnet -Profile Any | Out-Null

Say "Keeping the computer awake (no sleep; hibernate and Fast Startup off)"
powercfg /change standby-timeout-ac 0 | Out-Null
powercfg /change hibernate-timeout-ac 0 | Out-Null
# Fast Startup makes "Shut down" a half-hibernate; boot-time tasks may then not run.
# Turning hibernation off disables Fast Startup, so every power-on is a real boot.
powercfg /hibernate off | Out-Null

Wait-ForApp $Port

# ---------------------------------------------------------------- First admin
if (-not (Test-Superuser)) {
    Say "Create the first admin login (email + password)"
    if ($AdminEmail -and $AdminPassword) {
        $env:DJANGO_SUPERUSER_EMAIL = $AdminEmail
        $env:DJANGO_SUPERUSER_PASSWORD = $AdminPassword
        try { Invoke-Manage @("createsuperuser", "--noinput") }
        finally { Remove-Item Env:DJANGO_SUPERUSER_EMAIL, Env:DJANGO_SUPERUSER_PASSWORD -ErrorAction SilentlyContinue }
    } else {
        Push-Location $AppDir
        try { & $Python manage.py createsuperuser } finally { Pop-Location }
    }
    if (-not (Test-Superuser)) { Fail "No admin login was created. Run install again." }
}

$ip = "localhost"
$lan = @(Get-LanIPs)
if ($lan.Count -gt 0) { $ip = $lan[0] }
$url = "http://$ip/"
if ($Port -ne 80) { $url = "http://${ip}:$Port/" }
Say "Done!"
Write-Host ""
Write-Host "  Open in a browser:   $url"
Write-Host "  ZKTeco devices:      set Cloud Server / ADMS address to $ip, port $Port"
Write-Host "                       then approve each device in Settings -> Devices (tick Active)"
Write-Host "  Backups:             $BackupDir (nightly at 01:30, 30 days kept)"
Write-Host "  Logs:                $LogDir\daypay.log"
Write-Host "  Update later:        double-click deploy\windows\update.bat in the new code folder"
Write-Host ""
