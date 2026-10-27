# Installing Day Pay on the factory server

Day Pay runs on **one Linux computer on the factory network**. Office PCs and
phones open it in a browser; the ZKTeco machines send punches to it. Nothing
needs the internet once it is installed.

```
ZKTeco machines ──punches──►  Server (Ubuntu)   ◄──browser── Office PCs / phones
                              http://192.168.1.10
```

## 1. What you need

| Item | Recommendation |
|------|----------------|
| Computer | Mini PC or small server, 4+ cores, 8 GB RAM, SSD (e.g. Intel N100 / i3) |
| Operating system | **Ubuntu Server 24.04 LTS** (older versions are not supported) |
| Network | Wired LAN cable, same network as the ZKTeco machines |
| Power | A UPS, so a power cut does not stop payroll halfway |
| Backup disk | USB drive or NAS for copies of the nightly backup |

## 2. Give the server a fixed IP address

The ZKTeco machines must always find the server at the same address.
Either reserve an IP for the server in the router (DHCP reservation), or set a
static IP during Ubuntu install. The examples below use **192.168.1.10**.

## 3. Install

Copy the project folder to the server (USB drive, `scp`, or `git clone`), then:

```bash
cd hrms                         # the project folder
sudo bash deploy/install.sh --firewall
```

The script will:

1. install PostgreSQL, nginx and Python packages
2. set the clock to Asia/Dubai and turn on network time
3. create the database with a random password
4. write `/opt/daypay/app/.env` with a random secret key
5. start Day Pay as a service (starts on boot, restarts if it crashes)
6. set up a nightly backup at 01:30
7. ask you for the **first admin email and password**

`--firewall` allows only SSH and the web page (port 80). Leave it off if the
server also runs other software.

When it finishes, open **http://192.168.1.10/** on any office PC and sign in.

## 4. Connect the ZKTeco machines

On each machine: **Menu → COMM / Comm. → Cloud Server Setting** (name varies by model):

| Setting | Value |
|---------|-------|
| Server address | `192.168.1.10` (the server IP) |
| Server port | `80` |
| Domain name / HTTPS | Off |

Then in Day Pay go to **Settings → Devices**. Each new machine appears as
**"ZKTeco &lt;serial&gt; (pending approval)"** with status **Off**.
Check the serial number matches the machine, click **Edit**, tick **Active**,
and rename it (e.g. "Main gate"). The machine then uploads its stored punches.

> Machines are not trusted until you approve them. This stops anyone on the
> network from sending fake punches.

## 5. First-time setup in the app

Follow **Documentation** in the sidebar, in this order:

1. Company settings and masters (departments, locations, positions)
2. Roles and user logins
3. Calendars, shifts, holidays
4. Employees (with biometric ID = the PIN on the machine)
5. Leave types and balances
6. Salary components → structures → payroll periods

## 6. Daily operations

| Task | Command |
|------|---------|
| Is it running? | `sudo systemctl status daypay` |
| Live logs | `sudo journalctl -u daypay -f` |
| Restart | `sudo systemctl restart daypay` |
| Backup now | `sudo daypay-backup` |
| Backup log | `cat /var/log/daypay-backup.log` |

## 7. Backups

Every night at 01:30 the server saves the database and uploaded files to
`/var/backups/daypay/` and keeps 30 days.

**From the browser (Admins):** **Settings → Access control → Backups** lists
every backup with **Download** buttons (one for the database, one for the
documents) and a **Create backup now** button. Only users with the
*Manage backups* permission (the Admin role) can see this page, because backups
contain all personal and salary data. Every download is recorded in the
Activity log.

**Copy backups off the server.** If the server disk dies, backups on the same
disk die too. Either download them regularly from the Backups page, or mount a
USB drive / NAS and add `--copy-to` to the nightly job:

```bash
sudo mkdir -p /mnt/usb-backup && sudo chown daypay /mnt/usb-backup   # after mounting
sudo nano /etc/cron.d/daypay-backup
# change the line to:
30 1 * * * root /usr/local/sbin/daypay-backup --copy-to /mnt/usb-backup >> /var/log/daypay-backup.log 2>&1
```

**Restore** (only if something went wrong):

```bash
sudo systemctl stop daypay
sudo -u postgres pg_restore --clean --if-exists -d daypay /var/backups/daypay/db-YYYYmmdd-HHMMSS.dump
sudo tar -xzf /var/backups/daypay/media-YYYYmmdd-HHMMSS.tar.gz -C /opt/daypay/app
sudo chown -R daypay:daypay /opt/daypay/app/media
sudo systemctl start daypay
```

To restore a file you downloaded, copy it back to the server first
(e.g. `scp db-….dump user@192.168.1.10:/tmp/`) and use that path above.

## 8. Installing a new version

Copy the new project folder to the server, then from inside it:

```bash
sudo bash deploy/update.sh
```

It backs up first, keeps your settings, uploads and data, applies database
changes, and restarts.

## 9. Changing the server address later

Edit `/opt/daypay/app/.env`, update `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CSRF_TRUSTED_ORIGINS` and `SITE_URL`, then
`sudo systemctl restart daypay`. Also change the address on every ZKTeco machine.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Bad Request (400)" in the browser | The address you typed is not in `DJANGO_ALLOWED_HOSTS` in `.env` |
| "CSRF verification failed" on login | Add the address (with `http://`) to `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Machine never appears in Devices | Check the machine's server IP/port, and that it can ping the server |
| Machine appears but punches are missing | It is still **Off** — approve it (tick Active) |
| Page says 502 Bad Gateway | The app is down: `sudo journalctl -u daypay -n 50` |
