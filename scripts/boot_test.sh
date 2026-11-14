#!/usr/bin/env bash
# boot_test.sh MODE — headless MAME: the cart must boot into cart code and the
# snapshot must pass tests/check_snapshot.py MODE (text, dome, dome-lift,
# ship, ship-top, missile) or tests/check_leftovers.py (leftovers) or tests/check_broken.py
# (cracks: run with CRACK_CART pointing at the -DCRACK_TEST cart) or
# tests/check_hud.py (hud: the probe scripts a deterministic game) or
# tests/check_collapse.py (collapse: the probe scripts a full game to GAME
# OVER and reads the dome's VRAM back) or tests/check_frame_mark.py
# (framemark: a -DFRAME_MARK cart reports the worst end-of-work raster
# line) or tests/check_flow.py (flow / flow-restart: the AES title-and-return
# flow; flow-mvs / flow-mvs-start: the MVS boot harness — a coin, the BIOS
# compulsion timer, and the game starting when it runs out or on a real Start
# press; flow-mvs-norestart: on MVS, A at GAME OVER does nothing and the
# 295-frame return to the title still happens; flow-pages: the title's nine
# pages turn every 295 frames with no Start, the dome on page 0 only, and
# every sampled frame's rows equal the title model; flow-pages-c: a C press
# turns the page (M6 Tasks 1, 2, 4, 6); flow-level: B taps cycle the level
# NORMAL->HARD->EASY->NORMAL->HARD on page 0 with title_t 0 and the game
# begins at the chosen level; flow-return: the GAME OVER return opens the
# HIGH SCORES page (1) with the level kept, and a fresh boot shows page 0
# and NORMAL (M6 Task 7); best-mvs: the MVS backup-RAM high scores (M6
# Task 9); best-aes: the AES memory-card high scores (M6 Task 10) — three
# runs of `aes -cart esrg`, runs 1 and 2 sharing one -memcard file (run
# 2's fresh nvram proves the card, not the per-boot backup RAM, kept the
# score), run 3 with no card at all.
# sound / sound-mvs: the M7 Task 1 sound pipeline — the -DSOUND_TEST cart
# sends the five effects at recorded title frames (plus the frame-400
# two-in-one send) and the checker proves from the -wavwrite recording
# that every send was acknowledged, each is silent before / loud after /
# right length, and the frame-400 pair plays the hit's 0.64 s with the pip
# over it (sound-mvs runs the same cart under `neogeo -bios euro`).
# sound-game / sound-radar: the M7 Task 2 tests — the same cart now plays
# the deterministic "sound game" (sound_game_probe.lua drives it) and
# records every game sound send in the game log; the checker replays the
# model from the recorded inputs and proves the log equals its predicted
# commands frame for frame, the sampled sends are loud in the WAV, the
# dome deaths' 5 rumbles come 9 frames apart, and (sound-radar, no input)
# the lock-on pips come every 20 frames from the lock's first frame, none
# before.
# Env: FRAMES (900), BOOT_HOLD (input held from frame 120), MAME_BIOS_DIR, MAME,
# CRACK_CART (path to the crack-test cart), FRAME_MARK_CART (path to the
# frame-mark cart), MVS_BIOS_ZIP (source of the MVS BIOS set; default
# ~/ROMs/neogeo/neogeo.zip), MVS_COIN / MVS_START (the MVS input helper's
# holds; MVS_COIN=-100 disables the coin for the Task 2 failure demos);
# for best-aes: BEST_CARD_DIR (the memory-card file's directory, default
# $REPO/build/best-card), BEST_REUSE=1 (run 2: reuse run 1's card),
# BEST_NOCARD=1 (run 3: no -memcard).
# Boot timing: the cart's header turns the BIOS logo off (rom_eye_catcher_mode
# 2, the M8 fixes), so the AES title starts at MAME frame ~24 and the MVS one
# at ~299. Comments elsewhere that say the AES preamble is ~470 frames (title
# at ~477) or that MVS main() starts at ~749 date from the logo era: every
# frame-keyed number below still lands after the cart has started, so only
# the windows that had to fall on the title's first page were moved.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-text}"
CART="${CRACK_CART:-$REPO/build/rom/esrg.zip}"
if [[ "$MODE" == framemark ]]; then
    CART="${FRAME_MARK_CART:-$REPO/build/rom/esrg-framemark.zip}"
fi
if [[ "$MODE" == crackframemark ]]; then
    CART="${CRACK_FRAME_MARK_CART:-$REPO/build/rom/esrg-crackfm.zip}"
fi
if [[ "$MODE" == gameover-draw ]]; then
    CART="${GO_DRAW_CART:-$REPO/build/rom/esrg-godraw.zip}"
fi
if [[ "$MODE" == radar ]]; then
    CART="${RADAR_CART:-$REPO/build/rom/esrg-radartest.zip}"
fi
if [[ "$MODE" == sound || "$MODE" == sound-mvs ]]; then
    # the M7 Task 1 sound-pipeline test: the -DSOUND_TEST cart
    # (build/rom/esrg-soundtest.zip), which scripts five sound-command
    # sends on the title plus the two-in-one-frame pair, recording each
    # send in a RAM log. The probe needs the log's address (the static
    # sound_test_log / sound_test_n and the hook's title counter, found by
    # nm in the test ELF); the MVS leg runs the SAME cart under
    # `neogeo -bios euro -cart1 esrg`.
    CART="${SOUND_CART:-$REPO/build/rom/esrg-soundtest.zip}"
fi
if [[ "$MODE" == sound-game || "$MODE" == sound-radar ]]; then
    # the M7 Task 2 sound tests: the -DSOUND_TEST cart plays the
    # deterministic "sound game" (sound_game_probe.lua drives it) and logs
    # every game sound send; sound-radar uses the SOUND+RADAR_TEST cart
    # (build/rom/esrg-soundradar.zip: -DSOUND_TEST -DRADAR_TEST), so the
    # first missile aims at the resting ship and the lock-on pips happen
    # with NO probe input.
    if [[ "$MODE" == sound-radar ]]; then
        CART="${SOUND_RADAR_CART:-$REPO/build/rom/esrg-soundradar.zip}"
    else
        CART="${SOUND_CART:-$REPO/build/rom/esrg-soundtest.zip}"
    fi
fi
if [[ "$MODE" == flow || "$MODE" == flow-restart ]]; then
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
fi
if [[ "$MODE" == flow-pages || "$MODE" == flow-pages-c ]]; then
    # M6 Task 6: the title pages run (AES no-Start) and the C-turn run
    # (MVS). Both boot the plain NORMAL cart and need the title state's
    # BSS addresses (title_page / title_t / flow_entry), found by nm.
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
fi
if [[ "$MODE" == flow-level || "$MODE" == flow-return || "$MODE" == flow-return-best ]]; then
    # M6 Task 7: the level-select run (AES: B taps at 1000..1300, Start at
    # 1400, the game plays at the chosen level) and the no-B return run
    # (fresh boot page 0 / NORMAL, the Up-held game to GAME OVER, and the
    # returned title on the HIGH SCORES page). flow-return-best (M6 Task 9)
    # adds the backup-RAM high-score table reads (flow_best) so the checker
    # can prove the returned title shows the game's score. All three boot
    # the plain NORMAL cart and need the flow_level backup-RAM byte, the
    # static rules and the static mis addresses, found by nm.
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
fi
if [[ "$MODE" == best-mvs ]]; then
    # M6 Task 9: the MVS backup-RAM high-score proof (three runs sharing
    # or not sharing one nvram, see below). Boots the plain NORMAL cart
    # under `neogeo -bios euro -cart1 esrg` and needs flow_best (the
    # backup-RAM table), flow_level's marker pair, the static mis (for
    # score10) and the title state's addresses, found by nm.
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
fi
if [[ "$MODE" == best-aes ]]; then
    # M6 Task 10: the AES memory-card high-score proof (three runs, one
    # -memcard file shared by runs 1 and 2, none for run 3 — see below).
    # Boots the plain NORMAL cart under `aes -cart esrg` and needs the
    # flow_best backup-RAM table, the flow_level marker pair, the static
    # mis (for score10), the card-log words (card_log, the answers the
    # cart's card calls left) and the title state's addresses, found by
    # nm.
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
fi
OUT="$REPO/build/boot"

