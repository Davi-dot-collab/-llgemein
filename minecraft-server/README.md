# Stream-SMP – euer Community-Minecraft-Server

Fertiges Server-Paket für **Minecraft Java** (Paper) mit Minimap, Waypoints, Web-Karte, Rängen, Grundstücksschutz, Discord-Anbindung und Voice-Chat.

## Was ist drin?

| Plugin | Wofür |
|---|---|
| **LuckPerms** | Ränge: Spieler, Sub, Mod, Admin |
| **EssentialsX** | `/warp`, `/home`, `/tpa`, `/msg` … |
| **GriefPrevention** | Grundstücke schützen (mit Goldschaufel abstecken) |
| **CoreProtect** | Griefing rückgängig machen (`/co inspect`, `/co rollback`) |
| **BlueMap** | Live-3D-Karte im Browser (ideal für den Stream) |
| **Apollo** | Lunar-Client-Integration (Minimap, Waypoints vom Server) |
| **DiscordSRV** | Minecraft-Chat ↔ Discord-Kanal |
| **TAB** | Schöne Tablist mit Rängen |
| **Simple Voice Chat** | Proximity Voice Chat |
| **Chunky** | Welt vorgenerieren gegen Lags |
| *Geyser + Floodgate* | *optional:* Bedrock-Spieler (Handy, Konsole) |

---

## Weg 1: Gemieteter Server (empfohlen fürs Streamen)

So laggt euer Stream-PC nicht, und der Server läuft auch, wenn ihr offline seid.

