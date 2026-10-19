# Installiert Fabric + Sodium + Iris + Complementary Shader + Xaero's Minimap
# für den normalen Minecraft Launcher. Am einfachsten: installieren.bat doppelklicken.
param(
    [string]$McVersion = "26.3",
    [string]$RamGB = "4"
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$UA = 'stream-smp-client-setup/1.0 (github.com/davi-dot-collab/-llgemein)'
$Here = $PSScriptRoot
$Mc = Join-Path $env:APPDATA '.minecraft'
$Mods = Join-Path $Mc 'mods'
$Shaders = Join-Path $Mc 'shaderpacks'
$Config = Join-Path $Mc 'config'
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Info($t) { Write-Host $t -ForegroundColor Cyan }
function Ok($t)   { Write-Host "  + $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  ! $t" -ForegroundColor Yellow }

function Get-List($url) {
    $raw = Invoke-RestMethod -Uri $url -UserAgent $UA
    $list = @()
    foreach ($x in $raw) { $list += $x }
    return ,$list
}

# ---------- Vorbereitung ----------
Info "==> Minecraft-Ordner: $Mc"
if (-not (Test-Path $Mc)) {
    Write-Host "Minecraft-Ordner nicht gefunden. Starte den Minecraft Launcher einmal und spiele kurz, dann nochmal." -ForegroundColor Red
    return
}
if (Get-Process -Name 'MinecraftLauncher','Minecraft' -ErrorAction SilentlyContinue) {
    Write-Host "Bitte schliesse zuerst den Minecraft Launcher und Minecraft komplett!" -ForegroundColor Red
    return
}
New-Item -ItemType Directory -Force $Mods, $Shaders, $Config | Out-Null

# Alte Versionen derselben Mods wegräumen (sonst stürzt das Spiel ab)
$old = Get-ChildItem $Mods -Filter *.jar | Where-Object { $_.Name -match '^(fabric-api|sodium|iris|xaeros?)' }
if ($old) {
    $bak = Join-Path $Mods '_alte_mods'
    New-Item -ItemType Directory -Force $bak | Out-Null
    $old | Move-Item -Destination $bak -Force
    Warn "Alte Versionen nach mods\_alte_mods verschoben: $($old.Name -join ', ')"
}

# ---------- 1) Fabric Loader ----------
Info "==> Installiere Fabric fuer Minecraft $McVersion ..."
$loaders = Get-List "https://meta.fabricmc.net/v2/versions/loader/$McVersion"
if ($loaders.Count -eq 0) { throw "Fabric gibt es (noch) nicht fuer Minecraft $McVersion." }
$pick = $loaders | Where-Object { $_.loader.stable } | Select-Object -First 1
if (-not $pick) { $pick = $loaders[0] }
$loaderVersion = $pick.loader.version

$profileJson = Invoke-WebRequest -Uri "https://meta.fabricmc.net/v2/versions/loader/$McVersion/$loaderVersion/profile/json" -UserAgent $UA -UseBasicParsing
$versionId = ($profileJson.Content | ConvertFrom-Json).id
$versionDir = Join-Path $Mc "versions\$versionId"
New-Item -ItemType Directory -Force $versionDir | Out-Null
[IO.File]::WriteAllText((Join-Path $versionDir "$versionId.json"), $profileJson.Content, $Utf8NoBom)
$dummyJar = Join-Path $versionDir "$versionId.jar"
if (-not (Test-Path $dummyJar)) { New-Item -ItemType File $dummyJar | Out-Null }
Ok "Fabric Loader $loaderVersion ($versionId)"

# Launcher-Profil "Stream-SMP (Fabric)" anlegen
$javaArgs = "-Xmx${RamGB}G -XX:+UnlockExperimentalVMOptions -XX:+UseG1GC -XX:G1NewSizePercent=20 -XX:G1ReservePercent=20 -XX:MaxGCPauseMillis=50 -XX:G1HeapRegionSize=32M"
$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
$profileFiles = @('launcher_profiles.json', 'launcher_profiles_microsoft_store.json') |
    ForEach-Object { Join-Path $Mc $_ } | Where-Object { Test-Path $_ }
if (-not $profileFiles) {
    Warn "Keine Launcher-Profile gefunden. Starte den Launcher einmal, schliesse ihn und fuehre den Installer nochmal aus."
}
foreach ($pf in $profileFiles) {
    Copy-Item $pf "$pf.backup" -Force
    $data = Get-Content $pf -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $data.profiles) { $data | Add-Member -NotePropertyName profiles -NotePropertyValue ([pscustomobject]@{}) -Force }
    $entry = [pscustomobject]@{
        name          = "Stream-SMP (Fabric $McVersion)"
        type          = 'custom'
        created       = $now
        lastUsed      = $now
        icon          = 'Furnace'
        lastVersionId = $versionId
        javaArgs      = $javaArgs
    }
    $data.profiles | Add-Member -NotePropertyName 'stream-smp-fabric' -NotePropertyValue $entry -Force
    [IO.File]::WriteAllText($pf, ($data | ConvertTo-Json -Depth 32), $Utf8NoBom)
    Ok "Launcher-Profil 'Stream-SMP (Fabric $McVersion)' mit $RamGB GB RAM (Backup: $(Split-Path $pf -Leaf).backup)"
}