# Task 1: the MAME legs whose checkers replay the cart's game need the seed
# the cart used (mis_seed_used) and, for the first-missile proofs, the static
# `mis` (obj[0]'s ring/phi). One helper, so the eight checkers share one nm
# lookup and one MIS_* env pair instead of eight copies.
mis_select() {
    local elf=""
    case "$1" in
        hud|stars|collapse|ship-respawn|ship-respawn-nodeath|framemark|crackframemark)
            elf="$REPO/build/rom.elf"
            [[ "$1" == framemark ]] && elf="$REPO/build/rom-framemark.elf"
            [[ "$1" == crackframemark ]] && elf="$REPO/build/rom-crackframemark.elf" ;;
        gameover-draw) elf="$REPO/build/rom-gameoverdraw.elf" ;;
        radar)         elf="$REPO/build/rom-radartest.elf" ;;
        sound-game)    elf="$REPO/build/rom-soundtest.elf" ;;
        sound-radar)   elf="$REPO/build/rom-soundradar.elf" ;;
        flow|flow-restart|flow-pages|flow-pages-c|flow-level|flow-return|flow-return-best|\
        flow-mvs|flow-mvs-start|flow-mvs-norestart|best-mvs|best-aes)
            elf="$REPO/build/rom.elf" ;;
    esac
    [[ -n "$elf" ]] || return 0
    MIS_SEED_ADDR="$(m68k-neogeo-elf-nm "$elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis_seed_used" { print "0x" $1 }' \
        || nm "$elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis_seed_used" { print "0x" $1 }')"
    MIS_ADDR="$(m68k-neogeo-elf-nm "$elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    MIS_FIRST_VAL=0
    case "$1" in
        flow|flow-restart|flow-level|flow-return|flow-mvs-start|sound-game)
            MIS_FIRST_VAL=1 ;;      # the variety / first-missile proofs
    esac
}
mis_select "$MODE"

[[ -f "$CART" ]] || { echo "boot_test: $CART missing (run make)" >&2; exit 2; }

FLATPAK_MAME=/var/lib/flatpak/app/org.mamedev.MAME/x86_64/stable/active/files/bin/mame
if [[ -n "${MAME:-}" ]]; then read -r -a MAME_CMD <<< "$MAME"
elif [[ -x "$FLATPAK_MAME" ]]; then MAME_CMD=("$FLATPAK_MAME")
elif command -v mame >/dev/null; then MAME_CMD=(mame)
else echo "boot_test: no MAME (set MAME=)" >&2; exit 2; fi

BIOS_DIR="${MAME_BIOS_DIR:-$HOME/Development/emulators/roms/mame-neogeo}"
[[ -f "$BIOS_DIR/aes.zip" ]] || { echo "boot_test: $BIOS_DIR/aes.zip missing" >&2; exit 2; }

PROBE="boot_probe.lua"
if [[ "$MODE" == leftovers ]]; then PROBE="leftover_probe.lua"; fi
if [[ "$MODE" == cracks ]]; then PROBE="broken_probe.lua"; fi
if [[ "$MODE" == sound || "$MODE" == sound-mvs ]]; then PROBE="sound_probe.lua"; fi
if [[ "$MODE" == sound-game || "$MODE" == sound-radar ]]; then PROBE="sound_game_probe.lua"; fi
if [[ "$MODE" == collapse ]]; then PROBE="collapse_probe.lua"; fi
if [[ "$MODE" == framemark || "$MODE" == crackframemark ]]; then PROBE="frame_mark_probe.lua"; fi
if [[ "$MODE" == ship-respawn || "$MODE" == ship-respawn-nodeath ]]; then
    PROBE="ship_respawn_probe.lua"
    # the probe reads the cart's BSS debug exports (the cart frame counter
    # and the rules' alive flag) so it can time the death and respawn
    # exactly; find their addresses in the freshly built ELF
    SHIP_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    SHIP_RC_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules_dbg_alive" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules_dbg_alive" { print "0x" $1 }')"
    # the model's first death under the hold-Up policy is at cart frame
    # 486, the respawn at 604 (see tests/check_ship_respawn.py). The
    # nodeath mode runs the same probe but keeps the ship parked at the
    # start cell with no launches aimed at it: no death happens, and the
    # checker proves the ship's slots stayed word-identical. Task 1's seed
    # moves the hold-Up game's first death to fc 3687 (the model's frame;
    # 486 was the 0xACE1 game), so the respawn run needs ~3687 + 118 game
    # frames plus the ~603-frame game start: ~4,600 MAME frames.
    if [[ "$MODE" == ship-respawn ]]; then
        BOOT_FRAMES="${BOOT_FRAMES:-4600}"
        NODEATH_VAL=0
    else
        # the nodeath X dump needs fc >= 200; the title now starts the game
        # only on the Start window (MAME 600..604, so fc 1 is ~frame 603),
        # so the run must reach ~frame 803 + margin.
        BOOT_FRAMES="${BOOT_FRAMES:-1100}"
        NODEATH_VAL=1
    fi
fi
if [[ "$MODE" == cracks ]]; then
    # the probe samples only once the cart's main loop is running, using the
    # frame counter export (the BIOS preamble's sprites would otherwise
    # read), and snapshots when a front missile is over the broken top
    # cells (~cart fc 830). The AES BIOS preamble is ~470 MAME frames, so
    # the run needs ~1400 MAME frames to reach fc 830.
    BOOT_FRAMES="${BOOT_FRAMES:-1500}"
    HUD_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom-cracktest.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom-cracktest.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    # the test-only dome-angle override the probe sets for the permutation
    # leg (CRACK_ANGLE >= 48): its BSS address in the crack-test ELF
    CRACK_ANGLE_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom-cracktest.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "cracks_test_angle" { print "0x" $1 }' \
        || nm "$REPO/build/rom-cracktest.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "cracks_test_angle" { print "0x" $1 }')"
    CRACK_RULES_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom-cracktest.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }' \
        || nm "$REPO/build/rom-cracktest.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }')"
