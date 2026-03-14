# Windows PC Remote Power Setup

This guide configures your Windows PC so it can be remotely powered on/off from the Raspberry Pi dashboard using a smart plug + SSH.

## How It Works

- A **Kasa smart plug** controls AC power to the PC
- **BIOS "boot after power loss"** makes the PC boot whenever power is restored
- **Windows OpenSSH Server** starts at boot (no login needed) so the Pi can SSH in to issue a graceful shutdown before cutting power
- **WSL Ubuntu** is the default SSH shell, giving you a full Linux environment over SSH

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

## Step 8: Find Your PC's IP Address

On the Windows PC, run:

```powershell
ipconfig
```

Look for the **Wi-Fi adapter** section and note the **IPv4 Address** (e.g., `192.168.1.42`).

> Consider assigning a static IP or DHCP reservation in your router so the address doesn't change.

## Step 9: Configure the Pi Dashboard

On the Raspberry Pi, create the file `config/remote_machine_config.local.json` in the dashboard directory:

```json
{
  "remote_machines": [
    {
      "id": "desktop_pc",
      "enabled": true,
      "host": "YOUR_PC_IP",
      "ssh_user": "YOUR_WINDOWS_USERNAME",
      "plug_ip": "YOUR_KASA_PLUG_IP"
    }
  ]
}
```

Then restart the dashboard:

```bash
sudo systemctl restart pi-dashboard.service
```

Your PC should now appear as a card in the "Remote Machines" group on the dashboard.
