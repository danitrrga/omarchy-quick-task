#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QT_USER_HOME="${QT_USER_HOME:-$HOME}"
QT_BIN_DIR="${QT_BIN_DIR:-$QT_USER_HOME/.local/bin}"
QT_SHARE_DIR="${QT_SHARE_DIR:-$QT_USER_HOME/.local/share/quick-task}"
QT_PLUGIN_DIR="${QT_PLUGIN_DIR:-$QT_USER_HOME/.config/omarchy/plugins/danitrrga.quick-task}"
QT_BINDINGS_FILE="${QT_BINDINGS_FILE:-$QT_USER_HOME/.config/hypr/bindings.lua}"
QT_HYPRLAND_FILE="${QT_HYPRLAND_FILE:-$QT_USER_HOME/.config/hypr/hyprland.lua}"
QT_TOD_CONFIG="${QT_TOD_CONFIG:-$QT_USER_HOME/.config/tod.cfg}"

umask 077

log() { printf '  %s\n' "$*"; }

install_file() {
  local mode="$1" source="$2" target="$3" temporary
  if [[ -f "$target" ]] && cmp -s "$source" "$target"; then
    chmod "$mode" "$target"
    return
  fi
  # Stage outside the watched plugin tree. Creating a temporary beside the
  # destination makes Quickshell reload once for every write before the final
  # rename; this produces one complete-file event instead.
  temporary="$(mktemp "$QT_SHARE_DIR/.install.XXXXXX")"
  install -m"$mode" "$source" "$temporary"
  mv -f "$temporary" "$target"
}

install -d "$QT_BIN_DIR" "$QT_SHARE_DIR/quick_task" "$QT_PLUGIN_DIR"
install_file 755 "$SCRIPT_DIR/bin/quick-task" "$QT_BIN_DIR/quick-task"
for source in "$SCRIPT_DIR"/src/quick_task/*.py; do
  install_file 644 "$source" "$QT_SHARE_DIR/quick_task/$(basename "$source")"
done
install_file 644 \
  "$SCRIPT_DIR/packaging/omarchy/plugins/danitrrga.quick-task/QuickTask.qml" \
  "$QT_PLUGIN_DIR/QuickTask.qml"
install_file 644 \
  "$SCRIPT_DIR/packaging/omarchy/plugins/danitrrga.quick-task/manifest.json" \
  "$QT_PLUGIN_DIR/manifest.json"
log "installed helper and Omarchy plugin"

python3 "$SCRIPT_DIR/scripts/migrate_config.py" \
  --bindings "$QT_BINDINGS_FILE" \
  --hyprland "$QT_HYPRLAND_FILE"

if [[ -f "$QT_TOD_CONFIG" ]]; then
  chmod 600 "$QT_TOD_CONFIG"
  log "secured Todoist configuration"
fi

if [[ -n "${QT_SKIP_RELOAD:-}" ]]; then
  log "reload skipped"
  exit 0
fi

omarchy-shell shell rescanPlugins >/dev/null
omarchy plugin enable danitrrga.quick-task >/dev/null
hyprctl reload >/dev/null
log "enabled plugin and reloaded Hyprland"