fi
if [[ "$MODE" == hud ]]; then
    PROBE="hud_probe.lua"
    # the probe reads the cart's BSS debug exports (a redraw count and the
    # cart's frame counter, hud_dbg_events / hud_framecnt) so it can prove
    # the HUD redraws only on change and align its reads to cart frames, and
    # the static `rules` (for the after-death snapshot's lives byte);
    # find their addresses in the freshly built ELF
    HUD_EVENTS_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_dbg_events" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_dbg_events" { print "0x" $1 }')"
    HUD_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    HUD_RULES_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 == "b" && $3 == "rules" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 == "b" && $3 == "rules" { print "0x" $1 }')"
    # the probe script needs to run past game over and the A restart. Task 1
    # seeds the missiles from the title's time: at the default 600 Start
    # (seed 0xaede) game 1's first death is at fc 3687 (the after-death
    # snapshot fires there), GAME OVER at fc 17525, and the A press at GAME
    # OVER + 71 restarts at ~fc 17596. Game 2 then needs a few hundred frames
    # with fire to score (the checker's "the score never grew" leg), so
    # ~20,400 MAME frames (game start ~603 + 17596 + the game-2 margin).
    BOOT_FRAMES="${BOOT_FRAMES:-20400}"
fi
if [[ "$MODE" == stars ]]; then
    PROBE="stars_probe.lua"
    # the stars turn with the ship's dome_angle: the probe reads it from the
    # static `ship` in RAM (found by m68k-neogeo-elf-nm; the checker replays
    # the ship model from the recorded inputs and proves the two agree).
    # The stick-right policy walks the dome_angle ring continuously, so
    # 1900 frames (cart fc up to ~1300 after the ~477-frame AES BIOS preamble
    # and the Start window that now leaves the title at M6 Task 1) covers
    # many turns and the 100 samples (fc 60..1050, sampled every 10).
    STARS_ANGLE_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 == "b" && $3 == "ship" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 == "b" && $3 == "ship" { print "0x" $1 }')"
    STARS_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    BOOT_FRAMES="${BOOT_FRAMES:-1900}"
fi
if [[ "$MODE" == radar ]]; then
    # the M5 Task 4 radar boot-test: the -DRADAR_TEST cart (radartest-cart)
    # whose first missile of each game targets the ship's start cell, so the
    # lock-on happens with no input. The probe reads the static `ship`, `mis`
    # and `radar` from RAM (their addresses come from the test ELF, found by
    # m68k-neogeo-elf-nm) and every radar slot's VRAM + the ellipse palette
    # entry; tests/check_radar.py computes the expected radar from the RAM
    # via tests/radar_model.py and compares within 1 px. ~2400 MAME frames
    # covers ~1920 cart frames: the first missile flies and locks for ~580
    # frames, lands, the ship dies and a new game's first missile locks
    # again — plenty of locked samples and the death/blips-gone behaviour.
    PROBE="radar_probe.lua"
    RADAR_ELF="$REPO/build/rom-radartest.elf"
    RADAR_MIS_ADDR="$(m68k-neogeo-elf-nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 == "b" && $3 == "mis" { print "0x" $1 }' \
        || nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 == "b" && $3 == "mis" { print "0x" $1 }')"
    RADAR_SHIP_ADDR="$(m68k-neogeo-elf-nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 == "b" && $3 == "ship" { print "0x" $1 }' \
        || nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 == "b" && $3 == "ship" { print "0x" $1 }')"
    RADAR_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    RADAR_RADAR_ADDR="$(m68k-neogeo-elf-nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 == "b" && $3 == "radar" { print "0x" $1 }' \
        || nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 == "b" && $3 == "radar" { print "0x" $1 }')"
    BOOT_FRAMES="${BOOT_FRAMES:-2400}"
fi
if [[ "$MODE" == sound || "$MODE" == sound-mvs ]]; then
    # the M7 Task 1 sound test's RAM exports: the static sound_test_log
    # (u8[32]: tf_lo, tf_hi, cmd, result quadrupels) and sound_test_n (the
    # next free slot) and the hook's own u16 title counter sound_test_fc —
    # all from the -DSOUND_TEST ELF (build/rom-soundtest.elf), found by nm.
    # The run needs to reach title frame 400 (the last send: the
    # two-in-one frame), so ~1100 MAME frames: the ~477-frame AES BIOS
    # preamble + 400 title frames + margin. The MVS leg runs the same cart
    # under the MVS BIOS (`neogeo -bios euro -cart1 esrg`).
    SOUND_ELF="$REPO/build/rom-soundtest.elf"
    SOUND_LOG_ADDR="$(m68k-neogeo-elf-nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_log" { print "0x" $1 }' \
        || nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_log" { print "0x" $1 }')"
    SOUND_LOGN_ADDR="$(m68k-neogeo-elf-nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_n" { print "0x" $1 }' \
        || nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_n" { print "0x" $1 }')"
    SOUND_TITLE_FC_ADDR="$(m68k-neogeo-elf-nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_fc" { print "0x" $1 }' \
        || nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_fc" { print "0x" $1 }')"
    # AES: ~1100 MAME frames (the ~477-frame preamble + title frame 400 +
    # margin). MVS: the BIOS's own preamble and RAM clear run longer, and
    # the cart's main() is entered ~270 frames later (~frame 749): 1200.
    if [[ "$MODE" == sound-mvs ]]; then
        BOOT_FRAMES="${BOOT_FRAMES:-1200}"
    else
        BOOT_FRAMES="${BOOT_FRAMES:-1100}"
    fi
fi
if [[ "$MODE" == sound-game ]]; then
    # the M7 Task 2 sound-game test: the same -DSOUND_TEST cart now plays
    # the deterministic "sound game" (TRIAL-928 policy) and records every
    # game sound command in the game log (sound_test_glog / sound_test_gn)
    # with its game-session frame, and also exposes hud_framecnt for the
    # probe's cart-frame alignment. Task 1 seeds the missiles from the
    # title's time: at the default 600 Start (seed 0xaede) the game reaches
    # GAME OVER at fc 27142 (the model's derivation; 24963 with RNG_SEED;
    # the taps stop at 27105), so the run needs the ~24-frame AES preamble +
    # ~27142 game frames + the 295-frame GAME OVER window + margin: ~28,000
    # MAME frames.
    SOUND_ELF="$REPO/build/rom-soundtest.elf"
    SOUND_ELF_E=""
    SOUND_GLOG_ADDR="$(m68k-neogeo-elf-nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_glog" { print "0x" $1 }' \
        || nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_glog" { print "0x" $1 }')"
    SOUND_GN_ADDR="$(m68k-neogeo-elf-nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_gn" { print "0x" $1 }' \
        || nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_gn" { print "0x" $1 }')"
    SOUND_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    BOOT_FRAMES="${BOOT_FRAMES:-28200}"
fi
if [[ "$MODE" == sound-radar ]]; then
    # the M7 Task 2 locked-radar test: the SOUND+RADAR_TEST cart's first
    # missile aims at the resting ship (cell 27) — the lock-on happens by
    # itself, the probe holds NO input — so the pips must come every 20
    # frames from the lock's first frame and none before. Short run: the
    # first lock is at cart fc ~60 and the first missile lands ~fc 600;
    # ~2,500 MAME frames covers the lock + several pips + margin.
    SOUND_ELF="$REPO/build/rom-soundradar.elf"
    SOUND_GLOG_ADDR="$(m68k-neogeo-elf-nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_glog" { print "0x" $1 }' \
        || nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_glog" { print "0x" $1 }')"
    SOUND_GN_ADDR="$(m68k-neogeo-elf-nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_gn" { print "0x" $1 }' \
        || nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "sound_test_gn" { print "0x" $1 }')"
    SOUND_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$SOUND_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    SOUND_RADAR_VAL=1
    BOOT_FRAMES="${BOOT_FRAMES:-2500}"
