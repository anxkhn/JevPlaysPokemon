#!/bin/zsh
set -eu
ROOT="${0:A:h}"
case "${1:-start}" in
  start)
    if ! /usr/bin/curl --fail --silent http://127.0.0.1:8765/api/status >/dev/null; then
      /usr/bin/osascript -e "tell application \"Terminal\" to do script \"/bin/zsh '$ROOT/emulator.sh' --port 8765\""
    fi
    for attempt in {1..30}; do
      if /usr/bin/curl --fail --silent http://127.0.0.1:8765/api/status >/dev/null; then
        /usr/bin/open "http://127.0.0.1:8765"
        exit 0
      fi
      sleep 1
    done
    print 'Server did not start. Check the new Terminal window.'
    exit 1
    ;;
  status) /usr/bin/curl --fail --silent http://127.0.0.1:8765/api/status ;;
  *) print 'Usage: ./dashboard-service.sh start|status. Stop the server with Control-C in its Terminal window.'; exit 1 ;;
esac
