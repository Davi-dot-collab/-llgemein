#!/usr/bin/env bash
# Lädt Paper + alle Plugins herunter (Linux / Mac / VPS).
# Benötigt: curl, jq  (Ubuntu/Debian: sudo apt install curl jq)
#
# Optional:  MC_VERSION=1.21.8 ./setup.sh   -> feste Minecraft-Version
#            BEDROCK=ja ./setup.sh           -> Geyser + Floodgate für Handy/Konsole
set -euo pipefail

cd "$(dirname "$0")"
UA="stream-smp-setup/1.0 (github.com/davi-dot-collab/-llgemein)"
LOADERS='%5B%22paper%22%2C%22spigot%22%2C%22bukkit%22%5D'
MC_VERSION="${MC_VERSION:-}"
BEDROCK="${BEDROCK:-nein}"

for cmd in curl jq; do
  command -v "$cmd" >/dev/null || { echo "Fehlt: $cmd  ->  sudo apt install $cmd"; exit 1; }
done

get() { curl -fsSL -A "$UA" "$@"; }

download() { # url ziel
  if [[ -f "$2" ]]; then echo "  = schon da: $2"; return; fi
  get -o "$2" "$1" && echo "  + $2"
}

# ---------- Paper ----------
echo "==> Suche Paper-Version ..."
if [[ -z "$MC_VERSION" ]]; then
  for v in $(get https://fill.papermc.io/v3/projects/paper | jq -r '.versions[][]' \
             | grep -E '^[0-9]+(\.[0-9]+)+$' | sort -rV | head -n 10); do
    channel=$(get "https://fill.papermc.io/v3/projects/paper/versions/$v/builds/latest" | jq -r '.channel' || true)
    if [[ "$channel" == "STABLE" ]]; then MC_VERSION="$v"; break; fi
  done
fi
[[ -n "$MC_VERSION" ]] || { echo "Keine stabile Paper-Version gefunden."; exit 1; }
echo "    Minecraft-Version: $MC_VERSION"

paper_url=$(get "https://fill.papermc.io/v3/projects/paper/versions/$MC_VERSION/builds/latest" \
            | jq -r '.downloads["server:default"].url')
rm -f server.jar
download "$paper_url" server.jar

mkdir -p plugins

# ---------- Plugins von Modrinth ----------
modrinth() { # slug
  local slug="$1" json pick
  json=$(get "https://api.modrinth.com/v2/project/$slug/version?loaders=$LOADERS&game_versions=%5B%22$MC_VERSION%22%5D" || echo '[]')
  if [[ $(jq 'length' <<<"$json") -eq 0 ]]; then
    echo "  ! $slug: keine Version speziell für $MC_VERSION – nehme die neueste (bitte testen)"
    json=$(get "https://api.modrinth.com/v2/project/$slug/version?loaders=$LOADERS" || echo '[]')
  fi
  if [[ $(jq 'length' <<<"$json") -eq 0 ]]; then
    echo "  ! $slug: nicht gefunden – manuell laden: https://modrinth.com/plugin/$slug"; return
  fi
  pick=$(jq -r '(([.[] | select(.version_type == "release")] | .[0]) // .[0])
                | ((.files | map(select(.primary)) | .[0]) // .files[0])
                | "\(.filename)\t\(.url)"' <<<"$json")
  download "${pick#*$'\t'}" "plugins/${pick%%$'\t'*}"
}

# ---------- Plugins von GitHub ----------
github() { # repo regex
  local url name
  url=$(get "https://api.github.com/repos/$1/releases/latest" \
        | jq -r --arg re "$2" '[.assets[] | select(.name | test($re)) | select(.name | test("sources|javadoc") | not)][0].browser_download_url // empty' || true)
  if [[ -z "$url" ]]; then echo "  ! $1: nicht gefunden – manuell laden: https://github.com/$1/releases"; return; fi
  name="${url##*/}"
  download "$url" "plugins/$name"
}

echo "==> Lade Plugins ..."
for slug in luckperms essentialsx coreprotect bluemap discordsrv tab-was-taken simple-voice-chat chunky; do
  modrinth "$slug" || echo "  ! $slug: Fehler beim Download"
done
github GriefPrevention/GriefPrevention '^GriefPrevention.*\.jar$'
github LunarClient/Apollo '^apollo-bukkit.*\.jar$'

if [[ "$BEDROCK" == "ja" ]]; then
  echo "==> Lade Geyser + Floodgate (Bedrock) ..."
  download https://download.geysermc.org/v2/projects/geyser/versions/latest/builds/latest/downloads/spigot plugins/Geyser-Spigot.jar
  download https://download.geysermc.org/v2/projects/floodgate/versions/latest/builds/latest/downloads/spigot plugins/floodgate-spigot.jar
fi

# ---------- EULA ----------
if ! grep -qs 'eula=true' eula.txt; then
  echo
  echo "Minecraft-EULA: https://aka.ms/MinecraftEULA"
  read -r -p "Hast du die EULA gelesen und akzeptierst sie? (ja/nein) " answer
  if [[ "$answer" == "ja" ]]; then echo "eula=true" > eula.txt
  else echo "Ohne EULA startet der Server nicht. Du kannst setup.sh später nochmal starten."; fi
fi

chmod +x start.sh
echo
echo "Fertig! Server starten mit:  ./start.sh"