fi
if [[ "$MODE" == collapse || "$MODE" == framemark || "$MODE" == crackframemark ]]; then
    # the frame counter and the measurement exports come from the ELF
    COLLAPSE_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    # a full game to GAME OVER with the centred policy: first dome death
    # fc 8359, rebuild 8477, GAME OVER 27142 (the model's derivation under
    # Task 1's seed; 8202/8320/24963 with RNG_SEED — see
    # tests/check_collapse.py). The game starts at MAME ~603, so GAME OVER
    # lands at MAME ~27745: ~28,100 MAME frames covers it (at ~20k frames
    # /34 s ≈ 48 s).
    BOOT_FRAMES="${BOOT_FRAMES:-28100}"
fi
if [[ "$MODE" == framemark || "$MODE" == crackframemark ]]; then
    FM_ELF="$REPO/build/rom-framemark.elf"
    if [[ "$MODE" == crackframemark ]]; then
        FM_ELF="$REPO/build/rom-crackframemark.elf"
    fi
    # the frame counter of THIS cart: the framemark builds lay out RAM
    # differently from rom.elf (M6: reading rom.elf's address left fc at 0
    # and the measurement covered the title only)
    COLLAPSE_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$FM_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    END_ADDR="$(m68k-neogeo-elf-nm "$FM_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_end_mark" { print "0x" $1 }' \
        || nm "$FM_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_end_mark" { print "0x" $1 }')"
    MAX_ADDR="$(m68k-neogeo-elf-nm "$FM_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_max_mark" { print "0x" $1 }' \
        || nm "$FM_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_max_mark" { print "0x" $1 }')"
    MIN_ADDR="$(m68k-neogeo-elf-nm "$FM_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_min_mark" { print "0x" $1 }' \
        || nm "$FM_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_min_mark" { print "0x" $1 }')"
    START_ADDR="$(m68k-neogeo-elf-nm "$FM_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_start_mark" { print "0x" $1 }' \
        || nm "$FM_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_start_mark" { print "0x" $1 }')"
fi
if [[ "$MODE" == gameover-draw ]]; then
    # the probe reads the test cart's go_test_dbg (the hook's per-frame
    # event byte) and the cart frame counter; both come from the ELF. The
    # scripted game reaches the phase-2 GAME OVER at the model's frame
    # (Task 1's seed moved it: the phase-1 dome death is fc 8359, its GAME
    # OVER 8477, the A restart 8537, phase 2's park/seed 8548 and its cell
    # death ~8567), so ~9700 MAME frames covers it with the preamble.
    PROBE="gameover_draw_probe.lua"
    GO_TEST_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom-gameoverdraw.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "go_test_dbg" { print "0x" $1 }' \
        || nm "$REPO/build/rom-gameoverdraw.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "go_test_dbg" { print "0x" $1 }')"
    GO_FRESH_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom-gameoverdraw.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom-gameoverdraw.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    BOOT_FRAMES="${BOOT_FRAMES:-9700}"
fi
if [[ "$MODE" == flow || "$MODE" == flow-restart ]]; then
    # the M6 Task 1 flow boot-test: boots the NORMAL cart and proves the
    # title > Start > game > GAME OVER flow. The probe overrides the Start
    # window to MAME frames 1200..1204 (so the title runs for over a
    # second), holds Up from the game's first frame to reach the model's
    # GAME OVER under Task 1's seed (fc 8188; 6509 with RNG_SEED), and
    # either lets the 295-frame window expire (return to the title) or
    # presses A at GAME OVER + 60 (a new game). The run must cover the
    # ~24-frame preamble (no BIOS logo) + ~1176 title frames (Start at
    # 1200) + the game to fc 8188 + the 300-frame return + the ~200-frame
    # BIOS rebuild: 1200 + 8188 + 500 ~= 9900 MAME frames.
    PROBE="flow_probe.lua"
    # the probe reads the cart's game-session frame counter; find it in the
    # freshly built ELF
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    if [[ "$MODE" == flow ]]; then
        FLOW_RESTART_VAL=0
        BOOT_FRAMES="${BOOT_FRAMES:-10200}"
    else
        FLOW_RESTART_VAL=1
        # the restart leg holds Up to the model's GAME OVER (fc 8188 at
        # MAME ~1201 + 8188 = 9389) then presses A and samples the new game
        # to fc GAME OVER + 96 (~MAME 9485), so ~9700 MAME frames cover it
        # (the game begins at MAME ~1201 after the 1200..1204 Start and the
        # 24-frame preamble).
        BOOT_FRAMES="${BOOT_FRAMES:-9700}"
    fi
    # the flow probe overrides the Start window so the title runs for over
    # a second before the game begins (proof a needs ~720 title frames)
    SG_BEGIN="${SG_BEGIN:-1200}"
    SG_END="${SG_END:-1204}"
