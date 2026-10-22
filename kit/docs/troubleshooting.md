# WoP server: troubleshooting

> **First try the easy way:** use **Start WoP Server** again. Every start checks whether the other computers on
> your network can join, and if something blocks them it asks *"Do you want to allow this?"*. Answer yes (and click
> **Yes** on the Windows question that follows). This page is for when that isn't enough, or when you want to see
> for yourself what's going on.

All commands below are for **PowerShell** on the computer that runs the server (press the Windows key, type
*PowerShell*, open it). Mac: see [Mac](#mac) at the bottom. Paste a block, press Enter. Commands that change
something are marked **(admin)**: run those in PowerShell opened with *right-click → Run as administrator*.

- [Start here: the setup block](#start-here-the-setup-block)
- [Quick check: everything at once](#quick-check-everything-at-once)
- [See your server](#see-your-server) · [See your settings](#see-your-settings) ·
  [See your network](#see-your-network) · [See your firewall](#see-your-firewall)
- [Test from another computer](#test-from-another-computer)
- [Fixes for common problems](#fixes-for-common-problems)
- [Mac](#mac)

## Where everything is

| What | Where (in `%LOCALAPPDATA%\WoPServer`) |
|------|-------|
| Kit settings: port, server name, game folder | `install.json` |
| The script that runs the game server (rewritten on every start) | `run-server.cmd` |
| Server settings: name, passwords, players, startup game | `home\wop\server-friends.cfg` |
| Startup bot lineup / the last game mode Claude or you switched to | `home\wop\teams.cfg` / `home\wop\mode.cfg` |
| Server log (everything the server window shows) | `home\wop\qconsole.log` |
| Game log (kills, joins, scores) | `home\wop\games.log` |
| The game itself (unless you already had WoP installed) | `game\` |

The server uses **UDP port 27960** (only UDP, no TCP). The game's LAN list only looks at ports 27960 to 27963.

## Start here: the setup block

Paste this first, every time you open a new PowerShell window. The other blocks use `$wop`, `$port`,
`$program` and `Ask-WoP` from it.

```powershell
$wop = "$env:LOCALAPPDATA\WoPServer"
$install = Get-Content "$wop\install.json" -Raw | ConvertFrom-Json
$port = $install.port
$program = Join-Path $install.game_dir "wopded.x86_64.exe"
$rcon = (Select-String -Path "$wop\home\wop\server-friends.cfg" -Pattern '^\s*seta?\s+rconpassword\s+"([^"]*)"' |
         Select-Object -Last 1).Matches[0].Groups[1].Value

# Asks the server something, the same way the game does. Ask-WoP "getinfo" or Ask-WoP "getinfo" 192.168.1.50
function Ask-WoP([string]$Text, [string]$Address = "127.0.0.1", [int]$Port = $port) {
  $udp = New-Object System.Net.Sockets.UdpClient
  $udp.Client.ReceiveTimeout = 3000
  $bytes = [byte[]](255, 255, 255, 255) + [Text.Encoding]::ASCII.GetBytes($Text)
  [void]$udp.Send($bytes, $bytes.Length, $Address, $Port)
  $from = New-Object Net.IPEndPoint([Net.IPAddress]::Any, 0)
  $answer = ""
  try {
    while ($true) {
      $answer += [Text.Encoding]::ASCII.GetString($udp.Receive([ref]$from)).Substring(4) -replace '^print\n', ''
      $udp.Client.ReceiveTimeout = 300
    }
  } catch { } finally { $udp.Close() }
  if ($answer) { $answer -replace '\^[0-9]', '' } else { "No answer from ${Address}:$Port" }
}
"Port $port, server program $program"
```

## Quick check: everything at once

After the setup block, paste this. It prints one line per check with **OK** or **PROBLEM**; the
[fixes](#fixes-for-common-problems) below explain what to do about each problem.

```powershell
function Check($ok, $text) { if ($ok) { "OK       $text" } else { "PROBLEM  $text" } }
$listening = Get-NetUDPEndpoint -LocalPort $port -ErrorAction SilentlyContinue
Check $listening "server running on UDP port $port"
if ($listening) {
  $owner = (Get-Process -Id $listening[0].OwningProcess).Path
  Check ($owner -eq $program) "port $port belongs to the server ($owner)"
  Check ((Ask-WoP "getinfo") -like "infoResponse*") "server answers"
}
Check ($port -ge 27960 -and $port -le 27963) "port $port is one the LAN list searches (27960-27963)"
$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -ne 'WellKnown' -and $_.IPAddress -notlike '169.254.*' }
Check $ips "network address: $(($ips | ForEach-Object { "$($_.IPAddress)/$($_.PrefixLength) ($($_.InterfaceAlias))" }) -join ', ')"
$active = Get-NetConnectionProfile | ForEach-Object { "$($_.NetworkCategory)" -replace 'DomainAuthenticated', 'Domain' }
"INFO     network type: $($active -join ', ')"
$profiles = Get-NetFirewallProfile -PolicyStore ActiveStore | Where-Object { $active -contains "$($_.Name)" }
foreach ($p in $profiles) {
  if ("$($p.Enabled)" -ne 'True') { "INFO     Windows Firewall is off for $($p.Name)"; continue }
  Check ("$($p.AllowInboundRules)" -ne 'False') "$($p.Name): firewall doesn't block ALL incoming connections"
  Check ("$($p.AllowLocalFirewallRules)" -ne 'False') "$($p.Name): firewall rules on this computer count (not managed by an organization)"
}
$rule = Get-NetFirewallRule -DisplayName "WoP Server Kit" -ErrorAction SilentlyContinue | Select-Object -First 1
Check $rule "the 'WoP Server Kit' firewall rule exists"
if ($rule) {
  Check ("$($rule.Enabled)" -eq 'True' -and "$($rule.Action)" -eq 'Allow') "the rule is on and allows"
  Check ((($rule | Get-NetFirewallApplicationFilter).Program) -eq $program) "the rule is for the server program"
}
$blocks = Get-NetFirewallApplicationFilter | Where-Object Program -eq $program | Get-NetFirewallRule |
          Where-Object { "$($_.Action)" -eq 'Block' -and "$($_.Enabled)" -eq 'True' }
Check (-not $blocks) "no firewall rule blocks the server $(($blocks | ForEach-Object { "('$($_.DisplayName)')" }) -join ' ')"
$others = Get-CimInstance -Namespace root/SecurityCenter2 -ClassName FirewallProduct -ErrorAction SilentlyContinue
if ($others) { "INFO     other firewall installed: $(($others.displayName) -join ', ') (may need its own exception)" }
```

## See your server

```powershell
# Is it running? Which program has the port?
Get-Process wopded* -ErrorAction SilentlyContinue | Format-Table Id, StartTime, Path -AutoSize
Get-NetUDPEndpoint -LocalPort $port -ErrorAction SilentlyContinue |
  Select-Object LocalAddress, LocalPort, @{n = 'Program'; e = { (Get-Process -Id $_.OwningProcess).Path } }

# Name, map, game mode, number of players (what the LAN list shows)
Ask-WoP "getinfo"
# All public settings and the player list
Ask-WoP "getstatus"
# Players with their network addresses and ping (uses the rcon password)
Ask-WoP "rcon $rcon status"

# The last 40 lines of the server log; add -Wait to keep following it (Ctrl+C stops)
Get-Content "$wop\home\wop\qconsole.log" -Tail 40
```

You can send any server console command with `Ask-WoP "rcon $rcon <command>"`, for example
`Ask-WoP "rcon $rcon g_password"` shows the current join password.

## See your settings

```powershell
Get-Content "$wop\install.json"
Get-Content "$wop\run-server.cmd"
# The settings in server-friends.cfg that are really used (no comments)
Select-String -Path "$wop\home\wop\server-friends.cfg" -Pattern '^\s*(set|seta|map|exec)\s' | ForEach-Object { $_.Line.Trim() }
# Open it to edit (restart the server afterwards)
notepad "$wop\home\wop\server-friends.cfg"
```

## See your network

```powershell
# This computer's addresses; the players must be on the same network (e.g. all 192.168.1.x)
Get-NetIPAddress -AddressFamily IPv4 | Where-Object PrefixOrigin -ne WellKnown |
  Format-Table InterfaceAlias, IPAddress, PrefixLength -AutoSize
# Network type (Private / Public / Domain) per connection
Get-NetConnectionProfile | Format-Table InterfaceAlias, Name, NetworkCategory -AutoSize
# Connected adapters; a VPN shows up here too
Get-NetAdapter | Where-Object Status -eq Up | Format-Table Name, InterfaceDescription, LinkSpeed -AutoSize
```

## See your firewall

```powershell
# The kit's rule and what it allows
$r = Get-NetFirewallRule -DisplayName "WoP Server Kit"
$r | Format-List DisplayName, Enabled, Direction, Action, Profile
($r | Get-NetFirewallApplicationFilter).Program
($r | Get-NetFirewallPortFilter).Protocol
($r | Get-NetFirewallAddressFilter).RemoteAddress

# Every rule for the server program; an enabled Inbound + Block rule wins over the allow rule
Get-NetFirewallApplicationFilter | Where-Object Program -like "*wopded*" | Get-NetFirewallRule |
  Format-Table DisplayName, Enabled, Direction, Action, Profile -AutoSize

# The firewall per network type. AllowInboundRules False = "block all incoming connections"
Get-NetFirewallProfile -PolicyStore ActiveStore |
  Format-Table Name, Enabled, DefaultInboundAction, AllowInboundRules, AllowLocalFirewallRules -AutoSize

# Other firewalls / antivirus (Norton, Bitdefender, ...)
Get-CimInstance -Namespace root/SecurityCenter2 -ClassName FirewallProduct | Select-Object displayName
Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | Select-Object displayName
```

## Test from another computer

The real test: run this on a **player's** Windows computer (it doesn't need the kit). Put the server's address
(from [See your network](#see-your-network)) in `$ip`. Testing on the server computer itself proves nothing,
because Windows always lets a computer talk to itself.

```powershell
$ip = "192.168.1.50"; $port = 27960
$udp = New-Object System.Net.Sockets.UdpClient; $udp.Client.ReceiveTimeout = 3000
$bytes = [byte[]](255, 255, 255, 255) + [Text.Encoding]::ASCII.GetBytes("getinfo")
[void]$udp.Send($bytes, $bytes.Length, $ip, $port)
$from = New-Object Net.IPEndPoint([Net.IPAddress]::Any, 0)
try { [Text.Encoding]::ASCII.GetString($udp.Receive([ref]$from)).Substring(4) } catch { "No answer: blocked or not reachable" } finally { $udp.Close() }
```

- **`infoResponse ...` with the server name:** the network and firewall are fine. If the server isn't in the LAN
  list, join with `/connect <address>` in the game console (**~**).
- **No answer:** something blocks it. Check the server computer's firewall ([quick check](#quick-check-everything-at-once)),
  then the network ([No answer from the other computers](#no-answer-from-the-other-computers-but-the-firewall-is-fine)).

## Fixes for common problems

### The "WoP Server Kit" firewall rule is missing, off or wrong
Use **Start WoP Server** and answer yes. By hand **(admin)**, after the setup block:
```powershell
Remove-NetFirewallRule -DisplayName "WoP Server Kit" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "WoP Server Kit" -Direction Inbound -Action Allow -Protocol UDP `
  -Program $program -RemoteAddress LocalSubnet -Profile Any
```
In an admin window `$env:LOCALAPPDATA` can point to another user's folder: check that the
`Port ..., server program ...` line of the setup block shows *your* folder, or type the path yourself.

### A firewall rule blocks the server
Usually made when someone clicked **Cancel** when Windows asked whether to allow the server. **(admin)**:
```powershell
Get-NetFirewallApplicationFilter | Where-Object Program -like "*wopded*" | Get-NetFirewallRule |
  Where-Object { "$($_.Action)" -eq 'Block' } | Remove-NetFirewallRule
```

### Windows blocks ALL incoming connections
(Windows Security → Firewall & network protection → your network → *"Blocks all incoming connections"*.) **(admin)**:
```powershell
Set-NetFirewallProfile -Profile Domain, Private, Public -AllowInboundRules True
```
If `AllowLocalFirewallRules` shows `False`, a school or company manages the firewall; only they can allow it.

### Another firewall (Norton, Bitdefender, McAfee, ...)
Windows' rules don't count for it. In its settings, allow the program shown as `$program` (the
`wopded.x86_64.exe` in the WoP Server's `game` folder), or allow UDP port 27960 on your home network.

### The players can join with /connect but don't see the server in the LAN list
Joining by address always works: in the game's Multiplayer screen click **Specify** and enter the address and port
from the *How to join* window (or press ~ and type `/connect <address>`). To make the LAN list work:
- The port must be 27960 to 27963 (see `$port`). To change it: set `"port": 27960` in `install.json`, then use
  **Start WoP Server**.
- Everyone must be on the same network (the first three numbers of the address, like `192.168.1.`, are the same).
- Some routers don't pass the LAN list's search between Wi-Fi and cable.
- **A virtual network adapter on the player's computer** (WSL, Hyper-V, VirtualBox, VMware, a VPN) can take the
  LAN list's search: Windows sends it out of only one adapter, the connected one with the lowest metric. Check on
  the **player's** computer; the first line is the adapter the search uses:
  ```powershell
  Get-NetRoute -DestinationPrefix 255.255.255.255/32 -AddressFamily IPv4 | ForEach-Object {
    $if = Get-NetIPInterface -InterfaceIndex $_.InterfaceIndex -AddressFamily IPv4
    [pscustomobject]@{ Adapter = $_.InterfaceAlias; Metric = $_.RouteMetric + $if.InterfaceMetric; State = $if.ConnectionState }
  } | Where-Object State -eq Connected | Sort-Object Metric | Format-Table -AutoSize
  ```
  If the first line isn't the Wi-Fi or Ethernet that connects to the server, make that one win **(admin)**,
  using its name from the list:
  ```powershell
  Set-NetIPInterface -InterfaceAlias "Wi-Fi" -InterfaceMetric 10
  ```
  This also makes Windows prefer that connection for the internet when several are connected. To undo:
  `Set-NetIPInterface -InterfaceAlias "Wi-Fi" -AutomaticMetric Enabled`

### No answer from the other computers, but the firewall is fine
- **Guest Wi-Fi:** guest networks keep devices apart. Use the normal Wi-Fi on all computers.
- **"Client isolation" / "AP isolation"** in the router's Wi-Fi settings does the same: turn it off.
- **VPN:** a VPN on the server or a player's computer sends the traffic elsewhere. Turn it off while playing.
- **Wrong address:** with several addresses, use the one on the same network as the players.

### "The server is already running", but there's no server window
A server is stuck in the background. Use **Stop WoP Server**, or:
```powershell
Stop-Process -Name wopded.x86_64 -Force
```

### Another program uses port 27960
The quick check shows a different program for the port. See which one, then close it, or give the server
another port (27961 to 27963) with `"port"` in `install.json` and **Start WoP Server**:
```powershell
Get-NetUDPEndpoint -LocalPort 27960 | ForEach-Object { Get-Process -Id $_.OwningProcess } | Format-Table Id, Name, Path -AutoSize
```

### The server window shows an error or closes right away
The end of the log says why:
```powershell
Get-Content "$wop\home\wop\qconsole.log" -Tail 40
```

### Players get "wrong version" or can't connect after joining
Everyone needs World of PADMAN **1.7.0** (`Ask-WoP "getinfo"` shows `protocol\72`). Download it from
https://worldofpadman.net/en/download/.

### Forgot the join password, or want to remove it
```powershell
Select-String -Path "$wop\home\wop\server-friends.cfg" -Pattern 'g_password'
```
Set it to `set g_password ""` (no password) with `notepad "$wop\home\wop\server-friends.cfg"`, then restart the
server. Or ask Claude: *"Remove the join password"*.

### Settings messed up: start over with the default settings
Stop the server, then rename the settings files. **Start WoP Server** makes new ones (with a new rcon password,
which Claude picks up by itself):
```powershell
Rename-Item "$wop\home\wop\server-friends.cfg" "server-friends.cfg.old"
Rename-Item "$wop\home\wop\teams.cfg" "teams.cfg.old"
Rename-Item "$wop\home\wop\mode.cfg" "mode.cfg.old"
```

### The game files are damaged
Stop the server and remove the game folder; **Start WoP Server** downloads it again (1.2 GB). Only do this if
`game_dir` in `install.json` is inside the WoP Server folder, not a World of PADMAN you installed yourself:
```powershell
Remove-Item "$wop\game" -Recurse -Force
```

### Claude doesn't know the server / "The server isn't answering"
- Fully quit Claude Desktop (right-click its icon by the clock → Quit) and open it again.
- Claude's settings must list **wop-server**:
  `Select-String -Path "$env:APPDATA\Claude\claude_desktop_config.json" -Pattern 'wop-server'`
- Use **Start WoP Server** once: it sets up the Claude connection again.
- "Isn't answering" means the server is off: ask Claude to start it, or use **Start WoP Server**.

## Mac

> Not tested on a real Mac yet. Paste these in **Terminal**.

```bash
WOP="$HOME/Library/Application Support/WoPServer"
PORT=$(sed -nE 's/.*"port": *([0-9]+).*/\1/p' "$WOP/install.json")
RCON=$(sed -nE 's/^[[:space:]]*seta?[[:space:]]+rconpassword[[:space:]]+"([^"]*)".*/\1/p' "$WOP/home/wop/server-friends.cfg" | tail -1)
ask_wop() { printf '\xff\xff\xff\xff%s' "$1" | nc -u -w 2 "${2:-127.0.0.1}" "$PORT"; echo; }

ps aux | grep -i [w]opded                 # is it running?
lsof -nP -iUDP:"$PORT"                    # which program has the port
ask_wop getinfo                           # name, map, players
ask_wop "rcon $RCON status"               # players with addresses
tail -n 40 "$WOP/home/wop/qconsole.log"   # server log
ipconfig getifaddr en0                    # this Mac's address (Wi-Fi; en1 on some Macs)

FW=/usr/libexec/ApplicationFirewall/socketfilterfw
$FW --getglobalstate                      # firewall on?
$FW --getblockall                         # blocks ALL incoming connections?
$FW --getappblocked "$WOP/game/wopded.x86_64.app/Contents/MacOS/wopded.x86_64"
```

Fixes (asks for your Mac password):
```bash
sudo $FW --add "$WOP/game/wopded.x86_64.app/Contents/MacOS/wopded.x86_64"
sudo $FW --unblockapp "$WOP/game/wopded.x86_64.app/Contents/MacOS/wopded.x86_64"
sudo $FW --setblockall off
pkill -f wopded                           # stop a stuck server
```
