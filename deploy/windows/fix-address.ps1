<#
Day Pay HRMS - the server's IP address changed ("Bad Request (400)").

Double-click deploy\windows\fix-address.bat. It adds this PC's current IP to
the settings, restarts Day Pay and shows the address to use. Data is untouched.
#>
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
. "$PSScriptRoot\common.ps1"

Assert-Administrator
if (-not (Test-Path $EnvFile)) { Fail "Day Pay is not installed yet. Run install.bat first." }

$Port = Get-ConfiguredPort
Say "Adding this PC's current address to the settings"
$Ip = Sync-EnvAddresses $Port
Protect-File $EnvFile

Say "Restarting Day Pay"
Stop-DayPayServer
Start-ScheduledTask -TaskName $ServerTask
Wait-ForApp $Port

$Suffix = ""
if ($Port -ne 80) { $Suffix = ":$Port" }
Say "Done. Open http://$Ip$Suffix/ in the browser."
Write-Host ""
Write-Host "On every ZKTeco machine set: Menu > COMM > Cloud Server Setting"
Write-Host "    Server address = $Ip    Server port = $Port"
Write-Host ""
Write-Host "Give this PC a fixed IP (router DHCP reservation) so it does not change again."