fi
if [[ "$MODE" == flow-level || "$MODE" == flow-return || "$MODE" == flow-return-best ]]; then
    # the M6 Task 7 legs. flow-level (AES, no Start until 1400): the title
    # runs from ~frame 477; B is tapped on 1000/1100/1200/1300 (each
    # NORMAL->HARD->EASY->NORMAL->HARD on page 0, title_t 0), then Start on
    # 1400..1404 begins a game whose rules.level/mis.level read the chosen
    # level (HARD) on the first game frame — the run must cover the game's
    # opening frames, ~1700 MAME frames. flow-return (AES, no B): the
    # fresh boot must show page 0/NORMAL; the Up-held game runs to the
    # model's GAME OVER (Task 1's seed at the default 600..604 Start:
    # fc 17525; 6509 with RNG_SEED) at NORMAL, the 295-frame window
    # expires, and the returned title opens on page 1 (HIGH SCORES) —
    # ~18,400 MAME frames (the game begins at ~MAME 603).
    # flow-return-best (M6 Task 9) is the same return run with the best
    # table's reads enabled.
    PROBE="flow_probe.lua"
    FLOW_LEVEL_VAL=0
    FLOW_RETURN_VAL=0
    FLOW_BEST_RETURN_VAL=0
    if [[ "$MODE" == flow-level ]]; then
        FLOW_LEVEL_VAL=1
        BOOT_FRAMES="${BOOT_FRAMES:-1700}"
        # the level run's Start override: 1400..1404 (the task's plan)
        SG_BEGIN="${SG_BEGIN:-1400}"
        SG_END="${SG_END:-1404}"
    else
        FLOW_RETURN_VAL=1
        BOOT_FRAMES="${BOOT_FRAMES:-19200}"
        if [[ "$MODE" == flow-return-best ]]; then
            FLOW_BEST_RETURN_VAL=1
        fi
    fi
    # the task-7 RAM addresses (the backup-RAM pair's VALID marker — the
    # probe reads the marker at this address and the level at +1 —, the
    # static rules and the static mis) from the freshly built ELF
    FLOW_LEVEL_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }')"
    FLOW_RULES_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }')"
    FLOW_MIS_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    # M6 Task 9: the backup-RAM high-score table (flow_best) for the
    # flow-return-best leg (and the best-mvs mode, which sets its own)
    FLOW_BEST_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_best" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_best" { print "0x" $1 }')"
    # the title state's addresses (page/t/entry) for the returned-title and
    # page-0 checks
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_ENTRY_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }')"
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
fi
if [[ "$MODE" == flow-mvs || "$MODE" == flow-mvs-start || "$MODE" == flow-mvs-norestart ]]; then
    # the M6 Task 2 MVS legs (flow-mvs / flow-mvs-start) and the M6 Task 4
    # leg (flow-mvs-norestart): the same NORMAL cart under the MVS BIOS
    # (`neogeo -bios euro -cart1 esrg`). The probe (flow_probe.lua with
    # FLOW_MVS=1) writes bios_mvs_flag, bios_compulsion_timer and
    # hud_framecnt every frame; scripts/mvs_input.lua holds "Coin 1" on
    # MVS_COIN..+4 (1500) and "1 Player Start" on MVS_START..+4 (-100: never —
    # the countdown leg; 1800 — the Start and norestart legs). The runs
    # cover the coin at 1500, the BIOS's own player_start at frame 3312
    # (countdown out), or the Start at 1800, with margin: 3500 frames for
    # the pure countdown leg. The norestart leg (FLOW_NORESTART=1) drives
    # the game itself (P1 Up, A at GAME OVER + 60) and the probe reads the
    # cart's static `rules` from RAM (nm `rules`) so the checker can prove
    # A did not restart and the 295-frame return happened: the run covers
    # the game to fc 16551 (Task 1's seed 0xadf9; 6509 with RNG_SEED) +
    # the 295-frame window + the ~200-frame BIOS rebuild + margin,
    # ~19,200 MAME frames.
    PROBE="flow_probe.lua"
    FLOW_MVS_VAL=1
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    # M6 Task 6: the MVS title rows' page-0 gate (the checker reads the
    # page the rows were drawn on from the T records)
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_ENTRY_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }')"
    if [[ "$MODE" == flow-mvs ]]; then
        MVS_START_VAL=-100
        # the countdown leg: the BIOS's own player_start comes at ~frame 3312
        BOOT_FRAMES="${BOOT_FRAMES:-3500}"
    elif [[ "$MODE" == flow-mvs-start ]]; then
        MVS_START_VAL="${MVS_START:-1800}"
        # the Start leg: the game begins at ~frame 1802
        BOOT_FRAMES="${BOOT_FRAMES:-2600}"
    else
        MVS_START_VAL="${MVS_START:-1800}"
        FLOW_NORESTART_VAL=1
        FLOW_RULES_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
            | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }' \
            || nm "$REPO/build/rom.elf" 2>/dev/null \
            | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }')"
        # the start leg + the Up-held game to the model's GAME OVER (fc
        # 16551 under Task 1's seed 0xadf9; 6509 with RNG_SEED) + the
        # 295-frame window + the ~200-frame BIOS rebuild + margin:
        # ~1802 + 16551 + 500 = ~18,850 MAME frames
        BOOT_FRAMES="${BOOT_FRAMES:-19200}"
    fi
fi

if [[ "$MODE" == best-mvs ]]; then
    # the M6 Task 9 MVS high-score proof: three runs of
    # `neogeo -bios euro -cart1 esrg`. Run 1 (BEST_RUN=1) plays the
    # scoring game (Right held + A every 11 frames) to GAME OVER (fc 20240
    # under Task 1's seed 0xadf9; coin at 1500, Start at 1800 — the game
    # begins at ~1802), reads mis.score10 at GAME OVER (> 0), waits for the
    # high-scores return, and checks flow_best in RAM is valid and holds
    # the score. Run 2 (BEST_RUN=2) reuses run 1's nvram and proves the
    # FIRST page-0 frame's row 7 shows the persisted score before any game.
    # Run 3 (BEST_RUN=3) uses a FRESH nvram and proves row 7 reads "0" (no
    # garbage, no crash). boot_test.sh is called once per run with
    # BEST_RUN and BEST_NVRAM_DIR set by the Makefile's best-mvs target
    # (BEST_REUSE=1 for run 2, 0 otherwise).
    PROBE="flow_probe.lua"
    FLOW_BEST_VAL=1
    FLOW_MVS_VAL=1
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_ENTRY_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }')"
    FLOW_LEVEL_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }')"
    FLOW_MIS_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    FLOW_BEST_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_best" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_best" { print "0x" $1 }')"
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    # the run kind: run 1 (default) plays the scoring game (the game
    # begins at MAME ~1802 with the coin at 1500 and Start at 1800, and
    # ends at the model's GAME OVER, fc 20240 under Task 1's seed 0xadf9;
    # 24963 with RNG_SEED, so ~MAME 22042) plus the 295-frame window and
    # the ~200-frame BIOS rebuild: ~22,600 MAME frames, with margin.
    # Run 2 (BEST_REUSE=1)
    # and run 3 (BEST_FRESH=1) only sit on the title: run 2 opens on page
    # 1 (the persisted open-high-scores byte) and its first page-0 frame
    # comes only after a full 9-page cycle (~8 x 295 title frames after
    # the page-1 entry, ~MAME 3100) — the proof keys on that page-0 row 7,
    # so the run needs ~3300 frames; run 3 (a fresh nvram) opens on page 0
    # early, but shares the same budget.
    if [[ "${BEST_REUSE:-0}" == "1" || "${BEST_FRESH:-0}" == "1" ]]; then
        BOOT_FRAMES="${BOOT_FRAMES:-3300}"
        MVS_START_VAL="-100"
    else
        BOOT_FRAMES="${BOOT_FRAMES:-23000}"
        MVS_START_VAL="${MVS_START:-1800}"
    fi
fi

if [[ "$MODE" == best-aes ]]; then
    # the M6 Task 10 AES memory-card proof: three runs of `aes -cart
    # esrg`. Run 1 (BEST_REUSE=0, BEST_NOCARD=0) starts from a FRESH card
    # file (rm -rf'd below) and a FRESH nvram/cfg: the first entry LOADs
    # the (unformatted) card — answer 0x81 — then the scoring game runs
    # to GAME OVER (fc 17818 under Task 1's seed 0xaede; 24963 with
    # RNG_SEED) with score10 > 0, best_update changes the
    # table, and the SAVE answers 0x81, FORMAT answers 0, SAVE answers 0
    # (the card_log records, read from RAM). The returned title opens on
    # page 1 (HIGH SCORES) whose NORMAL row shows the score. Run 2
    # (BEST_REUSE=1) reuses run 1's card file with a FRESH nvram/cfg (a
    # power-off: backup RAM empty): the entry LOADs the card (answer 0)
    # and the FIRST page-0 frame's row 7 shows the same score before any
    # game. Run 3 (BEST_NOCARD=1) passes no -memcard: the load answers
    # 0x80, the first page-0 frame's row 7 reads "0", no crash, and a
    # game to GAME OVER still keeps the score in backup RAM for the run.
    PROBE="flow_probe.lua"
    FLOW_BEST_VAL=1
    FLOW_BEST_AES_VAL=1
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_ENTRY_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }')"
    FLOW_LEVEL_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }')"
    FLOW_MIS_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    FLOW_BEST_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_best" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_best" { print "0x" $1 }')"
    FLOW_CARDLOG_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "card_log" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "card_log" { print "0x" $1 }')"
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    # the run kind: run 2 (BEST_REUSE=1) only sits on the title (no Start)
    # and needs just the first page-0 frame (~MAME 500): 1400 frames. Runs
    # 1 and 3 play the scoring game (Right held + A every 11 frames) to the
    # model's GAME OVER (fc 17818 under Task 1's seed 0xaede from the
    # ~frame 603 Start, so ~MAME 18422; 24963 with RNG_SEED) plus the
    # 295-frame window and the ~200-frame BIOS rebuild: ~19,000 MAME
    # frames, with margin.
    if [[ "${BEST_REUSE:-0}" == "1" ]]; then
        BOOT_FRAMES="${BOOT_FRAMES:-1500}"
        SG_ENABLE_VAL=0          # run 2 plays no game: the first page-0
                                 # frame is the proof, before any Start
    else
        BOOT_FRAMES="${BOOT_FRAMES:-19600}"
    fi
