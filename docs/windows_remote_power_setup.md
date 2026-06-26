# Windows PC Remote Power Setup

This guide configures your Windows PC so it can be remotely powered on/off from the Raspberry Pi dashboard using a smart plug + SSH.

## How It Works

- A **Kasa smart plug** controls AC power to the PC
- **BIOS "boot after power loss"** makes the PC boot whenever power is restored
- **Windows OpenSSH Server** starts at boot (no login needed) so the Pi can SSH in to issue a graceful shutdown before cutting power
- **WSL Ubuntu** is the default SSH shell, giving you a full Linux environment over SSH

> **Where SSH actually runs (read this first — it's the #1 source of confusion).**
> SSH is the **Windows-native OpenSSH Server**, listening directly on the PC's
> LAN IP `0.0.0.0:22`. It is **NOT** an sshd running inside WSL, and there is
> **no `netsh portproxy` for port 22** — Windows binds 22 itself. When you
> connect, Windows' sshd launches `wsl.exe` as the login shell (Step 3), which
> drops you into WSL. That is why `utils/remote_machine_utils.py` uses
> `shell_type: "wsl"` and pipes the command via **stdin** with `ssh -T`: the
> remote "shell" is `wsl.exe`, which doesn't accept the `-c` flag normal SSH
> command execution uses. The shutdown command `shutdown.exe /s /t 0` is a
> Windows binary reachable from inside the WSL shell.
>
> (Any `netsh portproxy` rules you see, e.g. forwarding `:8080`, are unrelated —
> those forward a web service *into* WSL and have nothing to do with SSH/power.)

## Step 1: BIOS — Boot After Power Loss

1. Restart your PC and enter BIOS (typically **Del** or **F2** during boot)
2. Navigate to **Power Management**, **APM Configuration**, or similar
3. Find the setting called **AC Power Recovery**, **Restore on AC Power Loss**, or **After Power Failure**
4. Set it to **Power On** (sometimes called "Always On")
5. Save and exit

> This ensures the PC automatically boots whenever the smart plug restores power.

## Step 2: Install Windows OpenSSH Server

Open **PowerShell as Administrator** and run:

```powershell
# Install the OpenSSH Server feature
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Start the service
Start-Service sshd

# Set it to start automatically at boot
Set-Service -Name sshd -StartupType Automatic
```

Verify it's running:

```powershell
Get-Service sshd
```

You should see `Status: Running`.

> The OpenSSH Server runs as a Windows service — it starts at boot before any user logs in. No need to be signed into your Windows account.

## Step 3: Set Default SSH Shell to WSL Ubuntu

By default, SSHing into Windows drops you into `cmd.exe`. Change it to WSL:

```powershell
# PowerShell as Administrator
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\wsl.exe" -PropertyType String -Force
```

Now when the Pi SSHs in, it lands directly in your WSL Ubuntu environment.

## Step 4: Firewall Rule

Windows should have automatically created a firewall rule for OpenSSH, but verify:

```powershell
Get-NetFirewallRule -Name *ssh*
```

If no rule exists:

```powershell
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

> **IMPORTANT — harden this rule, or it *will* silently break.** The default
> OpenSSH rule is scoped to the **Private** network profile only. Windows
> periodically re-fingerprints the LAN and recreates the network as a *new*
> profile that defaults to **Public** (see the incident in the Troubleshooting
> section), at which point the Private-only rule no longer applies and SSH goes
> dark even though the service is running fine. Make the rule
> profile-independent and instead scope it by **source address** (home LAN +
> your Tailnet):
>
> ```powershell
> Set-NetFirewallRule -DisplayName 'OpenSSH SSH Server (sshd)' `
>   -Profile Any -RemoteAddress 192.168.1.0/24,100.64.0.0/10
> ```
>
> This is the configuration we settled on. See **Firewall scheme** and
> **Troubleshooting** at the bottom for the full rationale.

## Step 5: SSH Key Authentication

### On the Raspberry Pi

```bash
# Generate a key if you don't have one
ssh-keygen -t ed25519

# Try copying it to the PC (replace with your Windows username and PC IP)
ssh-copy-id your_windows_user@your_pc_ip
```

### If ssh-copy-id doesn't work (common on Windows)

Manually copy the Pi's public key to the PC:

1. On the Pi, display your public key:
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```

2. On the Windows PC, create/edit this file:
   ```
   C:\Users\your_username\.ssh\authorized_keys
   ```
   Paste the public key on a single line.

### Important: Admin User Gotcha

If your Windows user is in the **Administrators** group (most users are), Windows OpenSSH ignores the per-user `authorized_keys` file and looks at a system-wide file instead.

**Option A** — Use the system-wide file:

Append your Pi's public key to:
```
C:\ProgramData\ssh\administrators_authorized_keys
```

Then set permissions (PowerShell as Admin):
```powershell
icacls "C:\ProgramData\ssh\administrators_authorized_keys" /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
```

**Option B** — Disable the admin key override:

Edit `C:\ProgramData\ssh\sshd_config` and comment out the last two lines:
```
# Match Group administrators
#   AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys
```

Then restart the service:
```powershell
Restart-Service sshd
```

## Step 6: WSL Systemd (Optional)

If you want systemd services inside WSL to start automatically:

In WSL Ubuntu, edit `/etc/wsl.conf`:
```ini
[boot]
systemd=true
```

Then restart WSL from PowerShell:
```powershell
wsl --shutdown
```

## Step 7: Verify Everything

From the Raspberry Pi, run:

```bash
ssh your_windows_user@your_pc_ip
```

You should land in a WSL Ubuntu bash shell with **no password prompt**.

Then test that the shutdown command works from within WSL:

```bash
shutdown.exe /s /t 0
```

This should immediately begin shutting down the Windows PC.

## Step 8: Configure the Pi Dashboard

On the Raspberry Pi, create the file `config/remote_machine_config.local.json` in the dashboard directory:

```json
{
  "remote_machines": [
    {
      "id": "desktop_pc",
      "enabled": true,
      "host": "YOUR_PC_STATIC_IP",
      "ssh_user": "YOUR_WINDOWS_USERNAME",
      "plug_ip": "YOUR_KASA_PLUG_IP"
    }
  ]
}
```

Use the static IP you reserved in your router for the PC.

Then restart the dashboard:

```bash
sudo systemctl restart pi-dashboard.service
```

Your PC should now appear as a card in the "Remote Machines" group on the dashboard.

> **Note on `host`:** we deliberately keep `host` set to the PC's **LAN IP**
> (`192.168.1.89`), not its Tailscale IP — the LAN path is faster locally and
> avoids the Tailscale hop. The firewall rule below still allows the Tailnet so
> any peer (phone/laptop, local or abroad) can SSH in manually via the Tailscale
> address; the dashboard just doesn't need to.

---

## Firewall scheme (the durable fix)

**The rule we run:**

```powershell
Set-NetFirewallRule -DisplayName 'OpenSSH SSH Server (sshd)' `
  -Profile Any -RemoteAddress 192.168.1.0/24,100.64.0.0/10
```

**What each piece does and why:**

- **`-Profile Any`** — decouples SSH reachability from Windows' network *profile*
  classification (Public/Private/Domain). The default OpenSSH rule was
  `Private`-only, which is the trap (see Troubleshooting). With `Any`, a network
  getting re-classified as Public can no longer kill SSH.
- **`-RemoteAddress 192.168.1.0/24,100.64.0.0/10`** — replaces the lost
  profile-based protection with something stronger and explicit: scope by
  **source address**. Only two source ranges may connect:
  - `192.168.1.0/24` — the **home LAN** (the dashboard on the Pi reaches the PC
    this way, fast, no Tailscale).
  - `100.64.0.0/10` — the **entire Tailnet**. This is the RFC 6598 CGNAT block
    (range `100.64.0.0`–`100.127.255.255`) that Tailscale assigns *all* node IPs
    from, so it provably matches every current and future peer. Tailscale's own
    auth/ACLs gate who is even in the tailnet.
- **Net effect:** home LAN + any of my Tailscale devices (local or abroad) can
  SSH; **every other network is blocked**. A hostile network (coffee shop
  `10.x`/`172.x`) matches neither range, so port 22 stays dark there — we keep
  the security benefit of "untrusted networks can't reach me" while being
  immune to the profile-flip bug.

**Reference IPs (this tailnet):**

| Device      | Tailscale IP     | Role                          |
|-------------|------------------|-------------------------------|
| pi5server   | `100.75.30.50`   | The dashboard host (the Pi)   |
| nathan-r16  | `100.110.171.93` | The Alienware R16 (this PC)   |

Why `-Profile Any` + source scoping beats the alternatives:
- *Just flipping the network back to Private* fixes today but breaks again on the
  next profile re-fingerprint.
- *`-Profile Any` with no address scope* works but exposes port 22 on **any**
  network the machine joins, including untrusted ones — we don't want that.

---

## Troubleshooting: dashboard shows OFFLINE but the PC is on

The dashboard's online/offline status is just a **TCP connect to port 22**
(`utils/remote_machine_utils.py:check_machine_online`). "Shows off but it's on"
always means *nothing answered on `<host>:22`* — it is never a dashboard-code
problem.

### Quick recovery runbook (do these in order)

When the R16 shows offline but you know it's on, work down this list — each step
is also a *diagnosis* (the first one that changes the outcome tells you the
cause):

1. **Is port 22 reachable from the Pi?** This is the single source of truth —
   it's literally what the dashboard checks.
   ```bash
   timeout 3 bash -c 'cat < /dev/null > /dev/tcp/192.168.1.89/22' && echo OPEN || echo CLOSED
   ```
   If `OPEN`, the dashboard should already be flipping to online (give it one
   ~5s poll cycle, or reload). If `OPEN` but still shows offline, restart the
   dashboard: `sudo systemctl restart pi-dashboard.service`. If `CLOSED`,
   continue.

2. **Is the PC even on the network?** (rules out sleep / new DHCP IP)
   ```bash
   ping -c 2 192.168.1.89
   ```
   No reply → the PC is off/asleep, or its IP changed. Wake it / power-cycle the
   plug; verify its IP (reserve a static DHCP lease so this can't drift).

3. **On the PC (admin PowerShell): is sshd up and listening?**
   ```powershell
   Get-Service sshd
   netstat -ano | findstr :22
   Start-Service sshd; Set-Service sshd -StartupType Automatic   # if not Running/Automatic
   ```
   Expect `Running` and `0.0.0.0:22 ... LISTENING`.

4. **If sshd is Running but port 22 is still CLOSED → it's the firewall** (the
   usual culprit; see the 2026-06-26 incident). Re-apply the durable rule and
   confirm:
   ```powershell
   Set-NetFirewallRule -DisplayName 'OpenSSH SSH Server (sshd)' `
     -Profile Any -RemoteAddress 192.168.1.0/24,100.64.0.0/10
   Get-NetConnectionProfile        # sanity-check what profile the LAN is on now
   ```

5. **Re-test step 1 from the Pi.** Open → done. Still closed → fall through to the
   detailed diagnostics and decision table below.

### Detailed diagnosis

Diagnose from the **Pi**, top to bottom:

```bash
# 1. Is the host even up / on the network?  (expect replies + a REACHABLE arp entry)
ping -c 2 192.168.1.89
ip neigh show 192.168.1.89

# 2. Is port 22 open?  (this is the actual check the dashboard does)
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/192.168.1.89/22' && echo OPEN || echo CLOSED/FILTERED
```

Then on the **Windows PC** (admin PowerShell):

```powershell
Get-Service sshd                                   # is the service Running?
netstat -ano | findstr :22                         # is it LISTENING on 0.0.0.0:22 ?
Get-NetConnectionProfile                            # is the active NIC Public or Private?
Get-NetFirewallRule -DisplayName 'OpenSSH SSH Server*' |
  Format-Table DisplayName,Enabled,Profile,Action   # which profiles does the allow-rule cover?
```

**Decision table:**

| Symptom | Cause | Fix |
|---|---|---|
| ping fails / no arp entry | PC off, asleep, or new DHCP IP | wake it; reserve a static lease; check `host` in config |
| `Get-Service sshd` not Running | service stopped / set to Manual | `Start-Service sshd; Set-Service sshd -StartupType Automatic` |
| `netstat` shows only `127.0.0.1:22` | `ListenAddress 127.0.0.1` in `sshd_config` | remove it from `C:\ProgramData\ssh\sshd_config`, `Restart-Service sshd` |
| host up + sshd Running + port **CLOSED/FILTERED** | **firewall** (the usual case) | apply the **Firewall scheme** rule above |

### The actual incident — 2026-06-26

Symptoms: dashboard showed the R16 offline while it was on and in use; SSH timed
out. From the Pi: **ping succeeded, arp REACHABLE, but port 22 CLOSED/FILTERED.**
On Windows: `sshd` was **Running**, listening correctly on `0.0.0.0:22`. The
giveaway was `Get-NetConnectionProfile`: the Wi-Fi network was named
**"HighLatency 3"** with `NetworkCategory: Public`, while the OpenSSH firewall
rule was scoped to **`Private` only**.

Root cause: Windows fingerprints a network (mainly by the default gateway's MAC);
when that signature shifts — router reboot/firmware update, PC booting before the
gateway is ready, mesh AP roaming, or a Windows Update touching the network list —
it files the LAN as a **brand-new profile** (hence the incrementing name
"HighLatency", "…2", "…3"), and **new profiles default to Public**. It "worked for
months" because the old profile was Private; it broke the morning a new Public
profile was created. The fix was the **Firewall scheme** above (`-Profile Any` +
source-address scoping), which removes the dependency on the profile label
entirely.
