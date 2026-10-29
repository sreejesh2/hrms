# Day Pay HRMS - shared helpers for install.ps1 / update.ps1 (Windows PowerShell 5.1+).
# Keep this file ASCII-only: Windows PowerShell 5.1 misreads UTF-8 without a BOM.

$Base         = "C:\DayPay"
$AppDir       = "$Base\app"
$Venv         = "$Base\venv"
$Python       = "$Venv\Scripts\python.exe"
$BackupDir    = "$Base\backups"
$LogDir       = "$Base\logs"
$SecretsDir   = "$Base\secrets"
$SuperPwFile  = "$SecretsDir\postgres-superuser-password.txt"
$EnvFile      = "$AppDir\.env"
$ServerTask   = "DayPay Server"
$BackupTask   = "DayPay Backup"
$FirewallRule = "Day Pay (HTTP)"

function Say([string]$Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }

function Fail([string]$Message) {
    Write-Host "`nERROR: $Message" -ForegroundColor Red
    exit 1
}

function Assert-Administrator {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Fail "Run as Administrator (double-click the .bat file and allow the prompt)."
    }
}

function New-Secret([int]$Length = 32) {
    # Letters and digits only: safe in URLs, .env files and installer arguments
    $chars = [char[]]"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $bytes = New-Object byte[] $Length
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    # PowerShell 5.1 "UTF8" adds a BOM, which hides the first .env key from Python
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}

function Invoke-Checked([string]$Exe, [string[]]$ArgList) {
    # Native tools print warnings on stderr; judge them by exit code only
    $ErrorActionPreference = "Continue"
    & $Exe @ArgList 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { Fail "Command failed (exit $LASTEXITCODE): $Exe $($ArgList -join ' ')" }
}

function Invoke-Manage([string[]]$ArgList) {
    Push-Location $AppDir
    try { Invoke-Checked $Python (@("manage.py") + $ArgList) } finally { Pop-Location }
}

function Install-WithWinget([string]$Id, [string]$Override, [string]$Scope = "") {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        Fail "winget is not available on this Windows. Install $Id by hand (see deploy\windows\INSTALL-WINDOWS.md), then run install again."
    }
    $wingetArgs = @("install", "--id", $Id, "-e", "--silent", "--accept-package-agreements",
                    "--accept-source-agreements", "--override", $Override)
    if ($Scope) { $wingetArgs += @("--scope", $Scope) }
    $ErrorActionPreference = "Continue"
    & $winget.Source @wingetArgs 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { Write-Host "winget finished with exit code $LASTEXITCODE - checking the install anyway." }
}

function Find-Python {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @("3.13", "3.12")) {
            $ErrorActionPreference = "Continue"
            $out = & $launcher.Source "-$version" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) { return ([string]($out | Select-Object -First 1)).Trim() }
        }
    }
    foreach ($candidate in @("$env:ProgramFiles\Python313\python.exe", "$env:ProgramFiles\Python312\python.exe")) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Find-PgBin {
    $dirs = @(Get-ChildItem "$env:ProgramFiles\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName "bin\pg_dump.exe") } |
        Sort-Object { [int]($_.Name -replace '[^0-9].*$', '0') } -Descending)
    if ($dirs.Count -gt 0) { return (Join-Path $dirs[0].FullName "bin") }
    return $null
}

function Start-PostgresService([string]$PgBin) {
    $service = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $service) { Fail "The PostgreSQL Windows service was not found." }
    Set-Service -Name $service.Name -StartupType Automatic
    if ($service.Status -ne "Running") { Start-Service -Name $service.Name }
    $ErrorActionPreference = "Continue"
    for ($i = 0; $i -lt 60; $i++) {
        & "$PgBin\pg_isready.exe" -h localhost -p 5432 -q 2>$null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 1
    }
    Fail "PostgreSQL did not start. Check the '$($service.Name)' service in services.msc."
}