fi

if [[ "$MODE" == flow-pages || "$MODE" == flow-pages-c ]]; then
    # the M6 Task 6 legs. flow-pages (AES, no Start at all, 3300 frames):
    # the title starts at ~frame 24 (no BIOS logo since the M8 fixes),
    # so the 8 -> 0 wrap (9 x 295 title frames) lands at ~2680 inside the
    # run — the checker proves the page turned every 295 frames, that every
    # sampled title frame's fix rows equal tests/title_model.py (the
    # page/level/t/credits read from RAM in the same frame via the T
    # records), and the dome's SCB words / snapshots at the page PINs prove
    # the dome is chained on page 0, hidden on pages 1..8, and rebuilt
    # word-equal after the wrap. flow-pages-c (MVS, no coin/Start): the
    # title starts at ~frame 299, so page 0 spans ~299..592; a C tap on MAME
    # frames 450 and 550 turns 0 -> 1 -> 2 (within 2 frames), with title_t
    # reset to 0 — and the dome dumps at pages 0/1/2 prove the hidden
    # pages. Drives the C taps through the :edge:joy:JOY1 port (the AES
    # :ctrl1: fields do not exist on the MVS machine).
    PROBE="flow_probe.lua"
    FLOW_PAGES_VAL=0
    FLOW_PAGES_C_VAL=0
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_ENTRY_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }')"
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$REPO/build/rom.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    if [[ "$MODE" == flow-pages ]]; then
        FLOW_PAGES_VAL=1
        # the run must reach the 8 -> 0 wrap at ~24 + 9 x 295 = 2679 plus
        # margin (the no-logo title starts at MAME ~24)
        BOOT_FRAMES="${BOOT_FRAMES:-2900}"
        # no Start for the whole run: the pages must turn on their own
        SG_ENABLE_VAL=0
        FLOW_DOME_SNAP_VAL="${FLOW_DOME_SNAP:-1}"
    else
        # flow-pages-c is an MVS run (the C taps need the MVS P1 port): the
        # probe keys its MVS branch on FLOW_MVS
        FLOW_MVS_VAL=1
        FLOW_PAGES_C_VAL=1
        # the C turns at 450 and 550 are inside page 0 (~299..592); page 2
        # then runs to ~850, so 1700 frames cover the proof
        BOOT_FRAMES="${BOOT_FRAMES:-1700}"
        FLOW_DOME_SNAP_VAL="${FLOW_DOME_SNAP:-1}"
        MVS_COIN_SET="-100"
    fi
fi

rm -rf "$OUT"; mkdir -p "$OUT/roms" "$OUT/hash" "$OUT/snap"
if [[ "$MODE" == flow-mvs || "$MODE" == flow-mvs-start || "$MODE" == flow-mvs-norestart \
      || "$MODE" == flow-pages-c || "$MODE" == best-mvs || "$MODE" == sound-mvs ]]; then
    # the MVS BIOS set, repacked the same way aes.zip is: MAME's flatpak zip
    # reader rejects the source archive as it is (deflate), so copy every
    # member into a fresh ZIP_STORED zip beside esrg.zip. A fresh
    # -nvram_directory per run keeps the backup RAM from carrying state
    # between runs, exactly as the AES legs treat their nvram.
    cp -f "$CART" "$OUT/roms/esrg.zip"
    MVS_BIOS_ZIP="${MVS_BIOS_ZIP:-$HOME/ROMs/neogeo/neogeo.zip}"
    [[ -f "$MVS_BIOS_ZIP" ]] || { echo "boot_test: $MVS_BIOS_ZIP missing" >&2; exit 2; }
    python3 - "$MVS_BIOS_ZIP" "$OUT/roms/neogeo.zip" <<'PYEOF'
import sys, zipfile
src, dst = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(src) as z:
    members = z.infolist()
    if not members:
        sys.exit(f"boot_test: {src} is empty")
    data = {m.filename: z.read(m) for m in members}
with zipfile.ZipFile(dst, "w", zipfile.ZIP_STORED) as z:
    for m in members:
        z.writestr(m, data[m.filename])
print(f"boot_test: staged MVS BIOS {len(members)} members -> {dst}")
PYEOF
else
    cp -f "$BIOS_DIR/aes.zip" "$OUT/roms/aes.zip"
    cp -f "$CART" "$OUT/roms/esrg.zip"
fi
python3 "$REPO/scripts/mame_softlist.py" "$CART" "$OUT/hash" --name esrg --description "E-SRG" >/dev/null

# the MVS legs run the MVS machine with the MVS BIOS and the MVS input
# helper's holds; everything else runs the AES machine exactly as before.
DRIVER="aes"
CART_ARG="-cart esrg"
if [[ "$MODE" == flow-mvs || "$MODE" == flow-mvs-start || "$MODE" == flow-mvs-norestart \
      || "$MODE" == flow-pages-c || "$MODE" == best-mvs || "$MODE" == sound-mvs ]]; then
    DRIVER="neogeo"
    CART_ARG="-cart1 esrg -bios euro"
fi

# the best-mvs nvram handling: all three runs use BEST_NVRAM_DIR as the
# nvram directory (the state lives outside $OUT, which is rm -rf'd at the
# top of every run). Run 1 (BEST_REUSE=0) and run 3 (BEST_REUSE=0) start
# from a FRESH directory; run 2 (BEST_REUSE=1) reuses run 1's — the whole
# point of the proof: the BIOS persisted the _backup_ram block there when
# it entered attract mode after the game, and run 2's entry must load it
# back and show it on the title before any game.
BEST_NVRAM_DIR="${BEST_NVRAM_DIR:-$REPO/build/best-nvram}"
NVRAM_D="$OUT/nvram"
if [[ "$MODE" == best-mvs ]]; then
    NVRAM_D="$BEST_NVRAM_DIR"
    if [[ "${BEST_REUSE:-0}" == "1" ]]; then
        [[ -d "$NVRAM_D" ]] || { echo "boot_test: best-mvs run 2 needs run 1's nvram at $NVRAM_D" >&2; exit 2; }
    else
        rm -rf "$NVRAM_D"
        mkdir -p "$NVRAM_D"
    fi
fi

