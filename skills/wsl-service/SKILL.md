---
name: wsl-service
description: Turn a project in WSL into a managed systemd service, keep the WSL VM alive without an open terminal, and expose the service to the local network under either mirrored or NAT networking. Use when asked to run an app as a service, daemonize it, expose a WSL port to the LAN, keep services running after closing terminals, or debug why a WSL service is unreachable from LAN or localhost.
---

# Creating WSL services

Machine-specific state (networking mode, existing units, scheduled tasks,
allowed ports) belongs in project memory, not here — check memory first,
then verify on the machine; don't assume.

## 0. Detect the machine's setup

```bash
systemctl is-system-running                  # systemd enabled in this distro?
loginctl show-user $USER | grep Linger       # units start at boot / survive logout?
ip -4 addr show eth0                         # 172.16-31.x.x => NAT; LAN-subnet address => mirrored
cat "$(wslpath "$(cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')")/.wslconfig" 2>/dev/null
```

Enable what's missing: `loginctl enable-linger $USER`; systemd via
`[boot] systemd=true` in `/etc/wsl.conf` (needs a WSL restart).

## 1. systemd user unit

Create `~/.config/systemd/user/<name>.service`, keep a copy in the repo
(e.g. `scripts/<name>.service`), and look at existing units in that
directory first to match local conventions:

```ini
[Unit]
Description=<project> service

[Service]
Type=simple
WorkingDirectory=<project dir>
Environment=PATH=<conda or toolchain bin>:/usr/local/bin:/usr/bin:/bin
ExecStart=/bin/direnv exec <project dir> python -m <module> --host 0.0.0.0
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

`direnv exec <dir>` activates the project's `.envrc` (conda env, etc.);
substitute the project's own launcher if it doesn't use direnv. Bind
`0.0.0.0` if the service should be LAN-reachable.

```bash
cp scripts/<name>.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now <name>
systemctl --user status <name>        # journalctl --user -u <name> for logs
```

Manage services only through systemctl — never as background shells — and
restart the unit after code changes.

## 2. Keep the WSL VM alive

WSL2 stops the VM shortly (~1 min) after the last client process exits.
Terminals, VS Code servers, and `wsl.exe` invocations are clients; systemd
services and linger are NOT — closing the last terminal kills every
service. Logon-triggered scheduled tasks that briefly call `wsl.exe` boot
the VM but don't keep it up.

Fix: hold one hidden client open forever. Drop this into the Windows
Startup folder (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
wsl-keepalive.vbs`, no admin needed), and run it once immediately:

```vbs
CreateObject("Wscript.Shell").Run "wsl.exe --exec sleep infinity", 0, False
```

Verify with `pgrep -f 'sleep infinity'` inside WSL.

## 3. LAN exposure

Either way, the service binds `0.0.0.0` and Windows Firewall needs an
inbound rule for the port (elevated, see §4):

```powershell
netsh advfirewall firewall add rule name=<Name><port> dir=in action=allow protocol=TCP localport=<port>
```

### Mirrored networking (`networkingMode=mirrored`, Win11 22H2+)

WSL shares the host's interfaces: a `0.0.0.0` bind is LAN-reachable with
no proxy. Additionally allow the port in the Hyper-V firewall (one rule
can carry several ports; extend an existing one with
`Set-NetFirewallHyperVRule` before creating a new one):

```powershell
New-NetFirewallHyperVRule -Name <Name> -DisplayName "..." -Direction Inbound
    -VMCreatorId '{40E0AC32-B90B-4029-90E9-0AEB6D5069D4}' -Protocol TCP
    -LocalPorts <ports> -Action Allow
```

Caveat: Windows and WSL share ports — a Windows-side listener on the port
silently wins and the WSL bind loses. Check with
`Get-NetTCPConnection -LocalPort <port> -State Listen`.

### NAT networking (default; the only option on Windows 10)

Windows forwards localhost automatically; LAN clients need a portproxy:

```powershell
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=<port> connectaddress=<WSL IP> connectport=<port>
```

- `listenaddress=0.0.0.0`, never the LAN IP — DHCP renumbering silently
  breaks IP-specific listeners.
- `connectaddress=<WSL IP>` (`hostname -I`), **never 127.0.0.1** — at boot
  the proxy binds the port before WSL's localhost relay can, then connects
  back into its own listener and every request hangs.
- The WSL IP changes across WSL restarts, so the rule must be refreshed:
  keep one elevated logon scheduled task running a script that re-`set`s
  every proxied port to the current `wsl.exe hostname -I` (check memory /
  Task Scheduler for an existing one before creating a second). On-demand:
  `schtasks.exe /run /tn <task>`.
- App-level: derive self-links from the request `Host` header, not a
  configured base URL, so localhost and LAN clients both get working links.

### Migrating NAT → mirrored

Delete all portproxy rules (`netsh interface portproxy reset`) and disable
the refresh task first — leftover Windows-side listeners occupy the very
ports WSL then serves directly. Keep the Windows Firewall rules, add the
Hyper-V firewall rule, set `[wsl2] networkingMode=mirrored` in
`%USERPROFILE%\.wslconfig`, then `wsl --shutdown` — which kills the
session you are running in: hand that step to the user, and verify
afterwards in a fresh session. Update memory to the new mode so the proxy
machinery is never resurrected.

## 4. Elevated Windows commands

Unelevated `netsh` writes fail, and nested inline quoting mangles
arguments (quoted rule names vanish). Pattern: write a `.ps1` to the
Windows Temp directory, have it `Start-Transcript` to a log, then:

```bash
powershell.exe -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','C:\\...\\<script>.ps1'"
```

This pops a UAC prompt — tell the user to approve it. `Start-Process`
returns immediately, so poll for the effect (or the transcript log)
before declaring success.

## 5. Verify before declaring done

```bash
systemctl --user status <name>                    # unit healthy
curl -s http://127.0.0.1:<port>/<health>          # WSL-local
curl -s http://<windows-lan-ip>:<port>/<health>   # LAN path
powershell.exe -NoProfile -Command "(Invoke-WebRequest -Uri http://localhost:<port>/<health> -UseBasicParsing -TimeoutSec 5).StatusCode"   # Windows localhost
```

Windows LAN IP: `powershell.exe -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4).IPAddress"`
(ignore `169.254.*`, `127.0.0.1`, and the `vEthernet (WSL)` address). The
LAN path is only proven from a second device; curl from inside WSL is a
good proxy but shares the machine's firewall context.
