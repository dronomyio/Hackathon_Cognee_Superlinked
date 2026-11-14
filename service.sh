#!/bin/zsh
# Manage the worker in the current macOS login session; no API keys in launchd.
set -eu
cd "${0:A:h}"
root="$PWD"
label="com.suvasis.superlinked-bot"
domain="gui/$(id -u)"
state="$root/data/service"
plist="$state/$label.plist"
mkdir -p "$state"
chmod 700 "$state"

case "${1:-status}" in
  start)
    if launchctl print "$domain/$label" >/dev/null 2>&1; then
      print 'Service is already loaded. Use service.sh status or restart.'
      exit 0
    fi
    .venv/bin/python - "$root" "$plist" <<'PY'
import os, plistlib, sys
from pathlib import Path
root, target = map(Path, sys.argv[1:])
config = {
    "Label": "com.suvasis.superlinked-bot",
    "ProgramArguments": [str(root / ".venv/bin/python"), "-u", str(root / "app.py"), "band"],
    "WorkingDirectory": str(root),
    "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    "RunAtLoad": True,
    "KeepAlive": {"SuccessfulExit": False},
    "ThrottleInterval": 60,
    "ProcessType": "Background",
    "StandardOutPath": str(root / "data/service/stdout.log"),
    "StandardErrorPath": str(root / "data/service/stderr.log"),
}
with target.open("wb") as stream:
    plistlib.dump(config, stream)
target.chmod(0o600)
PY
    launchctl bootstrap "$domain" "$plist"
    print 'Local worker loaded. Check service.sh status and logs for connectivity.'
    ;;
  stop)
    launchctl bootout "$domain/$label"
    print 'Local worker stopped.'
    ;;
  restart)
    launchctl kickstart -k "$domain/$label"
    ;;
  status)
    launchctl print "$domain/$label"
    ;;
  logs)
    tail -n 60 "$state/stdout.log" "$state/stderr.log"
    ;;
  *)
    print -u2 'Usage: ./service.sh start|stop|restart|status|logs'
    exit 2
    ;;
esac