# the best-aes memory-card handling (M6 Task 10): the card file lives
# outside $OUT (rm -rf'd every run) in BEST_CARD_DIR. Run 1 (BEST_REUSE=0,
# BEST_NOCARD=0) and run 2 (BEST_REUSE=1, sharing run 1's card) use one
# file: run 1 starts from a FRESH one the way the task wants ("the file
# must not exist"), run 2 reuses it — a power-off, whose proof is that
# the card, not the per-boot backup RAM, kept the score. Run 3
# (BEST_NOCARD=1) passes no -memcard at all. The nvram/cfg are fresh per
# run as usual (only the card crosses runs).
BEST_CARD_DIR="${BEST_CARD_DIR:-$REPO/build/best-card}"
CARD_ARG=""
if [[ "$MODE" == best-aes ]]; then
    if [[ "${BEST_NOCARD:-0}" == "1" ]]; then
        # run 3: no card at all (the load answers 0x80, no crash)
        :
    else
        mkdir -p "$BEST_CARD_DIR"
        CARD_FILE="$BEST_CARD_DIR/card.neo"
        if [[ "${BEST_REUSE:-0}" == "1" ]]; then
            [[ -f "$CARD_FILE" ]] || { echo "boot_test: best-aes run 2 needs run 1's card at $CARD_FILE" >&2; exit 2; }
        else
            rm -f "$CARD_FILE"          # run 1: "the file must not exist"
        fi
        # MAME's -memcard takes (and creates, with a nonfatal first-run
        # warning) the image file. Use an absolute path: the flatpak
        # resets MAME's working directory.
        CARD_ARG="-memcard $CARD_FILE"
    fi
fi

# the sound modes record the session's audio with -wavwrite (the M7 Task 1
# proof: the checker measures the WAV silently-before / loud-after every
# send and the audible lengths; the M7 Task 2 game mode measures the same
# for sampled sends). -sound none still records the emulated audio to the
# WAV (the flatpak has no audio device here; the writer is sound-source
# based, not output based). An absolute path: the flatpak resets MAME's
# working directory.
WAV_ARG=""
SOUND_WAV=""
if [[ "$MODE" == sound || "$MODE" == sound-mvs || "$MODE" == sound-game || "$MODE" == sound-radar ]]; then
    SOUND_WAV="$OUT/sound.wav"
    WAV_ARG="-wavwrite $SOUND_WAV"
fi

FRAMES="${FRAMES:-${BOOT_FRAMES:-900}}" HOLD="${BOOT_HOLD:-}" OUT="$OUT/probe.txt" \
    REPO="$REPO" \
    HUD_EVENTS_ADDR="${HUD_EVENTS_ADDR:-0}" HUD_FRAMECNT_ADDR="${HUD_FRAMECNT_ADDR:-0}" \
    COLLAPSE_FRAMECNT_ADDR="${COLLAPSE_FRAMECNT_ADDR:-0}" \
    SHIP_FRAMECNT_ADDR="${SHIP_FRAMECNT_ADDR:-0}" SHIP_RC_ADDR="${SHIP_RC_ADDR:-0}" \
    SHIP_NODEATH="${NODEATH_VAL:-0}" \
    HUD_RULES_ADDR="${HUD_RULES_ADDR:-0}" \
    GO_TEST_ADDR="${GO_TEST_ADDR:-0}" GO_FRESH_ADDR="${GO_FRESH_ADDR:-0}" \
    END_ADDR="${END_ADDR:-0}" MAX_ADDR="${MAX_ADDR:-0}" MIN_ADDR="${MIN_ADDR:-0}" \
    START_ADDR="${START_ADDR:-0}" \
    CRACK_ANGLE="${CRACK_ANGLE:-0}" CRACK_ANGLE_ADDR="${CRACK_ANGLE_ADDR:-0}" \
    CRACK_RULES_ADDR="${CRACK_RULES_ADDR:-0}" \
    STARS_ANGLE_ADDR="${STARS_ANGLE_ADDR:-0}" STARS_FRAMECNT_ADDR="${STARS_FRAMECNT_ADDR:-0}" \
    RADAR_MIS_ADDR="${RADAR_MIS_ADDR:-0}" RADAR_SHIP_ADDR="${RADAR_SHIP_ADDR:-0}" \
    RADAR_FRAMECNT_ADDR="${RADAR_FRAMECNT_ADDR:-0}" \
    RADAR_RADAR_ADDR="${RADAR_RADAR_ADDR:-0}" \
    SG_BEGIN="${SG_BEGIN:-600}" SG_END="${SG_END:-604}" SG_ENABLE="${SG_ENABLE_VAL:-${SG_ENABLE:-1}}" \
    FLOW_RESTART="${FLOW_RESTART_VAL:-0}" FLOW_FRAMECNT_ADDR="${FLOW_FRAMECNT_ADDR:-0}" \
    FLOW_MVS="${FLOW_MVS_VAL:-0}" MVS_COIN="${MVS_COIN_SET:-${MVS_COIN:-1500}}" \
    FLOW_NORESTART="${FLOW_NORESTART_VAL:-0}" FLOW_RULES_ADDR="${FLOW_RULES_ADDR:-0}" \
    FLOW_PAGES="${FLOW_PAGES_VAL:-0}" FLOW_PAGES_C="${FLOW_PAGES_C_VAL:-0}" \
    FLOW_PAGE_ADDR="${FLOW_PAGE_ADDR:-0}" FLOW_T_ADDR="${FLOW_T_ADDR:-0}" \
    FLOW_ENTRY_ADDR="${FLOW_ENTRY_ADDR:-0}" FLOW_DOME_SNAP="${FLOW_DOME_SNAP_VAL:-0}" \
    FLOW_LEVEL="${FLOW_LEVEL_VAL:-0}" FLOW_RETURN="${FLOW_RETURN_VAL:-0}" \
    FLOW_LEVEL_ADDR="${FLOW_LEVEL_ADDR:-0}" FLOW_MIS_ADDR="${FLOW_MIS_ADDR:-0}" \
    FLOW_BEST="${FLOW_BEST_VAL:-0}" FLOW_BEST_RETURN="${FLOW_BEST_RETURN_VAL:-0}" \
    FLOW_BEST_ADDR="${FLOW_BEST_ADDR:-0}" \
    FLOW_BEST_AES="${FLOW_BEST_AES_VAL:-0}" FLOW_CARDLOG_ADDR="${FLOW_CARDLOG_ADDR:-0}" \
    SOUND_LOG_ADDR="${SOUND_LOG_ADDR:-0}" SOUND_LOGN_ADDR="${SOUND_LOGN_ADDR:-0}" \
    SOUND_TITLE_FC_ADDR="${SOUND_TITLE_FC_ADDR:-0}" \
    SOUND_GLOG_ADDR="${SOUND_GLOG_ADDR:-0}" SOUND_GN_ADDR="${SOUND_GN_ADDR:-0}" \
    SOUND_FRAMECNT_ADDR="${SOUND_FRAMECNT_ADDR:-0}" \
    SOUND_RADAR_MODE="${SOUND_RADAR_VAL:-0}" \
    SOUND_GAME_POLICY="${SOUND_GAME_POLICY:-centred}" \
    MVS_START="${MVS_START_VAL:--100}" \
    MIS_SEED_ADDR="${MIS_SEED_ADDR:-0}" MIS_ADDR="${MIS_ADDR:-0}" \
    MIS_PROBE_FIRST="${MIS_FIRST_VAL:-0}" \
timeout -s KILL 120 "${MAME_CMD[@]}" -rompath "$OUT/roms" -hashpath "$OUT/hash" \
    -video none -sound none -nothrottle -skip_gameinfo \
    -cfg_directory "$OUT/cfg" -nvram_directory "$NVRAM_D" -snapshot_directory "$OUT/snap" -autoboot_script "$REPO/scripts/${PROBE}" \
    ${WAV_ARG:-} $DRIVER $CARD_ARG $CART_ARG >"$OUT/mame.log" 2>&1 || true

