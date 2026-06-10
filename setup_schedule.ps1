# Airplay - register a daily price-monitor schedule (runs 08:00 and 20:00).
# How to run (from THIS folder, note the leading .\ ):
#     powershell -ExecutionPolicy Bypass -File .\setup_schedule.ps1
# No administrator rights needed (it creates a task for the current user).

$ErrorActionPreference = "Stop"
$bat = Join-Path $PSScriptRoot "run_monitor.bat"

if (-not (Test-Path $bat)) {
    Write-Host "ERROR: run_monitor.bat not found in this folder." -ForegroundColor Red
    Write-Host "Put setup_schedule.ps1 in the same folder as scraper.py / run_monitor.bat."
    exit 1
}

$action   = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $PSScriptRoot
$trigger1 = New-ScheduledTaskTrigger -Daily -At "08:00"
$trigger2 = New-ScheduledTaskTrigger -Daily -At "20:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$params = @{
    TaskName    = "AirplayPriceMonitor"
    Action      = $action
    Trigger     = @($trigger1, $trigger2)
    Settings    = $settings
    Description = "Run flight-deal scraper at 08:00 and 20:00 daily and notify lowest-price changes"
    Force       = $true
}
Register-ScheduledTask @params | Out-Null

Write-Host "OK - scheduled task 'AirplayPriceMonitor' created (daily 08:00 and 20:00)." -ForegroundColor Green
Write-Host "Test it now:  Start-ScheduledTask -TaskName 'AirplayPriceMonitor'"
Write-Host "Remove it:    Unregister-ScheduledTask -TaskName 'AirplayPriceMonitor' -Confirm:`$false"
