# Lädt Paper + alle Plugins herunter (Windows).
# Am einfachsten: setup.bat doppelklicken.
#
# Optional:  setup.bat -McVersion 1.21.8   -> feste Minecraft-Version
#            setup.bat -Bedrock           -> Geyser + Floodgate für Handy/Konsole
param(
    [string]$McVersion = "",
    [switch]$Bedrock
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # macht Downloads in PowerShell 5 viel schneller
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Set-Location $PSScriptRoot

$UA = 'stream-smp-setup/1.0 (github.com/davi-dot-collab/-llgemein)'
$Loaders = [uri]::EscapeDataString('["paper","spigot","bukkit"]')

function Get-Json($url) {
    $raw = Invoke-RestMethod -Uri $url -UserAgent $UA
    $list = @()
    foreach ($x in $raw) { $list += $x }   # JSON-Arrays in PowerShell 5 sauber entpacken
    return ,$list
}

function Save-File($url, $target) {
    if (Test-Path $target) { Write-Host "  = schon da: $target"; return }
    Invoke-WebRequest -Uri $url -UserAgent $UA -OutFile $target -UseBasicParsing
    Write-Host "  + $target"
}

# ---------- Paper ----------
Write-Host "==> Suche Paper-Version ..."
if (-not $McVersion) {
    $project = Invoke-RestMethod -Uri 'https://fill.papermc.io/v3/projects/paper' -UserAgent $UA
    $versions = $project.versions.PSObject.Properties | ForEach-Object { $_.Value } |
        Where-Object { $_ -match '^\d+(\.\d+)+$' } |
        Sort-Object { [version]($(if ($_ -match '\.') { $_ } else { "$_.0" })) } -Descending |
        Select-Object -First 10
    foreach ($v in $versions) {
        try {
            $b = Invoke-RestMethod -Uri "https://fill.papermc.io/v3/projects/paper/versions/$v/builds/latest" -UserAgent $UA
            if ($b.channel -eq 'STABLE') { $McVersion = $v; break }
        } catch { }
    }
}
if (-not $McVersion) { throw 'Keine stabile Paper-Version gefunden.' }
Write-Host "    Minecraft-Version: $McVersion"

$build = Invoke-RestMethod -Uri "https://fill.papermc.io/v3/projects/paper/versions/$McVersion/builds/latest" -UserAgent $UA
Remove-Item server.jar -ErrorAction SilentlyContinue
Save-File $build.downloads.'server:default'.url 'server.jar'

New-Item -ItemType Directory -Force plugins | Out-Null

# ---------- Plugins von Modrinth ----------
function Get-ModrinthPlugin($slug) {
    $gv = [uri]::EscapeDataString("[`"$McVersion`"]")
    $list = Get-Json "https://api.modrinth.com/v2/project/$slug/version?loaders=$Loaders&game_versions=$gv"
    if ($list.Count -eq 0) {
        Write-Host "  ! ${slug}: keine Version speziell für $McVersion - nehme die neueste (bitte testen)"
        $list = Get-Json "https://api.modrinth.com/v2/project/$slug/version?loaders=$Loaders"
    }
    if ($list.Count -eq 0) {
        Write-Host "  ! ${slug}: nicht gefunden - manuell laden: https://modrinth.com/plugin/$slug"; return
    }
    $v = $list | Where-Object { $_.version_type -eq 'release' } | Select-Object -First 1
    if (-not $v) { $v = $list[0] }
    $file = $v.files | Where-Object { $_.primary } | Select-Object -First 1
    if (-not $file) { $file = $v.files[0] }
    Save-File $file.url (Join-Path plugins $file.filename)
}

# ---------- Plugins von GitHub ----------
function Get-GitHubPlugin($repo, $pattern) {
    try {
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" -UserAgent $UA
        $asset = $rel.assets | Where-Object { $_.name -match $pattern -and $_.name -notmatch 'sources|javadoc' } | Select-Object -First 1
    } catch { $asset = $null }
    if (-not $asset) { Write-Host "  ! ${repo}: nicht gefunden - manuell laden: https://github.com/$repo/releases"; return }
    Save-File $asset.browser_download_url (Join-Path plugins $asset.name)
}

Write-Host "==> Lade Plugins ..."
foreach ($slug in 'luckperms','essentialsx','coreprotect','bluemap','discordsrv','tab-was-taken','simple-voice-chat','chunky') {
    try { Get-ModrinthPlugin $slug } catch { Write-Host "  ! ${slug}: Fehler beim Download ($_)" }
}
Get-GitHubPlugin 'GriefPrevention/GriefPrevention' '^GriefPrevention.*\.jar$'
Get-GitHubPlugin 'LunarClient/Apollo' '^apollo-bukkit.*\.jar$'

if ($Bedrock) {
    Write-Host "==> Lade Geyser + Floodgate (Bedrock) ..."
    Save-File 'https://download.geysermc.org/v2/projects/geyser/versions/latest/builds/latest/downloads/spigot' 'plugins\Geyser-Spigot.jar'
    Save-File 'https://download.geysermc.org/v2/projects/floodgate/versions/latest/builds/latest/downloads/spigot' 'plugins\floodgate-spigot.jar'
}

# ---------- EULA ----------
if (-not ((Test-Path eula.txt) -and (Select-String -Path eula.txt -Pattern 'eula=true' -Quiet))) {
    Write-Host ""
    Write-Host "Minecraft-EULA: https://aka.ms/MinecraftEULA"
    $answer = Read-Host "Hast du die EULA gelesen und akzeptierst sie? (ja/nein)"
    if ($answer -eq 'ja') { Set-Content eula.txt 'eula=true' -Encoding ASCII }
    else { Write-Host "Ohne EULA startet der Server nicht. Du kannst setup.bat spaeter nochmal starten." }
}

Write-Host ""
Write-Host "Fertig! Server starten mit: start.bat"
