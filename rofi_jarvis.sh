#!/usr/bin/env bash
# Toggle behavior: if rofi is already open, close it
if pgrep -x rofi >/dev/null; then
    pkill -x rofi
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

QUERY=$(rofi -dmenu \
    -p "⚡ Jarvis" \
    -theme-str 'window {width: 540px; height: 68px;} listview {enabled: false;} entry {placeholder: "Ask Jarvis anything..."; horizontal-align: 0.0;}' \
    < /dev/null)

if [ -n "$QUERY" ]; then
    "$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/jarvis.py" "$QUERY"
fi
