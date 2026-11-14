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
# (default ~/ROMs/neogeo/neogeo.zip), as boot_test.sh does.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$REPO/build/mame"
BIOS_DIR="${MAME_BIOS_DIR:-$HOME/Development/emulators/roms/mame-neogeo}"
rm -rf "$STAGE"; mkdir -p "$STAGE/roms" "$STAGE/hash"
if [[ "${MVS:-0}" == 1 ]]; then
    python3 -I - "${MVS_BIOS_ZIP:-$HOME/ROMs/neogeo/neogeo.zip}" "$STAGE/roms/neogeo.zip" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z, zipfile.ZipFile(sys.argv[2], "w", zipfile.ZIP_STORED) as o:
    for n in z.namelist():
        o.writestr(n, z.read(n))
PY
    SYSTEM=(neogeo -bios euro -cart1 esrg)
else
    cp -f "$BIOS_DIR/aes.zip" "$STAGE/roms/aes.zip"
    SYSTEM=(aes -cart esrg)
fi
CART="${CART:-$REPO/build/rom/esrg.zip}"
cp -f "$CART" "$STAGE/roms/esrg.zip"
python3 "$REPO/scripts/mame_softlist.py" "$CART" "$STAGE/hash" --name esrg --description "E-SRG"
FLATPAK_ARGS="${MAME_FLATPAK_ARGS---nosocket=wayland --socket=x11 --env=SDL_VIDEODRIVER=x11}"
# shellcheck disable=SC2086  # word-split the flatpak options on purpose
exec flatpak run $FLATPAK_ARGS org.mamedev.MAME -rompath "$STAGE/roms" -hashpath "$STAGE/hash" \
    -cfg_directory "$REPO/build/mame-cfg" -nvram_directory "$REPO/build/mame-nvram" -w -resolution 960x672 -noautosave -skip_gameinfo "${SYSTEM[@]}" "$@"