# ---------- 2) Mods + Shader ----------
function Install-FromModrinth($slug, $loader, $target, $localPattern, $useGameVersion = $true) {
    # 1. Datei liegt schon neben dem Installer -> die nehmen (passt garantiert zusammen)
    $local = Get-ChildItem $Here -Filter $localPattern -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($local) {
        Copy-Item $local.FullName (Join-Path $target $local.Name) -Force
        Ok "$($local.Name)"
        return $local.Name
    }
    # 2. Sonst die neueste passende Version von Modrinth laden
    $loaders = [uri]::EscapeDataString("[`"$loader`"]")
    $url = "https://api.modrinth.com/v2/project/$slug/version?loaders=$loaders"
    if ($useGameVersion) { $url += "&game_versions=" + [uri]::EscapeDataString("[`"$McVersion`"]") }
    try {
        $list = Get-List $url
        if ($list.Count -gt 0) {
            $v = $list | Where-Object { $_.version_type -eq 'release' } | Select-Object -First 1
            if (-not $v) { $v = $list[0] }
            $file = $v.files | Where-Object { $_.primary } | Select-Object -First 1
            if (-not $file) { $file = $v.files[0] }
            $dest = Join-Path $target $file.filename
            if (-not (Test-Path $dest)) {
                Invoke-WebRequest -Uri $file.url -UserAgent $UA -OutFile $dest -UseBasicParsing
            }
            Ok "$($file.filename) (heruntergeladen)"
            return $file.filename
        }
    } catch { }
    Warn "$slug nicht gefunden - bitte manuell von https://modrinth.com/project/$slug laden"
    return $null
}

Info "==> Lade Mods ..."
Install-FromModrinth 'fabric-api'      'fabric' $Mods 'fabric-api*.jar' | Out-Null
Install-FromModrinth 'sodium'          'fabric' $Mods 'sodium*.jar'     | Out-Null
Install-FromModrinth 'iris'            'fabric' $Mods 'iris*.jar'       | Out-Null
Install-FromModrinth 'xaeros-minimap'  'fabric' $Mods 'Xaeros_Minimap*.jar' | Out-Null

Info "==> Lade Shader ..."
$shaderFile = Install-FromModrinth 'complementary-reimagined' 'iris' $Shaders 'ComplementaryReimagined*.zip' $false

# ---------- 3) Einstellungen ----------
Info "==> FPS-Einstellungen ..."
if ($shaderFile) {
    $irisProps = Join-Path $Config 'iris.properties'
    $lines = @()
    if (Test-Path $irisProps) { $lines = Get-Content $irisProps | Where-Object { $_ -notmatch '^(shaderPack|enableShaders)=' } }
    $lines += "shaderPack=$shaderFile"
    $lines += "enableShaders=true"
    [IO.File]::WriteAllLines($irisProps, [string[]]$lines, $Utf8NoBom)
    Ok "Shader '$shaderFile' ist eingeschaltet"
}

$optionsFile = Join-Path $Mc 'options.txt'
if (Test-Path $optionsFile) {
    Copy-Item $optionsFile "$optionsFile.backup" -Force
    $set = @{ 'renderDistance' = '10'; 'simulationDistance' = '8'; 'enableVsync' = 'false' }
    $out = Get-Content $optionsFile | ForEach-Object {
        $k = ($_ -split ':', 2)[0]
        if ($set.ContainsKey($k)) { "${k}:$($set[$k])" } else { $_ }
    }
    [IO.File]::WriteAllLines($optionsFile, [string[]]$out, $Utf8NoBom)
    Ok "Sichtweite 10, Simulation 8, V-Sync aus (Backup: options.txt.backup)"
}

Write-Host ""
Write-Host "FERTIG!" -ForegroundColor Green
Write-Host "1. Minecraft Launcher oeffnen"
Write-Host "2. Unten links das Profil 'Stream-SMP (Fabric $McVersion)' waehlen und SPIELEN"
Write-Host "3. Wenn es ruckelt: Optionen > Grafik > Shader Packs > Shader-Einstellungen > Profil 'Low'"