[[ -f "$OUT/probe.txt" ]] || { echo "boot_test: MAME produced no probe output"; tail -20 "$OUT/mame.log"; exit 1; }
cat "$OUT/probe.txt"
grep -q "pc_in_cart=1" "$OUT/probe.txt" || { echo "boot_test: FAIL — the 68k never reached cart space"; exit 1; }
# the hud mode's probe takes TWO snapshots (the fc-100 one and the one at
# the first death): the checker indexes the PNGs in the snapshot dir in
# order, so the copy must be the FIRST one (0000.png) and the dir must keep
# both. mapfile reads sort's whole output (no early pipe close: a `| head`
# would SIGPIPE sort once there is more than one PNG, and set -o pipefail
# would kill the script).
mapfile -t _PNGS < <(find "$OUT/snap" -name '*.png' | sort)
SNAP_SRC="${_PNGS[0]:-}"
[[ -n "$SNAP_SRC" ]] || { echo "boot_test: FAIL — no snapshot"; exit 1; }
cp "$SNAP_SRC" "${SNAP:-$OUT/snap.png}"
if [[ "$MODE" == leftovers ]]; then
    python3 "$REPO/tests/check_leftovers.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"
elif [[ "$MODE" == cracks ]]; then
    python3 "$REPO/tests/check_broken.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"
elif [[ "$MODE" == collapse ]]; then
    python3 "$REPO/tests/check_collapse.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" "$COLLAPSE_FRAMECNT_ADDR"
elif [[ "$MODE" == framemark || "$MODE" == crackframemark ]]; then
    FM_TAG=""
    if [[ "$MODE" == crackframemark ]]; then
        FM_TAG="crackframemark"   # no collapse happens (the hook keeps the dome whole)
    fi
    python3 "$REPO/tests/check_frame_mark.py" "$OUT/probe.txt" "$END_ADDR" "$FM_TAG"
elif [[ "$MODE" == ship-respawn || "$MODE" == ship-respawn-nodeath ]]; then
    SHIP_NODEATH="${NODEATH_VAL:-0}" python3 "$REPO/tests/check_ship_respawn.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$SHIP_FRAMECNT_ADDR" "$SHIP_RC_ADDR"
elif [[ "$MODE" == hud ]]; then
    python3 "$REPO/tests/check_hud.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" "$HUD_EVENTS_ADDR"
elif [[ "$MODE" == gameover-draw ]]; then
    python3 "$REPO/tests/check_gameover_draw.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"  \
        "$GO_TEST_ADDR" "$GO_FRESH_ADDR"
elif [[ "$MODE" == stars ]]; then
    python3 "$REPO/tests/check_stars.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$STARS_ANGLE_ADDR" "$STARS_FRAMECNT_ADDR"
elif [[ "$MODE" == radar ]]; then
    python3 "$REPO/tests/check_radar.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$RADAR_MIS_ADDR" "$RADAR_SHIP_ADDR" "$RADAR_FRAMECNT_ADDR"
    # the snapshot with a locked missile on the radar, for the user and the
    # orchestrator (the task's proof 5)
    cp "${SNAP:-$OUT/snap.png}" "$REPO/docs/superpowers/m5-radar.png"
elif [[ "$MODE" == sound || "$MODE" == sound-mvs ]]; then
    # the M7 Task 1 sound check: every send acknowledged, and the recorded
    # WAV is silent before each send and loud right after, with the
    # audible length matching the sample's (the MVS leg passes "mvs").
    [[ -f "$SOUND_WAV" ]] || { echo "boot_test: FAIL — no sound WAV at $SOUND_WAV"; exit 1; }
    if [[ "$MODE" == sound-mvs ]]; then
        python3 "$REPO/tests/check_sound.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" "$SOUND_WAV" mvs
    else
        python3 "$REPO/tests/check_sound.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" "$SOUND_WAV"
    fi
elif [[ "$MODE" == sound-game || "$MODE" == sound-radar ]]; then
    # the M7 Task 2 check: the game-log sends equal the model's predicted
    # commands (frame for frame), the sampled sends are loud in the WAV,
    # the dome deaths' 5 rumbles come 9 frames apart (sound-game), and the
    # radar leg's pips come every 20 frames from the lock's first frame.
    [[ -f "$SOUND_WAV" ]] || { echo "boot_test: FAIL — no sound WAV at $SOUND_WAV"; exit 1; }
    python3 "$REPO/tests/check_sound_game.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" "$SOUND_WAV" "$MODE"
elif [[ "$MODE" == flow || "$MODE" == flow-restart ]]; then
    python3 "$REPO/tests/check_flow.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$FLOW_FRAMECNT_ADDR" "${FLOW_RESTART_VAL:-0}"
elif [[ "$MODE" == flow-mvs || "$MODE" == flow-mvs-start || "$MODE" == flow-mvs-norestart ]]; then
    python3 "$REPO/tests/check_flow.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$FLOW_FRAMECNT_ADDR" "${FLOW_RESTART_VAL:-0}" "$MODE"
elif [[ "$MODE" == flow-pages || "$MODE" == flow-pages-c ]]; then
    FLOW_SNAP_DIR="$OUT/snap" python3 "$REPO/tests/check_flow.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$FLOW_FRAMECNT_ADDR" "0" "$MODE"
elif [[ "$MODE" == flow-level || "$MODE" == flow-return || "$MODE" == flow-return-best ]]; then
    # the M6 Task 7 legs: flow-level proves the B level select and the
    # Start's level; flow-return proves the fresh boot (page 0 / NORMAL),
    # the NORMAL game, and the HIGH SCORES return; flow-return-best (M6
    # Task 9) adds the backup-RAM high-score proof on the returned title.
    python3 "$REPO/tests/check_flow.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$FLOW_FRAMECNT_ADDR" "0" "$MODE"
elif [[ "$MODE" == best-mvs ]]; then
    # the M6 Task 9 best-mvs leg: the checker keys the nvram reuse/new
    # state on BEST_REUSE (2 = run 2, sharing; 3 = run 3, fresh; else run 1).
    if [[ "${BEST_REUSE:-0}" == "1" ]]; then
        BEST_LEG=2
    elif [[ "${BEST_FRESH:-0}" == "1" ]]; then
        BEST_LEG=3
    else
        BEST_LEG=1
    fi
    BEST_NVRAM_LEG="$BEST_LEG" python3 "$REPO/tests/check_flow.py" \
        "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$FLOW_FRAMECNT_ADDR" "0" "$MODE"
elif [[ "$MODE" == best-aes ]]; then
    # the M6 Task 10 best-aes leg: the checker keys the card reuse/new
    # state on BEST_REUSE (2 = run 2, sharing the card) and BEST_NOCARD
    # (3 = run 3, no card; else run 1).
    if [[ "${BEST_REUSE:-0}" == "1" ]]; then
        BEST_CARD_LEG=2
    elif [[ "${BEST_NOCARD:-0}" == "1" ]]; then
        BEST_CARD_LEG=3
    else
        BEST_CARD_LEG=1
    fi
    BEST_CARD_LEG="$BEST_CARD_LEG" python3 "$REPO/tests/check_flow.py" \
        "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$FLOW_FRAMECNT_ADDR" "0" "$MODE"
else
    python3 "$REPO/tests/check_snapshot.py" "${SNAP:-$OUT/snap.png}" "$MODE"
fi