function Invoke-PgSuper([string]$PgBin, [string]$SuperPw, [string]$Sql) {
    $ErrorActionPreference = "Continue"
    $env:PGPASSWORD = $SuperPw
    try {
        $out = & "$PgBin\psql.exe" -h localhost -U postgres -d postgres -tAc $Sql 2>&1
        if ($LASTEXITCODE -ne 0) { Fail "PostgreSQL command failed (wrong 'postgres' password?): $out" }
        return ([string]($out | Out-String)).Trim()
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

function Stop-DayPayServer {
    if (Get-ScheduledTask -TaskName $ServerTask -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $ServerTask -ErrorAction SilentlyContinue
    }
    # Also stop a server started by hand; running Python locks package files
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*deploy\windows\serve.py*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

function Copy-AppCode([string]$Src) {
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    $ErrorActionPreference = "Continue"
    # /MIR mirrors the code; excluded folders/files (uploads, settings, backups) are never deleted
    & robocopy.exe $Src $AppDir /MIR /XD .git .venv venv __pycache__ media staticfiles backups `
        /XF .env db.sqlite3 .DS_Store /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "Copying the code failed (robocopy exit $LASTEXITCODE)." }
    $global:LASTEXITCODE = 0
    New-Item -ItemType Directory -Force -Path "$AppDir\media" | Out-Null
}

function Get-LanIPs {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Sort-Object InterfaceMetric |
        ForEach-Object { $_.IPAddress }
}

function Set-EnvDefault([string]$Key, [string]$Value) {
    $lines = @(Get-Content $EnvFile -ErrorAction SilentlyContinue)
    if (-not ($lines | Where-Object { $_ -match "^$([regex]::Escape($Key))=" })) {
        $text = (($lines + "$Key=$Value") -join "`r`n") + "`r`n"
        Write-Utf8NoBom $EnvFile $text
    }
}

function Get-ConfiguredPort {
    $line = Get-Content $EnvFile | Where-Object { $_ -match "^DAYPAY_LISTEN=" } | Select-Object -First 1
    if ($line) { return [int](($line -split ":")[-1]) }
    return 80
}

function Protect-Path([string]$Path, [string]$Inherit) {
    # Only Administrators (S-1-5-32-544) and SYSTEM (S-1-5-18): SIDs work on any Windows language
    $ErrorActionPreference = "Continue"
    & icacls.exe $Path /inheritance:r /grant:r "*S-1-5-32-544:$($Inherit)F" "*S-1-5-18:$($Inherit)F" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "Could not set permissions on $Path" }
}
function Protect-Folder([string]$Path) { Protect-Path $Path "(OI)(CI)" }
function Protect-File([string]$Path) { Protect-Path $Path "" }

function Assert-PortFree([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $proc = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
        Fail ("Port $Port is already used by '$($proc.ProcessName)' (PID $($listener.OwningProcess)). " +
              "Stop that program (for IIS: the 'World Wide Web Publishing Service'), " +
              "or install on another port:  install.bat -Port 8080")
    }
}

function Register-DayPayTasks {
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    # Server: at boot (no login needed), restart every minute if it ever stops, no time limit
    $serverAction = New-ScheduledTaskAction -Execute $Python `
        -Argument "`"$AppDir\deploy\windows\serve.py`"" -WorkingDirectory $AppDir
    $serverSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $ServerTask -Action $serverAction -Principal $principal `
        -Trigger (New-ScheduledTaskTrigger -AtStartup) -Settings $serverSettings `
        -Description "Day Pay HRMS web server (waitress)" -Force | Out-Null

    # Backup: daily 01:30; runs at next start if the PC was off at 01:30
    $backupAction = New-ScheduledTaskAction -Execute "cmd.exe" -WorkingDirectory $AppDir `
        -Argument "/c $Python manage.py backup >> $LogDir\backup.log 2>&1"
    $backupSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    Register-ScheduledTask -TaskName $BackupTask -Action $backupAction -Principal $principal `
        -Trigger (New-ScheduledTaskTrigger -Daily -At "01:30") -Settings $backupSettings `
        -Description "Day Pay HRMS nightly backup (database + documents)" -Force | Out-Null
}

function Set-WindowsEnvDefaults([string]$PgBin, [int]$Port) {
    Set-EnvDefault "HRMS_BACKUP_DIR" "'$BackupDir'"
    Set-EnvDefault "HRMS_PG_DUMP" "'$PgBin\pg_dump.exe'"
    Set-EnvDefault "DAYPAY_LISTEN" "0.0.0.0:$Port"
    Set-EnvDefault "DAYPAY_LOG_DIR" "'$LogDir'"
}

function Wait-ForApp([int]$Port) {
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$Port/accounts/login/"
            if ($response.StatusCode -eq 200) { return }
        } catch { }
        Start-Sleep -Seconds 2
    }
    Fail "Day Pay is not responding. See $LogDir\daypay.log"
}

function Test-Superuser {
    Push-Location $AppDir
    try {
        $ErrorActionPreference = "Continue"
        & $Python manage.py shell --no-imports -c "import sys; from accounts.models import User; sys.exit(0 if User.objects.filter(is_superuser=True).exists() else 1)" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally { Pop-Location }
}