1. Server mieten, z. B. bei Nitrado, Apex Hosting, Sparked Host oder BisectHosting. **6–8 GB RAM** reichen für den Start.
2. Im Hoster-Panel als Server-Typ **„Paper“** wählen, mit der **neuesten Version**.
3. Server einmal starten und wieder stoppen.
4. Die Plugins herunterladen. Die Links stehen unten unter [Plugin-Links](#plugin-links). Achtet darauf, dass jedes Plugin zu eurer Minecraft-Version passt. Ladet die `.jar`-Dateien im Panel (Dateimanager oder FTP) in den Ordner **`plugins`** hoch.
5. Die Werte aus [`server.properties`](server.properties) im Panel übernehmen (MOTD, Whitelist …).
6. Server starten und weiter mit [Nach dem ersten Start](#nach-dem-ersten-start).

> Manche Hoster haben auch einen „Plugin-Installer“ im Panel. Dann sucht ihr die Plugins einfach dort.

## Weg 2: Eigener PC oder Linux-VPS (alles automatisch)

**Voraussetzung:** **Java 21** oder neuer, z. B. von [adoptium.net](https://adoptium.net). Für ganz neue Minecraft-Versionen braucht ihr eventuell Java 25. Wenn der Server meckert, steht in der Fehlermeldung, welche Version er will.

**Windows:**
1. Diesen Ordner `minecraft-server` irgendwohin kopieren.
2. **`setup.bat`** doppelklicken. Das Skript lädt Paper und alle Plugins herunter und fragt nach der EULA.
   - Mit Bedrock-Spielern: In der Eingabeaufforderung `setup.bat -Bedrock` ausführen.
   - Bestimmte Version: `setup.bat -McVersion 1.21.8`
3. **`start.bat`** doppelklicken. Fertig!

**Linux / Mac / VPS:**
```bash
sudo apt install curl jq openjdk-21-jre-headless   # Ubuntu/Debian
./setup.sh                 # oder: BEDROCK=ja ./setup.sh
./start.sh                 # mehr RAM: RAM=8G ./start.sh
```

**Damit Freunde joinen können:** Im Router den Port **25565 (TCP)** an euren PC weiterleiten („Portfreigabe“). Für Voice-Chat zusätzlich **24454 (UDP)**, für BlueMap **8100 (TCP)**, für Bedrock **19132 (UDP)**. Einfacher ohne Router-Einstellungen geht es mit [playit.gg](https://playit.gg).

**Updaten:** Alte `.jar`-Dateien im `plugins`-Ordner löschen und das Setup nochmal starten. Eure Welt bleibt erhalten.

---

## Nach dem ersten Start

### 1. Euch selbst whitelisten und zu Admins machen
In der Server-Konsole eingeben:
```
whitelist add DEIN_NAME
whitelist add NAME_VOM_KUMPEL
op DEIN_NAME
```

### 2. Ränge einrichten
Alle Befehle aus [`befehle/luckperms-raenge.txt`](befehle/luckperms-raenge.txt) nacheinander in die Konsole kopieren und vorher eure Namen eintragen.
Neue Spieler freischalten: `whitelist add NAME`. Einen Sub ernennen: `lp user NAME parent add sub`.

### 3. Warps und Waypoints setzen
Alle Befehle stehen in [`befehle/waypoints.txt`](befehle/waypoints.txt):
- **Warps** (`/setwarp shop` usw.) gehen für alle Spieler. Mit `/warp` sieht man die Liste.
- **Locator-Bar-Waypoints** (ab Minecraft 1.21.6) sieht jeder Spieler **ohne Mods** über der Hotbar.
- **Minimap:** Spieler mit dem **Lunar Client** haben eine eingebaute Minimap. Über Apollo kann der Server ihnen Waypoints schicken. Die Einrichtung steht unter [lunarclient.dev](https://lunarclient.dev).

### 4. BlueMap (Web-Karte)
1. In `plugins/BlueMap/core.conf` die Zeile `accept-download: false` auf **`true`** ändern. Damit erlaubt ihr BlueMap, die Minecraft-Texturen zu laden.
2. In der Konsole `bluemap reload` eingeben.
3. Die Karte unter **`http://SERVER-IP:8100`** öffnen. Beim Hoster müsst ihr eventuell einen zusätzlichen Port freischalten, fragt dafür den Support.

**BlueMap-Marker** (z. B. Spawn, Shop) tragt ihr in `plugins/BlueMap/maps/world.conf` unter `marker-sets` ein, Beispiel:
```hocon
marker-sets: {
  orte: {
    label: "Wichtige Orte"
    markers: {
      spawn: { type: "poi", position: { x: 0, y: 70, z: 0 }, label: "Spawn" }
      shop:  { type: "poi", position: { x: 120, y: 64, z: -40 }, label: "Shop" }
    }
  }
}
```
Danach `bluemap reload` eingeben. Mehr dazu steht unter [bluemap.bluecolored.de/wiki](https://bluemap.bluecolored.de/wiki/).

> **Stream-Tipp:** Die BlueMap-Seite in OBS als **Browserquelle** einbinden. Dann sehen die Zuschauer live, wo alle sind.

### 5. Welt vorgenerieren (gegen Lags)
In der Konsole eingeben:
```
chunky radius 3000
chunky start
```
Das läuft am besten, wenn niemand online ist, und kann eine Weile dauern.

### 6. Discord verbinden (DiscordSRV)
1. Auf [discord.com/developers](https://discord.com/developers/applications) einen Bot erstellen und den **Token** kopieren. Bei „Privileged Gateway Intents“ **Server Members** und **Message Content** einschalten.
2. Den Bot auf euren Discord einladen.
3. In `plugins/DiscordSRV/config.yml` den `BotToken` eintragen und bei `Channels` die ID eures Minecraft-Chat-Kanals eintragen (Rechtsklick auf den Kanal → „ID kopieren“, dafür muss der Entwicklermodus an sein).
4. Server neu starten.

> ⚠️ Den Bot-Token **nie** im Stream zeigen und nicht auf GitHub hochladen!

### 7. Grundstücke (GriefPrevention)
Wenn Spieler ihre erste Kiste platzieren, wird automatisch ein kleines Grundstück darum geschützt. Mit einer **Goldschaufel** stecken sie größere Gebiete ab. `/trust NAME` lässt Freunde mitbauen.

---

## Plugin-Links

- Paper: https://papermc.io/downloads/paper
- LuckPerms: https://modrinth.com/plugin/luckperms
- EssentialsX: https://modrinth.com/plugin/essentialsx
- GriefPrevention: https://github.com/GriefPrevention/GriefPrevention/releases
- CoreProtect: https://modrinth.com/plugin/coreprotect
- BlueMap: https://modrinth.com/plugin/bluemap
- Apollo (Lunar): https://github.com/LunarClient/Apollo/releases (die Datei `apollo-bukkit-….jar`)
- DiscordSRV: https://modrinth.com/plugin/discordsrv
- TAB: https://modrinth.com/plugin/tab-was-taken
- Simple Voice Chat: https://modrinth.com/plugin/simple-voice-chat (Spieler brauchen die Mod auch im Client)
- Chunky: https://modrinth.com/plugin/chunky
- Geyser + Floodgate: https://geysermc.org/download

## Regeln
Eine Vorlage für Server- und Discord-Regeln findet ihr in [`regeln.md`](regeln.md).
