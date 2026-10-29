<#
Day Pay HRMS - install a new version on Windows (run from the NEW code folder).

Easiest: double-click deploy\windows\update.bat in the new code folder.
Takes a backup first; keeps settings (.env), uploads and the database.
#>
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
. "$PSScriptRoot\common.ps1"

Assert-Administrator
$SrcDir = (Resolve-Path "$PSScriptRoot\..\..").Path
if (-not (Test-Path "$SrcDir\manage.py")) { Fail "Run this from inside the new Day Pay project folder." }
if (-not (Test-Path $EnvFile)) { Fail "Day Pay is not installed yet. Run install.bat first." }
if ($SrcDir -eq $AppDir) { Fail "Run this from the new code folder, not from $AppDir." }

$Port = Get-ConfiguredPort
$PgBin = Find-PgBin
if (-not $PgBin) { Fail "PostgreSQL was not found in C:\Program Files\PostgreSQL." }

Say "Backing up before update"
Invoke-Manage @("backup")

Say "Stopping Day Pay"
Stop-DayPayServer

Say "Copying new code"
Copy-AppCode $SrcDir
Set-WindowsEnvDefaults $PgBin $Port
Protect-File $EnvFile

Say "Updating packages, database and static files"
Invoke-Checked $Python @("-m", "pip", "install", "-q", "-r", "$AppDir\requirements.txt")
Invoke-Manage @("migrate", "--noinput")
Invoke-Manage @("collectstatic", "--noinput", "-v", "0")
Invoke-Manage @("check", "--deploy", "--fail-level", "ERROR")

Say "Starting Day Pay"
Register-DayPayTasks
Start-ScheduledTask -TaskName $ServerTask
Wait-ForApp $Port

Say "Updated - Day Pay is running."
