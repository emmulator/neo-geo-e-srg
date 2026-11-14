#!/usr/bin/env bash
# mame.sh — play the cart in MAME (window). Controls: arrows = stick,
# LCtrl/LAlt/Space/LShift = A/B/C/D, 1 = start.
# MAME runs under XWayland by default: on KDE Wayland with an input method
# (plasma-keyboard) the character keys (1 = Start, 5 = coin) go to the input
# method and never reach MAME as key presses. MAME_FLATPAK_ARGS= (empty)
# runs it native Wayland instead.
# MVS=1 runs the arcade board (neogeo, euro BIOS) instead of the AES:
# 5 = coin, 1 = start. CART=path plays another cart zip (default build/rom/esrg.zip).
# It stages a stored copy of MVS_BIOS_ZIP
# (default: neogeo.zip in the BIOS directory), as boot_test.sh does.
# MAME: MAME_CMD, else the MAME flatpak, else `mame` on PATH. BIOS: aes.zip
# (neogeo.zip for MVS) in MAME_BIOS_DIR or ~/ROMs/mame, ~/mame/roms,
# ~/ROMs/neogeo, ~/.mame/roms, /usr/share/mame/roms. Needs bash, python3 and cp (Linux,
# macOS, WSL).
# MAME_RES=WxH sets the window size (default 1280x896, 4x the 320x224 screen).
# Saves: the AES keeps the high-score boards on a memory card and the MVS in
# backup RAM, so the card image (saves/card.neo) and the MVS nvram live in
# SAVE_DIR (default saves/ in the repo, git-ignored, outside build/ so a
# make clean keeps them). MAME creates the card file on the first run.
set -euo pipefail
# Settings: environment variables, or KEY=value lines in
# ${E_SRG_CONFIG:-~/.config/e-srg/config} (sourced first; useful when a
# frontend starts this script and you cannot set the environment).
CONF="${E_SRG_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/e-srg/config}"
# shellcheck disable=SC1090
[[ -f "$CONF" ]] && . "$CONF"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$REPO/build/mame"
# the BIOS: MAME_BIOS_DIR (the directory holding aes.zip), else a usual place
find_bios() {  # find_bios FILE -> prints its path, or fails
    local d
    for d in "${MAME_BIOS_DIR:-}" "$HOME/ROMs/mame" "$HOME/ROMs/neogeo" "$HOME/mame/roms" "$HOME/.mame/roms" /usr/share/mame/roms; do
        [[ -n "$d" && -f "$d/$1" ]] && { printf '%s\n' "$d/$1"; return 0; }
    done
    echo "$1 not found: set MAME_BIOS_DIR to the directory that holds it" >&2
    return 1
}
# the MAME command: MAME_CMD (e.g. "mame", "/opt/mame/mame", or a flatpak
# command line), else the MAME flatpak if installed, else `mame` on PATH
FLATPAK_ARGS="${MAME_FLATPAK_ARGS---nosocket=wayland --socket=x11 --env=SDL_VIDEODRIVER=x11}"
if [[ -n "${MAME_CMD:-}" ]]; then
    read -ra MAME_RUN <<<"$MAME_CMD"
elif command -v flatpak >/dev/null 2>&1 && flatpak info org.mamedev.MAME >/dev/null 2>&1; then
    # shellcheck disable=SC2206  # word-split the flatpak options on purpose
    MAME_RUN=(flatpak run $FLATPAK_ARGS org.mamedev.MAME)
elif command -v mame >/dev/null 2>&1; then
    MAME_RUN=(mame)
else
    echo "no MAME found: install it, or set MAME_CMD to its command" >&2; exit 2
fi
rm -rf "$STAGE"; mkdir -p "$STAGE/roms" "$STAGE/hash"
if [[ "${MVS:-0}" == 1 ]]; then
    MVS_ZIP="${MVS_BIOS_ZIP:-$(find_bios neogeo.zip)}" || exit 2
    python3 -I - "$MVS_ZIP" "$STAGE/roms/neogeo.zip" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z, zipfile.ZipFile(sys.argv[2], "w", zipfile.ZIP_STORED) as o:
    for n in z.namelist():
        o.writestr(n, z.read(n))
PY
    SYSTEM=(neogeo -bios euro -cart1 esrg)
else
    AES_ZIP="$(find_bios aes.zip)" || exit 2
    cp -f "$AES_ZIP" "$STAGE/roms/aes.zip"
    SYSTEM=(aes -cart esrg)
fi
SAVE_DIR="${SAVE_DIR:-$REPO/saves}"
mkdir -p "$SAVE_DIR/nvram"
if [[ "${MVS:-0}" != 1 ]]; then
    SYSTEM+=(-memcard "$SAVE_DIR/card.neo")
fi
CART="${CART:-$REPO/build/rom/esrg.zip}"
cp -f "$CART" "$STAGE/roms/esrg.zip"
python3 "$REPO/scripts/mame_softlist.py" "$CART" "$STAGE/hash" --name esrg --description "E-SRG"
exec "${MAME_RUN[@]}" -rompath "$STAGE/roms" -hashpath "$STAGE/hash" \
    -cfg_directory "$REPO/build/mame-cfg" -nvram_directory "$SAVE_DIR/nvram" -w -resolution "${MAME_RES:-1280x896}" -noautosave -skip_gameinfo "${SYSTEM[@]}" "$@"
