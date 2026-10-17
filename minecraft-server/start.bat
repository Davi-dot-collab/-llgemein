@echo off
cd /d "%~dp0"
rem RAM anpassen: 6G = 6 GB. Nicht mehr als ca. 70 % vom PC-RAM nehmen.
set RAM=6G
:loop
java -Xms%RAM% -Xmx%RAM% -XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:+AlwaysPreTouch -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseIntervalMillis=0 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1 -Dusing.aikars.flags=https://mcflags.emc.gs -Daikars.new.flags=true -jar server.jar --nogui
echo.
echo Server gestoppt. Neustart in 10 Sekunden - zum Beenden dieses Fenster schliessen.
timeout /t 10
goto loop
