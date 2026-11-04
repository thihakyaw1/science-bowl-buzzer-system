#!/bin/sh
set -eu
dest="$HOME/Library/Application Support/ScienceBowl"
mkdir -p "$dest" "$HOME/Library/LaunchAgents"
cat > "$dest/watch.sh" <<'WATCH'
#!/bin/sh
opened=0
failures=0
while :; do
  if /usr/bin/curl --noproxy '*' --fail --silent --max-time 2 http://192.168.77.2:8080/api/state | /usr/bin/grep -q '"hardware"'; then
    failures=0
    if [ "$opened" = 0 ]; then /usr/bin/open http://192.168.77.2:8080/; opened=1; fi
  else
    failures=$((failures + 1))
    if [ "$failures" -ge 3 ]; then opened=0; fi
  fi
  sleep 5
done
WATCH
# plutil constructs the property list without interpolating paths into XML.
plist="$HOME/Library/LaunchAgents/org.sciencebowl.dashboard.plist"
/usr/bin/plutil -create xml1 "$plist"
/usr/bin/plutil -insert Label -string org.sciencebowl.dashboard "$plist"
/usr/bin/plutil -insert ProgramArguments -json '[]' "$plist"
/usr/bin/plutil -insert ProgramArguments.0 -string /bin/sh "$plist"
/usr/bin/plutil -insert ProgramArguments.1 -string "$dest/watch.sh" "$plist"
/usr/bin/plutil -insert RunAtLoad -bool YES "$plist"
/usr/bin/plutil -insert KeepAlive -bool YES "$plist"
/bin/launchctl bootout "gui/$(id -u)/org.sciencebowl.dashboard" 2>/dev/null || true
/bin/launchctl bootstrap "gui/$(id -u)" "$plist"
echo 'Installed. The dashboard opens when the Pi responds. Stay signed in.'
