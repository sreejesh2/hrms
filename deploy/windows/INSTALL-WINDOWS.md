# Installing Day Pay on Windows

Day Pay runs on **one Windows PC or server on the factory network**. Office PCs
and phones open it in a browser; the ZKTeco machines send punches to it. No
Docker, and nothing needs the internet once it is installed.

> Linux (Ubuntu 24.04) is still the most tested option — see `deploy/INSTALL.md`.
> Use this guide when the server must be Windows.

## 1. What you need

| Item | Recommendation |
|------|----------------|
| Computer | A PC that **stays on 24/7** (not someone's daily desktop): 4+ cores, 8 GB RAM, SSD |
| Windows | Windows 10/11 (Pro) or Windows Server 2022/2025 |
| Network | Wired LAN, same network as the ZKTeco machines, **fixed IP address** |
| Power | A UPS |
| Internet | Only during installation (to download Python and PostgreSQL) |


**Power cuts:** in the PC's BIOS/UEFI setup (press Del or F2 while it starts),
set **"Restore on AC Power Loss"** (also called "AC Back" or "After Power
Failure") to **Power On**. Then the PC switches itself back on when power
returns, and Day Pay starts automatically. Punches made while it was off are
kept in the ZKTeco machines and uploaded when the PC is back.

## 2. Give the PC a fixed IP address

Reserve the PC's IP in the router (DHCP reservation), or set it in
**Settings → Network → Ethernet → IP assignment → Manual**.
The examples below use **192.168.1.10**.

## 3. Install

1. Copy the whole project folder to the PC (USB drive, or download the ZIP from
   GitHub and extract it), e.g. to `C:\Users\you\Downloads\hrms`.
2. Open `deploy\windows` and **double-click `install.bat`**.
3. Click **Yes** when Windows asks for administrator rights.
4. Wait (10–20 minutes the first time). At the end, type the **email and
   password for the first admin login**.

The installer:

- installs **Python 3.12** and **PostgreSQL 16** with `winget` if they are missing
- puts everything in `C:\DayPay` (`app`, `venv`, `backups`, `logs`, `secrets`)
- creates the database with a random password and writes `C:\DayPay\app\.env`
- creates the **DayPay Server** task: starts at boot **without anyone logging in**,
  restarts by itself if it stops
- creates the **DayPay Backup** task: every night at 01:30
- opens port 80 in Windows Firewall for the local network only
- turns off sleep, hibernate and **Fast Startup** (a sleeping PC records no punches,
  and Fast Startup can stop boot-time tasks from running)

When it finishes, open **http://192.168.1.10/** on any office PC and sign in.

**Port 80 already in use?** (IIS, another web app) The installer stops and tells
you which program uses it. Either stop that program, or install on another port:
open Command Prompt in `deploy\windows` and run `install.bat -Port 8080`
(then the address is `http://192.168.1.10:8080/`).

**No winget?** (Windows Server 2022 / older Windows 10) Install these by hand,
then run `install.bat` again:

- Python 3.12 from python.org — tick **"Add python.exe to PATH"** and
  **"Install for all users"** (Customize installation)
- PostgreSQL 16 from enterprisedb.com — remember the `postgres` password; the
  installer asks for it

## 4. Connect the ZKTeco machines

On each machine: **Menu → COMM → Cloud Server Setting**:

| Setting | Value |
|---------|-------|
| Server address | `192.168.1.10` |
| Server port | `80` (or the port you chose) |
| HTTPS / Domain name | Off |

In Day Pay go to **Settings → Devices**. Each new machine appears as
**"ZKTeco &lt;serial&gt; (pending approval)"** with status **Off** — check the
serial number, click **Edit**, tick **Active**, rename it. It then uploads its
stored punches.

## 5. Daily operations

| Task | How |
|------|-----|
| Is it running? | Open http://192.168.1.10/ — or **Task Scheduler** → *DayPay Server* → Status *Running* |
| Restart | Task Scheduler → *DayPay Server* → **End**, then **Run** (or restart the PC) |
| Logs | `C:\DayPay\logs\daypay.log` (and `backup.log`) |
| Backup now | Day Pay → **Settings → Access control → Backups → Create backup now** |
| Download backups | Same page → **Download** (database + documents) |

## 6. Backups

Every night at 01:30 (or at the next start if the PC was off) the database and
uploaded files are saved to `C:\DayPay\backups`, kept for 30 days. Only
Administrators can open that folder.

**Copy backups off the PC** — download them from the Backups page regularly
and keep them on another disk. For an automatic copy to a USB disk or network
share, edit the *DayPay Backup* task → **Actions** → **Edit** and add
`--copy-to E:\DayPayBackups` after `manage.py backup`.

**Restore** (only if something went wrong), in an Administrator PowerShell:

```powershell
Stop-ScheduledTask -TaskName "DayPay Server"
$env:PGPASSWORD = Get-Content C:\DayPay\secrets\postgres-superuser-password.txt
& "C:\Program Files\PostgreSQL\16\bin\pg_restore.exe" -h localhost -U postgres --clean --if-exists -d daypay C:\DayPay\backups\db-YYYYmmdd-HHMMSS.dump
tar -xzf C:\DayPay\backups\media-YYYYmmdd-HHMMSS.tar.gz -C C:\DayPay\app
Start-ScheduledTask -TaskName "DayPay Server"
```

(If PostgreSQL was installed before Day Pay, use the `postgres` password you
chose then instead of the file.)

## 7. Installing a new version

Copy the new project folder to the PC, open its `deploy\windows` folder and
**double-click `update.bat`**. It backs up first, keeps your settings, uploads
and data, applies database changes and restarts Day Pay.

## 8. Changing the server address later

If the PC's IP changed, the browser shows **"Bad Request (400)"**. Double-click
**`deploy\windows\fix-address.bat`** (in `C:\DayPay\app` or the project folder):
it adds the new IP to the settings, restarts Day Pay and prints the address.
`update.bat` does the same automatically. Then set the new address on every
ZKTeco machine (**Menu → COMM → Cloud Server Setting**).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Bad Request (400)" in the browser | The address you typed is not in `DJANGO_ALLOWED_HOSTS` in `.env` |
| "CSRF verification failed" on login | Add the address (with `http://`) to `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Page does not open from other PCs | Check the PC's IP; Windows Firewall rule **Day Pay (HTTP)** must exist |
| Machine never appears in Devices | Check the machine's server IP/port and that it can reach the PC |
| Machine appears but punches are missing | It is still **Off** — approve it (tick Active) |
| Nothing works after a Windows update | Restart the PC; check `C:\DayPay\logs\daypay.log` |
