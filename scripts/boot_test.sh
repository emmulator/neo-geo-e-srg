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
# 295-frame return to the title still happens; flow-pages: the title's eleven
# pages turn every 295 frames with no Start, the dome on page 0 only, and
# every sampled frame's rows equal the title model; flow-pages-c: a C press
# turns the page (M6 Tasks 1, 2, 4, 6); flow-level: B taps cycle the level
# NORMAL->HARD->EASY->NORMAL->HARD on page 0 with title_t 0 and the game
# begins at the chosen level; flow-return: the GAME OVER return opens the
# played level's board page (NORMAL -> page 2) with the level kept, and a
# fresh boot shows page 0 and NORMAL (M6 Task 7); best-mvs: the MVS
# backup-RAM board (high-score
# boards Task B2) — four runs: 1 plays the aiming game, 2 proves the board
# persisted, 3 reuses it with the saved magic patched to the old 'ESRG'
# (the entry must reset to the defaults), 4 starts from a fresh nvram;
# best-aes: the AES memory-card board (Task B2) — four runs, runs 1 and 2
# sharing one -memcard file (run 2's fresh nvram proves the card kept the
# board), run 3 the old 'ESRG' card magic, run 4 no card at all.
# sound: the M7 Task 1 sound pipeline — the -DSOUND_TEST cart sends the
# six effects at recorded title frames (plus the frame-400 two-in-one
# send) and the checker proves from the -wavwrite recording that every
# send was acknowledged, each is silent before / loud after / right length,
# and the frame-400 pair plays the hit's 0.75 s with the pip over it.
# sound-mvs: Attract A4/D1 — the NORMAL cart (the demo compiled in) under
# `neogeo -bios euro`. The probe sets bios_game_dip[6] (the "DEMO SOUND"
# soft DIP) and taps REG_SOUND: at its header default OFF the entry cycle
# and a full 3245-frame cycle send none (and a 60-frame D hold on MVS does
# nothing, no row-21 confirmation); with it ON a full cycle's commands
# equal the model's; a real game started after it still sounds; and the
# ROM header's soft-DIP table decodes to E-SRG / DEMO SOUND / ON / OFF with
# OFF (selected 1) the default (the BIOS game-settings data).
# sound-game / sound-radar: the M7 Task 2 tests — the same cart now plays
# the deterministic "sound game" (sound_game_probe.lua drives it) and
# records every game sound send in the game log; the checker replays the
# model from the recorded inputs and proves the log equals its predicted
# commands frame for frame, the sampled sends are loud in the WAV, the
# collapse's 5 beats alternate HIT/CRACK 9 frames apart, and (sound-radar,
# no input) the lock-on pips come every 20 frames from the lock's first
# frame, none before.
# Env: FRAMES (900), BOOT_HOLD (input held from frame 120), MAME_BIOS_DIR, MAME,
# CRACK_CART (path to the crack-test cart), FRAME_MARK_CART (path to the
# frame-mark cart), MVS_BIOS_ZIP (source of the MVS BIOS set; default
# ~/ROMs/neogeo/neogeo.zip), MVS_COIN / MVS_START (the MVS input helper's
# holds; MVS_COIN=-100 disables the coin for the Task 2 failure demos);
# for best-aes: BEST_CARD_DIR (the memory-card file's directory, default
# $REPO/build/best-card), BEST_REUSE=1 (run 2: reuse run 1's card),
# BEST_OLD=1 (run 3: patch the saved magic to the old 'ESRG'),
# BEST_NOCARD=1 (run 4: no -memcard).
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
if [[ "$MODE" == tear ]]; then
    # Task 18: the props spin on the FRAME_MARK cart, whose work_start_mark
    # and work_commit_mark give the frame's start-to-commit-end. The cart is
    # the normal cart plus those two BSS marks.
    CART="${FRAME_MARK_CART:-$REPO/build/rom/esrg-framemark.zip}"
fi
if [[ "$MODE" == gameover-draw ]]; then
    CART="${GO_DRAW_CART:-$REPO/build/rom/esrg-godraw.zip}"
fi
if [[ "$MODE" == radar ]]; then
    CART="${RADAR_CART:-$REPO/build/rom/esrg-radartest.zip}"
fi
if [[ "$MODE" == sound ]]; then
    # the M7 Task 1 sound-pipeline test: the -DSOUND_TEST cart
    # (build/rom/esrg-soundtest.zip), which scripts five sound-command
    # sends on the title plus the two-in-one-frame pair, recording each
    # send in a RAM log. The probe needs the log's address (the static
    # sound_test_log / sound_test_n and the hook's title counter, found by
    # nm in the test ELF).
    CART="${SOUND_CART:-$REPO/build/rom/esrg-soundtest.zip}"
fi
if [[ "$MODE" == sound-mvs ]]; then
    # Attract A4: the demo-sound leg runs the NORMAL cart (the demo is
    # compiled in) under the MVS BIOS (`neogeo -bios euro -cart1 esrg`).
    # The probe taps REG_SOUND and sets bios_game_dip[6] itself, so it
    # needs the demo's epoch/frame exports from the normal ELF.
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
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
# Attract Task A3: the pre-A3 title-scene and calibrated gameplay legs use
# the static-title cart (demo compiled out) so their frames and seeds stay
# where they were calibrated; the demo/flow/Start legs keep the demo cart.
STATIC_MODES="dome dome-lift ship ship-top missile leftovers hud collapse ship-respawn ship-respawn-nodeath sky ground ripple mountains band console props"
PROBE_ELF="$REPO/build/rom.elf"
if [[ " $STATIC_MODES " == *" $MODE "* ]]; then
    CART="${STATIC_CART:-$REPO/build/rom/esrg-static.zip}"
    PROBE_ELF="$REPO/build/rom-static.elf"
fi
if [[ "$MODE" == tear ]]; then
    CART="${STATIC_FM_CART:-$REPO/build/rom/esrg-staticfm.zip}"
    PROBE_ELF="$REPO/build/rom-staticfm.elf"
fi
if [[ "$MODE" == entry-lives || "$MODE" == entry-ruin ]]; then
    # high-score boards Task B6: the entry-screen leg. `entry-lives` plays the
    # aiming game (Left held, A only when aligned) until the score qualifies,
    # then Up held to a lives-out GAME OVER over the whole dome; `entry-ruin`
    # scores the same way and then stops firing for the dome death that
    # collapses to the ruin. Both then wait out the 118
    # GAME OVER frames, drive the entry (held turns, erase, auto-jump, END),
    # and sample the returned title's blink. The probe needs the entry
    # machine, the flow state, the ship/mis/rules, the board, the card log,
    # the title state and the aim tables, found by nm.
    PROBE="entry_probe.lua"
    ENTRY_CASE_VAL="${MODE#entry-}"
    BOOT_FRAMES="${BOOT_FRAMES:-32000}"
    FLOW_STATE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow" { print "0x" $1 }')"
    ENTRY_STATE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "entry_state" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "entry_state" { print "0x" $1 }')"
    ENTRY_FC_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "entry_fc" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "entry_fc" { print "0x" $1 }')"
    FLOW_SHIP_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
    FLOW_MIS_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    FLOW_RULES_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }')"
    FLOW_BEST_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_board" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_board" { print "0x" $1 }')"
    FLOW_LEVEL_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }')"
    FLOW_CARDLOG_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "card_log" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "card_log" { print "0x" $1 }')"
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_CELL_RING_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_ring" && !seen++ { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_ring" && !seen++ { print "0x" $1 }')"
    FLOW_CELL_PHI_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_phi" && !seen++ { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_phi" && !seen++ { print "0x" $1 }')"
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
fi
if [[ "$MODE" == sky ]]; then
    # dome-scenery Task 4: the backdrop is the sky in play and black on the
    # title. The probe snapshots the title (fc 0) and a game frame (fc 30+);
    # tests/check_sky.py compares the top-left backdrop pixel of both.
    PROBE="sky_probe.lua"
    SKY_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    # the title snapshot lands at MAME ~frame 300 (fc 0), Start at 600, the
    # game frame at fc 30 around MAME 640: 900 frames is ample.
    BOOT_FRAMES="${BOOT_FRAMES:-900}"
fi
if [[ "$MODE" == flow-pages || "$MODE" == flow-pages-c ]]; then
    # M6 Task 6: the title pages run (AES no-Start) and the C-turn run
    # (MVS). Both boot the plain NORMAL cart and need the title state's
    # BSS addresses (title_page / title_t / flow_entry), found by nm.
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
fi
if [[ "$MODE" == demo || "$MODE" == demo-start ]]; then
    # Attract Task A3: the demo's frame budget is measured too, so both runs
    # use the FRAME_MARK cart (it carries the same code plus the work marks).
    CART="${FRAME_MARK_CART:-$REPO/build/rom/esrg-framemark.zip}"
fi
if [[ "$MODE" == flow-level || "$MODE" == flow-return || "$MODE" == flow-return-best ]]; then
    # M6 Task 7: the level-select run (AES: B taps at 1000..1300, Start at
    # 1400, the game plays at the chosen level) and the no-B return run
    # (fresh boot page 0 / NORMAL, the Up-held game to GAME OVER, and the
    # returned title on the played level's board page). flow-return-best (Task B2)
    # adds the backup-RAM board reads (flow_board) so the checker can prove
    # the returned title shows the board's top entries. All three boot the
    # plain NORMAL cart and need the flow_level backup-RAM byte, the static
    # rules and the static mis addresses, found by nm.
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
fi
if [[ "$MODE" == best-mvs ]]; then
    # high-score boards Task B2: the MVS backup-RAM board proof (four runs
    # sharing or not sharing one nvram, see below). Boots the plain NORMAL
    # cart under `neogeo -bios euro -cart1 esrg` and needs flow_board (the
    # backup-RAM board), flow_level's marker pair, the static mis (for
    # score10), ship/the ROM cell tables (the aim policy) and the title
    # state's addresses, found by nm.
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
fi
if [[ "$MODE" == best-aes ]]; then
    # high-score boards Task B2: the AES memory-card board proof (four
    # runs, one -memcard file shared by runs 1..3, none for run 4 — see
    # below). Boots the plain NORMAL cart under `aes -cart esrg` and needs
    # the flow_board backup-RAM board, the flow_level marker pair, the
    # static mis (for score10), ship/the ROM cell tables (the aim policy),
    # the card-log words (card_log, the answers the cart's card calls left)
    # and the title state's addresses, found by nm.
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
fi
if [[ "$MODE" == entry-lives || "$MODE" == entry-ruin ]]; then
    # high-score boards Task B6: the entry screen, on the plain NORMAL AES
    # cart (the aim game / the centred collapse game to GAME OVER).
    CART="${FLOW_CART:-$REPO/build/rom/esrg.zip}"
fi
# Plan P2 amendment 3: every Start is pressed on the cart's title_seed_t,
# not on a fixed MAME frame, so the game's missile seed stays HEAD's seed.
# Find title_seed_t's RAM address in the ELF of the cart this leg runs (the
# probes' PROBE_ELF is not always the cart's ELF: radar, gameover-draw,
# sound-game and sound-radar use their own test carts).
cart_elf() {
    case "$(basename "$CART")" in
        esrg-static.zip)     echo "$REPO/build/rom-static.elf" ;;
        esrg-staticfm.zip)   echo "$REPO/build/rom-staticfm.elf" ;;
        esrg-framemark.zip)  echo "$REPO/build/rom-framemark.elf" ;;
        esrg-crackfm.zip)    echo "$REPO/build/rom-crackframemark.elf" ;;
        esrg-cracks.zip)     echo "$REPO/build/rom-cracktest.elf" ;;
        esrg-godraw.zip)     echo "$REPO/build/rom-gameoverdraw.elf" ;;
        esrg-radartest.zip)  echo "$REPO/build/rom-radartest.elf" ;;
        esrg-soundtest.zip)  echo "$REPO/build/rom-soundtest.elf" ;;
        esrg-soundradar.zip) echo "$REPO/build/rom-soundradar.elf" ;;
        *)                   echo "$REPO/build/rom.elf" ;;
    esac
}
TITLE_SEED_ELF="$(cart_elf)"
TITLE_SEED_ADDR="$(m68k-neogeo-elf-nm "$TITLE_SEED_ELF" 2>/dev/null \
    | awk '$2 ~ /^[BbDd]$/ && $3 == "title_seed_t" { print "0x" $1 }' \
    || nm "$TITLE_SEED_ELF" 2>/dev/null \
    | awk '$2 ~ /^[BbDd]$/ && $3 == "title_seed_t" { print "0x" $1 }')" \
    || TITLE_SEED_ADDR=0
TITLE_SEED_ADDR="${TITLE_SEED_ADDR:-0}"
# BOOT_OUT: the leg's own output directory (scripts/boot_test_all.sh gives
# every leg its own, so legs can run in parallel); build/boot by default.
OUT="${BOOT_OUT:-$REPO/build/boot}"

# Task 1: the MAME legs whose checkers replay the cart's game need the seed
# the cart used (mis_seed_used) and, for the first-missile proofs, the static
# `mis` (obj[0]'s ring/phi). One helper, so the eight checkers share one nm
# lookup and one MIS_* env pair instead of eight copies.
mis_select() {
    local elf=""
    case "$1" in
        hud|collapse|ship-respawn|ship-respawn-nodeath|framemark|crackframemark)
            elf="$PROBE_ELF"
            [[ "$1" == framemark ]] && elf="$REPO/build/rom-framemark.elf"
            [[ "$1" == crackframemark ]] && elf="$REPO/build/rom-crackframemark.elf" ;;
        gameover-draw) elf="$REPO/build/rom-gameoverdraw.elf" ;;
        radar)         elf="$REPO/build/rom-radartest.elf" ;;
        sound-game)    elf="$REPO/build/rom-soundtest.elf" ;;
        sound-radar)   elf="$REPO/build/rom-soundradar.elf" ;;
        flow|flow-restart|flow-pages|flow-pages-c|flow-level|flow-return|flow-return-best|\
        flow-mvs|flow-mvs-start|flow-mvs-norestart|best-mvs|best-aes)
            elf="$PROBE_ELF" ;;
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

# Task S3: the leftovers leg's bullet proof reads the static mis (the two
# bullets' ring/phi/r), the ship (its dome angle), and hud_framecnt (the
# churn's frame counter). Their .bss addresses come from the selected cart's
# ELF, found by nm like the other legs' exports.
if [[ "$MODE" == leftovers ]]; then
    SHIP_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
    MIS_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    HUD_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
fi

[[ -f "$CART" ]] || { echo "boot_test: $CART missing (run make)" >&2; exit 2; }

FLATPAK_MAME=/var/lib/flatpak/app/org.mamedev.MAME/x86_64/stable/active/files/bin/mame
if [[ -n "${MAME:-}" ]]; then read -r -a MAME_CMD <<< "$MAME"
elif [[ -x "$FLATPAK_MAME" ]]; then MAME_CMD=("$FLATPAK_MAME")
elif command -v mame >/dev/null; then MAME_CMD=(mame)
else echo "boot_test: no MAME (set MAME=)" >&2; exit 2; fi

BIOS_DIR="${MAME_BIOS_DIR:-$HOME/Development/emulators/roms/mame-neogeo}"
[[ -f "$BIOS_DIR/aes.zip" ]] || { echo "boot_test: $BIOS_DIR/aes.zip missing" >&2; exit 2; }

PROBE="boot_probe.lua"
if [[ "$MODE" == entry-lives || "$MODE" == entry-ruin ]]; then
    PROBE="entry_probe.lua"
fi
if [[ "$MODE" == leftovers ]]; then PROBE="leftover_probe.lua"; fi
if [[ "$MODE" == cracks ]]; then PROBE="broken_probe.lua"; fi
if [[ "$MODE" == sound || "$MODE" == sound-mvs ]]; then PROBE="sound_probe.lua"; fi
if [[ "$MODE" == sound-game || "$MODE" == sound-radar ]]; then PROBE="sound_game_probe.lua"; fi
if [[ "$MODE" == collapse ]]; then PROBE="collapse_probe.lua"; fi
if [[ "$MODE" == framemark || "$MODE" == crackframemark ]]; then PROBE="frame_mark_probe.lua"; fi
if [[ "$MODE" == tear ]]; then PROBE="tear_probe.lua"; fi
if [[ "$MODE" == ship-respawn || "$MODE" == ship-respawn-nodeath ]]; then
    PROBE="ship_respawn_probe.lua"
    # the probe reads the cart's BSS debug exports (the cart frame counter
    # and the rules' alive flag) so it can time the death and respawn
    # exactly; find their addresses in the freshly built ELF
    SHIP_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    SHIP_RC_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules_dbg_alive" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
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
    # dome-scenery Task 12: the props follow the camera (ship.dome_angle,
    # the ship struct's first byte), which the crack cart keeps at 0 even
    # when CRACK_ANGLE forces a different overlay permutation. Its BSS
    # address lets the probe dump the real angle for the checker's composite.
    SHIP_ADDR="$(m68k-neogeo-elf-nm "$REPO/build/rom-cracktest.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$REPO/build/rom-cracktest.elf" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
fi
if [[ "$MODE" == hud ]]; then
    PROBE="hud_probe.lua"
    # the probe reads the cart's BSS debug exports (a redraw count and the
    # cart's frame counter, hud_dbg_events / hud_framecnt) so it can prove
    # the HUD redraws only on change and align its reads to cart frames, and
    # the static `rules` (for the after-death snapshot's lives byte);
    # find their addresses in the freshly built ELF
    HUD_EVENTS_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_dbg_events" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_dbg_events" { print "0x" $1 }')"
    HUD_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    HUD_RULES_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }')"
    # the probe script needs to run past game over and the A restart. Task 1
    # seeds the missiles from the title's time: at the default 600 Start
    # (seed 0xaede) game 1's first death is at fc 3687 (the after-death
    # snapshot fires there), GAME OVER at fc 17525, and the A press at GAME
    # OVER + 71 restarts at ~fc 17596. Game 2 then needs a few hundred frames
    # with fire to score (the checker's "the score never grew" leg), so
    # ~20,400 MAME frames (game start ~603 + 17596 + the game-2 margin).
    BOOT_FRAMES="${BOOT_FRAMES:-20400}"
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
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    RADAR_SHIP_ADDR="$(m68k-neogeo-elf-nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
    RADAR_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    RADAR_RADAR_ADDR="$(m68k-neogeo-elf-nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "radar" { print "0x" $1 }' \
        || nm "$RADAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "radar" { print "0x" $1 }')"
    BOOT_FRAMES="${BOOT_FRAMES:-2400}"
fi
if [[ "$MODE" == sound ]]; then
    # the M7 Task 1 sound test's RAM exports: the static sound_test_log
    # (u8[32]: tf_lo, tf_hi, cmd, result quadrupels) and sound_test_n (the
    # next free slot) and the hook's own u16 title counter sound_test_fc —
    # all from the -DSOUND_TEST ELF (build/rom-soundtest.elf), found by nm.
    # The run needs to reach title frame 400 (the last send: the
    # two-in-one frame), so ~1100 MAME frames: the ~477-frame AES BIOS
    # preamble + 400 title frames + margin.
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
    BOOT_FRAMES="${BOOT_FRAMES:-1100}"
fi
if [[ "$MODE" == sound-mvs ]]; then
    # Attract A4/D1: the demo-sound leg. The normal cart's demo epoch/frame
    # exports let the probe window the header default OFF (the entry's 3242
    # frames and the full epoch-2 3245-frame cycle), the full epoch-3
    # 3245-frame cycle with the DIP set ON, and the real game after it. The
    # MVS BIOS clears RAM by ~frame 280 and the cart's title starts at
    # ~302; the run also holds D for 60 frames during the default epoch:
    # ~13,000 MAME frames (entry 3242 + two 3245-frame cycles = 9732, then
    # the coin/Start and the real game's first 90 frames).
    DEMO_ELF="$REPO/build/rom.elf"
    DEMO_EPOCH_ADDR="$(m68k-neogeo-elf-nm "$DEMO_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "demo_dbg_epoch" { print "0x" $1 }' \
        || nm "$DEMO_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "demo_dbg_epoch" { print "0x" $1 }')"
    DEMO_FC_ADDR="$(m68k-neogeo-elf-nm "$DEMO_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "demo_dbg_fc" { print "0x" $1 }' \
        || nm "$DEMO_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "demo_dbg_fc" { print "0x" $1 }')"
    SOUND_DEMO_VAL=1
    BOOT_FRAMES="${BOOT_FRAMES:-13000}"
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
    COLLAPSE_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
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
if [[ "$MODE" == tear ]]; then
    # Task 18: the props leg's spin on the FRAME_MARK cart. Task 18b adds a
    # second drive: the collapse leg's centred policy (stick centred, A every
    # 11 cart frames, 3000 MAME frames: missiles land, the radar locks and
    # blinks, explosions play). TEAR_DRIVE picks one; the probe reads the
    # cart frame counter and the static `ship` (dome_angle), plus the frame's
    # work-start and the last commit's end (both BSS marks).
    PROBE="tear_probe.lua"
    TEAR_DRIVE="${TEAR_DRIVE:-spin}"
    if [[ "$TEAR_DRIVE" == fire ]]; then
        BOOT_FRAMES="${BOOT_FRAMES:-3000}"
    elif [[ "$TEAR_DRIVE" == title ]]; then
        # Attract A2: 600 logged title frames (probe logs MAME 41..640)
        BOOT_FRAMES="${BOOT_FRAMES:-640}"
    else
        BOOT_FRAMES="${BOOT_FRAMES:-1600}"
    fi
    TEAR_ELF="$PROBE_ELF"
    PROPS_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$TEAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$TEAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    PROPS_SHIP_ADDR="$(m68k-neogeo-elf-nm "$TEAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$TEAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
    START_ADDR="$(m68k-neogeo-elf-nm "$TEAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_start_mark" { print "0x" $1 }' \
        || nm "$TEAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_start_mark" { print "0x" $1 }')"
    COMMIT_ADDR="$(m68k-neogeo-elf-nm "$TEAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_commit_mark" { print "0x" $1 }' \
        || nm "$TEAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "work_commit_mark" { print "0x" $1 }')"
    # Task 18b's fire drive forces the first missile to the ship's start cell,
    # as the RADAR_TEST cart's hook does: the normal cart's centred policy
    # never targets cell 27 (outside the spawn rings), so without this the
    # drive would play no lock/blink and no explosion within 3000 frames.
    # The static `mis` and the missile tables' const arrays (all in ROM).
    MIS_ADDR="$(m68k-neogeo-elf-nm "$TEAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$TEAR_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    MIS_R_SPAWN_ADDR="$(m68k-neogeo-elf-nm "$TEAR_ELF" 2>/dev/null \
        | awk '$3 == "mis_r_spawn" && !n++ { print "0x" $1 }' \
        || nm "$TEAR_ELF" 2>/dev/null \
        | awk '$3 == "mis_r_spawn" && !n++ { print "0x" $1 }')"
    MIS_CELL_RING_ADDR="$(m68k-neogeo-elf-nm "$TEAR_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_ring" && !n++ { print "0x" $1 }' \
        || nm "$TEAR_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_ring" && !n++ { print "0x" $1 }')"
    MIS_CELL_PHI_ADDR="$(m68k-neogeo-elf-nm "$TEAR_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_phi" && !n++ { print "0x" $1 }' \
        || nm "$TEAR_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_phi" && !n++ { print "0x" $1 }')"
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
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
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
    # expires, and the returned title opens on page 2 (the played NORMAL
    # level's board page) — ~18,400 MAME frames (the game begins at ~MAME
    # 603). flow-return-best (high-score boards Task B2/B3) is the same
    # return run with the board's reads enabled.
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
    FLOW_LEVEL_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }')"
    FLOW_RULES_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }')"
    FLOW_MIS_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    # high-score boards Task B2: the backup-RAM board (flow_board) for the
    # flow-return-best leg (and the best-mvs mode, which sets its own)
    FLOW_BEST_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_board" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_board" { print "0x" $1 }')"
    # the title state's addresses (page/t/entry) for the returned-title and
    # page-0 checks
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_ENTRY_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }')"
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
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
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    # M6 Task 6: the MVS title rows' page-0 gate (the checker reads the
    # page the rows were drawn on from the T records)
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_ENTRY_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
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
        FLOW_RULES_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
            | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }' \
            || nm "$PROBE_ELF" 2>/dev/null \
            | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }')"
        # the start leg + the Up-held game to the model's GAME OVER (fc
        # 16551 under Task 1's seed 0xadf9; 6509 with RNG_SEED) + the
        # 295-frame window + the ~200-frame BIOS rebuild + margin:
        # ~1802 + 16551 + 500 = ~18,850 MAME frames
        BOOT_FRAMES="${BOOT_FRAMES:-19200}"
    fi
fi

if [[ "$MODE" == best-mvs ]]; then
    # high-score boards Task B2: the MVS backup-RAM board proof. Four runs
    # of `neogeo -bios euro -cart1 esrg`. Run 1 (best-mvs default) plays
    # the aiming game (Left held, A only when a missile is aligned) to GAME
    # OVER (coin at 1500, Start at 1800; the game begins at ~frame 1802),
    # reads mis.score10 at GAME OVER (> 1000, i.e. above the default 5th
    # entry), waits for the high-scores return, and checks flow_board in
    # RAM is valid and holds the entry (three spaces) and the defaults.
    # Run 2 (BEST_REUSE=1) reuses run 1's nvram and proves the board,
    # including the game's entry, persisted before any game. Run 3
    # (BEST_REUSE=1 BEST_OLD=1) reuses run 2's nvram after boot_test.sh
    # overwrites the saved board's magic with the old 'ESRG' one; the entry
    # must reject it and start from the defaults. Run 4 (BEST_FRESH=1)
    # uses a FRESH nvram and proves the defaults (no garbage, no crash).
    # boot_test.sh is called once per run with BEST_RUN / BEST_NVRAM_DIR
    # set by the Makefile's target.
    PROBE="flow_probe.lua"
    FLOW_BEST_VAL=1
    FLOW_MVS_VAL=1
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_ENTRY_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }')"
    FLOW_LEVEL_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }')"
    FLOW_MIS_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    FLOW_BEST_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_board" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_board" { print "0x" $1 }')"
    FLOW_RULES_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }')"
    FLOW_SHIP_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
    FLOW_CELL_RING_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_ring" && !seen++ { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_ring" && !seen++ { print "0x" $1 }')"
    FLOW_CELL_PHI_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_phi" && !seen++ { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_phi" && !seen++ { print "0x" $1 }')"
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    FLOW_STATE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow" { print "0x" $1 }')"
    ENTRY_STATE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "entry_state" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "entry_state" { print "0x" $1 }')"
    FLOW_BLINK_ACTIVE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_blink_active" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_blink_active" { print "0x" $1 }')"
    FLOW_ENTRY_FINISH_VAL=1
    # the run kind: run 1 (default) plays the aiming game (the game
    # begins at MAME ~1802 with the coin at 1500 and Start at 1800; the
    # measured GAME OVER is fc ~25978 under Task 1's seed 0xadf9) plus the
    # 295-frame window and the ~200-frame BIOS rebuild: 30000 MAME frames,
    # with margin. Runs 2 and 3 (reuse) and run 4 (fresh) only sit on the
    # title: the first page-0 frame's row 9 is the proof; a reused run
    # opens on page 2 (run 1 returned on NORMAL's board page) and its first
    # page-0 frame comes after the 10 -> 0 turns (~9 x 295 title frames after
    # the page-2 entry, ~MAME 2700), so 3300 frames cover all three.
    if [[ "${BEST_REUSE:-0}" == "1" || "${BEST_FRESH:-0}" == "1" ]]; then
        BOOT_FRAMES="${BOOT_FRAMES:-3300}"
        MVS_START_VAL="-100"
    else
        BOOT_FRAMES="${BOOT_FRAMES:-30000}"
        MVS_START_VAL="${MVS_START:-1800}"
    fi
fi

if [[ "$MODE" == best-aes ]]; then
    # high-score boards Task B2: the AES memory-card board proof. Four runs
    # of `aes -cart esrg`. Run 1 (default) starts from a FRESH card file
    # (rm'd below) and a FRESH nvram/cfg: the first entry LOADs the
    # (unformatted) card — answer 0x81 — then the aiming game runs to GAME
    # OVER with score10 above the default 5th entry, board_insert changes
    # the board, and the SAVE answers 0x81, FORMAT answers 0, SAVE answers
    # 0 (the card_log records, read from RAM); the returned title opens on
    # page 2 (NORMAL's board page) whose row 11 shows the board's top entry.
    # Run 2
    # (BEST_REUSE=1) reuses run 1's card file with a FRESH nvram/cfg (a
    # power-off: backup RAM empty): the entry LOADs the card (answer 0) and
    # the board, including the game's entry, is back before any game. Run
    # 3 (BEST_REUSE=1 BEST_OLD=1) reuses the card after boot_test.sh
    # overwrites the saved board's magic with the old 'ESRG' one; the load
    # answers 0 but board_valid rejects it, so the entry starts from the
    # defaults. Run 4 (BEST_NOCARD=1) passes no -memcard: the load answers
    # 0x80, the first page-0 frame shows the default board's NORMAL top,
    # no crash, and a game to GAME OVER still keeps the board in backup RAM
    # for the run.
    PROBE="flow_probe.lua"
    FLOW_BEST_VAL=1
    FLOW_BEST_AES_VAL=1
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_ENTRY_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }')"
    FLOW_LEVEL_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_level_valid" { print "0x" $1 }')"
    FLOW_MIS_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "mis" { print "0x" $1 }')"
    FLOW_BEST_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_board" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[Bb]$/ && $3 == "flow_board" { print "0x" $1 }')"
    FLOW_RULES_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "rules" { print "0x" $1 }')"
    FLOW_SHIP_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
    FLOW_CELL_RING_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_ring" && !seen++ { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_ring" && !seen++ { print "0x" $1 }')"
    FLOW_CELL_PHI_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_phi" && !seen++ { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_phi" && !seen++ { print "0x" $1 }')"
    FLOW_CARDLOG_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "card_log" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "card_log" { print "0x" $1 }')"
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    FLOW_STATE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow" { print "0x" $1 }')"
    ENTRY_STATE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "entry_state" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "entry_state" { print "0x" $1 }')"
    FLOW_BLINK_ACTIVE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_blink_active" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_blink_active" { print "0x" $1 }')"
    FLOW_ENTRY_FINISH_VAL=1
    # the run kind: runs 2 and 3 (BEST_REUSE=1) only sit on the title (no
    # Start) and need just the first page-0 frame (~MAME 500): 1500 frames.
    # Run 1 and run 4 (no card) play the aiming game (Left held, A only when
    # a missile is aligned) to the measured GAME OVER (fc ~28348 under
    # Task 1's seed 0xaede from the ~frame 603 Start, so ~MAME 28950) plus
    # the 295-frame window and the ~200-frame BIOS rebuild: 31000 MAME
    # frames, with margin.
    if [[ "${BEST_REUSE:-0}" == "1" ]]; then
        BOOT_FRAMES="${BOOT_FRAMES:-1500}"
        SG_ENABLE_VAL=0          # runs 2/3 play no game: the first page-0
                                 # frame is the proof, before any Start
    else
        BOOT_FRAMES="${BOOT_FRAMES:-31000}"
    fi
fi

if [[ "$MODE" == sky ]]; then
    # dome-scenery Task 4: the backdrop is the sky in play and black on the
    # title. The probe snapshots the title (fc 0) and a game frame (fc 30+);
    # tests/check_sky.py compares the top-left backdrop pixel of both.
    PROBE="sky_probe.lua"
    SKY_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    # the title snapshot lands at MAME ~frame 300 (fc 0), Start at 600, the
    # game frame at fc 30 around MAME 640: 900 frames is ample.
    BOOT_FRAMES="${BOOT_FRAMES:-900}"
fi
if [[ "$MODE" == mountains ]]; then
    # dome-scenery Task 6: the mountains. The probe presses Start, walks the
    # ship up to the peak and spins the dome left through the panorama (and
    # back right to 230), reading the driver's SCB3/SCB4 and all 21 chain
    # columns' SCB1 words at dome angles 0, 1, 160, 161, 239 and 230, and
    # snapshotting the title (fc 0) and a wrapping frame with a scroll phase
    # (da 161). tests/check_mountains.py compares every read with the model
    # and the WINDOW snapshot's band with the generated picture.
    PROBE="mountains_probe.lua"
    MTN_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    MTN_SHIP_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
    # the ~24-frame AES preamble, the game start at 603, the climb to the
    # peak (~3 moves of 19 + a jump?) and a full left+right spin (50 steps/s:
    # ~240 left frames + ~10 right) — 1600 MAME frames is ample.
    BOOT_FRAMES="${BOOT_FRAMES:-1600}"
fi
if [[ "$MODE" == band ]]; then
    # dome-scenery Task 17: the towns-and-forests band. The probe presses
    # Start, walks the ship up to the peak and spins the dome left through
    # the panorama (and back right to 230), reading the driver's SCB3/SCB4
    # and all 21 chain columns' SCB1 words at dome angles 0, 1, 60, 140, 141,
    # 232, 239 and 230, snapshotting the title (fc 0) and a wrapping frame
    # with a scroll phase where a back prop reaches into the band (da 232),
    # and counting the sprites on every scanline over the run.
    # tests/check_band.py compares every read with the model and the WINDOW
    # snapshot's band with the band and mountain pictures.
    PROBE="band_probe.lua"
    BAND_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    BAND_SHIP_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
    # the ~24-frame AES preamble, the game start at 603, the climb to the
    # peak and a full left+right spin (~240 left + ~10 right frames) — 1600
    # MAME frames is ample.
    BOOT_FRAMES="${BOOT_FRAMES:-1600}"
fi
if [[ "$MODE" == console ]]; then
    # dome-scenery Task 7: the console. The probe plays the centred game and
    # snapshots the title (fc 0) and an early whole-dome play frame (fc 30,
    # before the first missile at fc 59); it dumps all 20 columns' SCB1/SCB2/
    # SCB3/SCB4, every slot's SCB3/SCB4 and the fix rows, and counts the
    # sprites on every scanline over the whole game. tests/check_console.py
    # compares the columns with build/console_map.h, the panel's clean pixels
    # with the generator's picture, the title's hide, and the worst line.
    PROBE="console_probe.lua"
    CON_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    # the game starts at MAME ~603; the census runs over the WHOLE centred
    # game (GAME OVER at fc 27142, the collapse leg's model), so the stated
    # worst is the game's worst: ~28100 MAME frames (like the ground leg).
    BOOT_FRAMES="${BOOT_FRAMES:-28100}"
fi
if [[ "$MODE" == props ]]; then
    # dome-scenery Task 12/13: the trees and rocks. The probe walks the ship
    # up to the peak, spins the dome left through the whole turn (0..239) and
    # back right to 0, then plays the centred game, snapshotting the title
    # (fc 0) and an early whole-dome play frame (fc 30, before the first
    # missile at fc 59). It reads ship.dome_angle there, dumps all
    # PROP_SLOTS (51) prop slots' SCB1/SCB2/SCB3/SCB4 and each shown prop's
    # bank, every slot's SCB3/SCB4 and the higher slots' tile rows and the
    # fix rows for the pixel proof, counts the sprites on every scanline over
    # the whole run, and on every frame whose dome angle changed dumps every
    # prop slot's SCB1 rows 0..4, SCB2/SCB3/SCB4 and each shown prop's bank
    # entries 1/13. tests/check_props.py compares the angle frames and the
    # PLAY slots/banks with tests/props_model.py, the clean prop pixels with
    # the model's palette, the title's hide, and the worst line. The whole
    # turn lands in the first ~630 game frames, so the 28100-frame run (the
    # whole run's census) stays as it is.
    PROBE="props_probe.lua"
    PROPS_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    PROPS_SHIP_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
    # the game starts at MAME ~603; the census runs over the WHOLE centred
    # game (GAME OVER at fc 27142, the collapse leg's model), so the stated
    # worst is the game's worst: ~28100 MAME frames (like the ground leg).
    BOOT_FRAMES="${BOOT_FRAMES:-28100}"
fi
if [[ "$MODE" == ground ]]; then
    # dome-scenery Task 5: the grass. The probe plays the centred full game
    # (the collapse leg's policy: the first dome death at fc 8359, the
    # collapse's gone frames after it, GAME OVER at fc 27142 under the
    # default Start's seed) and snapshots the title (fc 0), an early
    # whole-dome frame (fc 30, before the first missile) and the first
    # all-dome-hidden frame after a whole dome. tests/check_ground.py
    # compares the clean band and the shadow pixels with the generated art
    # and states the worst sprites-per-scanline count.
    PROBE="ground_probe.lua"
    GROUND_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    # the game starts at MAME ~603; the first dome death is at fc 8359 and
    # its collapse's gone frames follow. The census runs over the WHOLE
    # centred game (GAME OVER at fc 27142 — the collapse leg's model), so
    # the stated worst is the game's worst: ~28100 MAME frames (like the
    # collapse leg).
    BOOT_FRAMES="${BOOT_FRAMES:-28100}"
fi
if [[ "$MODE" == ripple ]]; then
    # dome-scenery Task 19: the grass ripples by palette rotation. The probe
    # plays the props leg's spin (climb to the peak, turn the dome left
    # through the whole turn and back right to 0) then the centred game
    # (A every 11 frames) until the first dome death's collapse: the props
    # leg's first split is at cart fc 9120 and the collapse's gone frames at
    # ~9179, so 10000 MAME frames (the game starts at ~603) cover the turn,
    # the gone state and the respawn. tests/check_ripple.py compares every
    # play frame's ripple banks with build/ground_map.h at the previous
    # frame's angle, every palette write's raster line, the ground SCB1
    # words, and three snapshots' uncovered ground pixels with the C ROM.
    PROBE="ripple_probe.lua"
    PROPS_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    PROPS_SHIP_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "ship" { print "0x" $1 }')"
    BOOT_FRAMES="${BOOT_FRAMES:-10000}"
fi
if [[ "$MODE" == flow-pages || "$MODE" == flow-pages-c ]]; then
    # the M6 Task 6 legs. flow-pages (AES, no Start at all, 3400 frames):
    # the title starts at ~frame 24 (no BIOS logo since the M8 fixes),
    # so the 10 -> 0 wrap (11 x 295 title frames) lands at ~3269 inside the
    # run — the checker proves the page turned every 295 frames, that every
    # sampled title frame's fix rows equal tests/title_model.py (the
    # page/level/t/credits and board read from RAM in the same frame via the
    # T/B records), and the dome's SCB words / snapshots at the page PINs
    # prove the dome is chained on page 0, on pages 1..10 (the three boards
    # included), and rebuilt word-equal after the wrap. flow-pages-c (MVS,
    # no coin/Start): the
    # title starts at ~frame 299, so page 0 spans ~299..592; a C tap on MAME
    # frames 450 and 550 turns 0 -> 1 -> 2 (within 2 frames), with title_t
    # reset to 0 — and the dome dumps at pages 0/1/2 prove the scene's
    # chain on the C-turned board pages. Drives the C taps through the
    # :edge:joy:JOY1 port (the AES
    # :ctrl1: fields do not exist on the MVS machine).
    PROBE="flow_probe.lua"
    FLOW_PAGES_VAL=0
    FLOW_PAGES_C_VAL=0
    FLOW_PAGE_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_page" { print "0x" $1 }')"
    FLOW_T_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "title_t" { print "0x" $1 }')"
    FLOW_ENTRY_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "flow_entry" { print "0x" $1 }')"
    FLOW_FRAMECNT_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$2 ~ /^[BbDd]$/ && $3 == "hud_framecnt" { print "0x" $1 }')"
    if [[ "$MODE" == flow-pages ]]; then
        FLOW_PAGES_VAL=1
        # the run must reach the 10 -> 0 wrap at ~24 + 11 x 295 = 3269 plus
        # margin (the no-logo title starts at MAME ~24)
        BOOT_FRAMES="${BOOT_FRAMES:-3400}"
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

if [[ "$MODE" == spider ]]; then
    # Task S2: the stopper-spider's frame choice. The normal cart (the demo
    # is compiled in) runs one full demo cycle on the title, then the probe
    # starts a scripted game (walk -> jump, a shot on the landing frame, a
    # second shot restarting the heave, a forced missile death and the
    # respawn). The probe reads the ship/rules/mis/demo state and the ship
    # slots' SCB1/SCB3 from RAM and VRAM, so every address comes from the
    # freshly built ELF (nm). ~6487 demo frames to epoch 3 + the Start +
    # ~200 game frames: 7600 MAME frames is ample.
    PROBE="spider_probe.lua"
    spider_sym() {
        m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
            | awk -v n="$1" '$2 ~ /^[BbDd]$/ && $3 == n { print "0x" $1 }'
    }
    SPIDER_SHIP_ADDR="$(spider_sym ship)"
    SPIDER_RULES_ADDR="$(spider_sym rules)"
    SPIDER_MIS_ADDR="$(spider_sym mis)"
    SPIDER_FRAMECNT_ADDR="$(spider_sym hud_framecnt)"
    SPIDER_DEMO_EPOCH_ADDR="$(spider_sym demo_dbg_epoch)"
    SPIDER_DEMO_FC_ADDR="$(spider_sym demo_dbg_fc)"
    SPIDER_DEMO_HASH_ADDR="$(spider_sym demo_dbg_hash)"
    SPIDER_MIS_CELL_RING_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_ring" && !n++ { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_ring" && !n++ { print "0x" $1 }')"
    SPIDER_MIS_CELL_PHI_ADDR="$(m68k-neogeo-elf-nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_phi" && !n++ { print "0x" $1 }' \
        || nm "$PROBE_ELF" 2>/dev/null \
        | awk '$3 == "mis_cell_phi" && !n++ { print "0x" $1 }')"
    BOOT_FRAMES="${BOOT_FRAMES:-7600}"
fi

if [[ "$MODE" == demo || "$MODE" == demo-start ]]; then
    # Attract Task A3: the demo's state and frame budget. The FRAME_MARK
    # cart carries the same code plus the work marks; the probe reads the
    # cart's BSS exports from the framemark ELF (nm), like the other legs.
    PROBE="demo_probe.lua"
    DEMO_ELF="$REPO/build/rom-framemark.elf"
    demo_sym() {
        m68k-neogeo-elf-nm "$DEMO_ELF" 2>/dev/null \
            | awk -v n="$1" '$2 ~ /^[BbDd]$/ && $3 == n { print "0x" $1 }'
    }
    DEMO_EPOCH_ADDR="$(demo_sym demo_dbg_epoch)"
    DEMO_FC_ADDR="$(demo_sym demo_dbg_fc)"
    DEMO_HASH_EPOCH_ADDR="$(demo_sym demo_dbg_hash_epoch)"
    DEMO_HASH_FC_ADDR="$(demo_sym demo_dbg_hash_fc)"
    DEMO_HASH_DONE_ADDR="$(demo_sym demo_dbg_hash_done)"
    DEMO_HASH_ADDR="$(demo_sym demo_dbg_hash)"
    DEMO_FRAMECNT_ADDR="$(demo_sym hud_framecnt)"
    DEMO_RULES_ADDR="$(demo_sym rules)"
    DEMO_SHIP_ADDR="$(demo_sym ship)"
    DEMO_MIS_ADDR="$(demo_sym mis)"
    DEMO_RADAR_ADDR="$(demo_sym radar)"
    DEMO_TITLE_SEED_ADDR="$(demo_sym title_seed_t)"
    DEMO_BEST_ADDR="$(demo_sym flow_board)"
    MIS_SEED_ADDR="$(demo_sym mis_seed_used)"
    DEMO_PAGE_ADDR="$(demo_sym title_page)"
    DEMO_T_ADDR="$(demo_sym title_t)"
    DEMO_LEVEL_ADDR="$(demo_sym flow_level_valid)"
    DEMO_AES_ON_ADDR="$(demo_sym softdip_dbg_aes_on)"
    DEMO_TOGGLES_ADDR="$(demo_sym softdip_dbg_toggles)"
    PROPS_ANGLE_ADDR="$(demo_sym props_dbg_last_angle)"
    WORK_START_ADDR="$(demo_sym work_start_mark)"
    WORK_END_ADDR="$(demo_sym work_end_mark)"
    WORK_MAX_ADDR="$(demo_sym work_max_mark)"
    WORK_MIN_ADDR="$(demo_sym work_min_mark)"
    if [[ "$MODE" == demo-start ]]; then
        DEMO_MODE_VAL=start
        # Attract D1: the press lands just after build/demo.json's first
        # crack jump (2092), so the probe starts at demo frame 2093. The
        # no-input game to GAME OVER is at most 23,113 frames for the
        # title_seed_t range around the new press (the host models), then
        # the 295-frame window, the BIOS rebuild and 100 returned demo
        # frames: 27,002 MAME frames (Task P2's two-frame title-entry wait
        # shifts every cart frame by two).
        DEMO_START_DFC="$(python3 - "$REPO/build/demo.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))["crack_jumps"][0][0] + 1)
PY
)"
        BOOT_FRAMES="${BOOT_FRAMES:-27002}"
    else
        DEMO_MODE_VAL=cycle
        # entry page 0 (3242 demo frames) + two full 3245-frame cycles + the
        # epoch-4 D hold/B restart and 100 of epoch 5's frames: 11000 covers
        # the 10332-title-frame run plus Task P2's two-frame title-entry
        # wait and margin. The run also presses D at epoch 2, on page 1 of
        # epoch 3, and holds it 60 frames at epoch 4 (Attract D1).
        # The C page-through from epoch 5's frame 120 (about 45 frames) and
        # 100 frames of epoch 6 add 300 frames.
        BOOT_FRAMES="${BOOT_FRAMES:-11300}"
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

# the best-mvs nvram handling: all four runs use BEST_NVRAM_DIR as the
# nvram directory (the state lives outside $OUT, which is rm -rf'd at the
# top of every run). Run 1 (BEST_REUSE=0) and run 4 (BEST_FRESH=1) start
# from a FRESH directory; run 2 (BEST_REUSE=1) reuses run 1's — the whole
# point of the proof: the BIOS persisted the _backup_ram block there when
# it entered attract mode after the game, and run 2's entry must load it
# back and show it on the title before any game. Run 3 reuses it again
# after the saved magic is patched to the old 'ESRG'.
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

# the best-aes memory-card handling (high-score boards Task B2): the card
# file lives outside $OUT (rm -rf'd every run) in BEST_CARD_DIR. Runs 1..3
# use one file: run 1 starts from a FRESH one the way the task wants ("the
# file must not exist"), run 2 reuses it — a power-off, whose proof is that
# the card, not the per-boot backup RAM, kept the board; run 3 reuses it
# after the saved magic is patched to the old 'ESRG'. Run 4
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

if [[ "$MODE" == entry-lives || "$MODE" == entry-ruin ]]; then
    # high-score boards Task B6: a fresh AES memory card for each backdrop's
    # run, so the END save's answers are the fresh-card 0x81 / FORMAT / 0
    # sequence the checker proves.
    ENTRY_CARD_DIR="${ENTRY_CARD_DIR:-$REPO/build/entry-card-$MODE}"
    mkdir -p "$ENTRY_CARD_DIR"
    CARD_FILE="$ENTRY_CARD_DIR/card.neo"
    rm -f "$CARD_FILE"
    CARD_ARG="-memcard $CARD_FILE"
fi

# high-score boards Task B2: the old-'ESRG' leg. Run 3 of best-mvs reuses
# run 1/2's nvram and run 3 of best-aes reuses run 1/2's card; before MAME
# starts, the saved board's magic 'ESR2' is overwritten with the old
# best_t's 'ESRG' magic. The cart's board_valid must reject it and the
# entry must start from the default board. The MVS saveram stores the
# backup words swapped (MAME's file is little-endian), so both byte orders
# are tried; the card image may store either.
if [[ "${BEST_OLD:-0}" == "1" ]]; then
    if [[ "$MODE" == best-mvs ]]; then
        OLD_FILE="$NVRAM_D/neogeo/saveram"
    else
        OLD_FILE="$CARD_FILE"
    fi
    [[ -f "$OLD_FILE" ]] || { echo "boot_test: BEST_OLD needs $OLD_FILE" >&2; exit 2; }
    python3 - "$OLD_FILE" <<'PYEOF'
import sys
path = sys.argv[1]
data = bytearray(open(path, "rb").read())
pairs = [
    (bytes.fromhex("53 45 32 52"), bytes.fromhex("53 45 47 52")),  # words
    (bytes.fromhex("45 53 52 32"), bytes.fromhex("45 53 52 47")),  # bytes
]
for old, new in pairs:
    i = data.find(old)
    if i >= 0:
        data[i:i + len(old)] = new
        open(path, "wb").write(data)
        print(f"boot_test: old 'ESRG' board magic patched at {i} in {path}")
        break
else:
    sys.exit(f"boot_test: no 'ESR2' board magic in {path}")
PYEOF
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

# Plan P2 amendment 3: the Start is pressed on the cart's title frame count.
# On AES the title's first title_frame starts at MAME 25, so HEAD's title
# count at a MAME frame is that frame - 25 (the confirmed 600 -> 575, and the
# flow legs' 1200 -> 1175 and 1400 -> 1375). The hold is the same number of
# frames as the old SG_BEGIN..SG_END window.
SG_BEGIN="${SG_BEGIN:-600}"
SG_END="${SG_END:-604}"
SG_TITLE_BEGIN=$((SG_BEGIN - 25))
SG_TITLE_END=$((SG_TITLE_BEGIN + SG_END - SG_BEGIN))
# On MVS the coin at 1500 makes the BIOS enter the cart title afresh; HEAD's
# title count at the calibrated 1800 Start is 280 (mis_seed_from(280) =
# 0xadf9). The same 5-frame hold as MVS_START..+4.
if [[ "${MVS_START_VAL:--100}" == "1800" ]]; then
    MVS_TITLE_START=280
else
    MVS_TITLE_START=-1
fi
MVS_TITLE_END=$((MVS_TITLE_START + 4))

FRAMES="${FRAMES:-${BOOT_FRAMES:-900}}" HOLD="${BOOT_HOLD:-}" OUT="$OUT/probe.txt" \
    REPO="$REPO" \
    HUD_EVENTS_ADDR="${HUD_EVENTS_ADDR:-0}" HUD_FRAMECNT_ADDR="${HUD_FRAMECNT_ADDR:-0}" \
    COLLAPSE_FRAMECNT_ADDR="${COLLAPSE_FRAMECNT_ADDR:-0}" \
    SHIP_FRAMECNT_ADDR="${SHIP_FRAMECNT_ADDR:-0}" SHIP_RC_ADDR="${SHIP_RC_ADDR:-0}" \
    SHIP_NODEATH="${NODEATH_VAL:-0}" \
    HUD_RULES_ADDR="${HUD_RULES_ADDR:-0}" \
    GO_TEST_ADDR="${GO_TEST_ADDR:-0}" GO_FRESH_ADDR="${GO_FRESH_ADDR:-0}" \
    END_ADDR="${END_ADDR:-0}" MAX_ADDR="${MAX_ADDR:-0}" MIN_ADDR="${MIN_ADDR:-0}" \
    START_ADDR="${START_ADDR:-0}" COMMIT_ADDR="${COMMIT_ADDR:-0}" \
    CRACK_ANGLE="${CRACK_ANGLE:-0}" CRACK_ANGLE_ADDR="${CRACK_ANGLE_ADDR:-0}" \
    SHIP_ADDR="${SHIP_ADDR:-0}" \
    CRACK_RULES_ADDR="${CRACK_RULES_ADDR:-0}" \
    RADAR_MIS_ADDR="${RADAR_MIS_ADDR:-0}" RADAR_SHIP_ADDR="${RADAR_SHIP_ADDR:-0}" \
    RADAR_FRAMECNT_ADDR="${RADAR_FRAMECNT_ADDR:-0}" \
    RADAR_RADAR_ADDR="${RADAR_RADAR_ADDR:-0}" \
    SG_BEGIN="${SG_BEGIN:-600}" SG_END="${SG_END:-604}" SG_ENABLE="${SG_ENABLE_VAL:-${SG_ENABLE:-1}}" \
    TITLE_SEED_ADDR="${TITLE_SEED_ADDR:-0}" \
    SG_TITLE_BEGIN="${SG_TITLE_BEGIN}" SG_TITLE_END="${SG_TITLE_END}" \
    MVS_TITLE_START="${MVS_TITLE_START}" MVS_TITLE_END="${MVS_TITLE_END}" \
    FLOW_RESTART="${FLOW_RESTART_VAL:-0}" FLOW_FRAMECNT_ADDR="${FLOW_FRAMECNT_ADDR:-0}" \
    FLOW_MVS="${FLOW_MVS_VAL:-0}" MVS_COIN="${MVS_COIN_SET:-${MVS_COIN:-1500}}" \
    FLOW_NORESTART="${FLOW_NORESTART_VAL:-0}" FLOW_RULES_ADDR="${FLOW_RULES_ADDR:-0}" \
    FLOW_PAGES="${FLOW_PAGES_VAL:-0}" FLOW_PAGES_C="${FLOW_PAGES_C_VAL:-0}" \
    FLOW_PAGE_ADDR="${FLOW_PAGE_ADDR:-0}" FLOW_T_ADDR="${FLOW_T_ADDR:-0}" \
    FLOW_ENTRY_ADDR="${FLOW_ENTRY_ADDR:-0}" FLOW_DOME_SNAP="${FLOW_DOME_SNAP_VAL:-0}" \
    FLOW_LEVEL="${FLOW_LEVEL_VAL:-0}" FLOW_RETURN="${FLOW_RETURN_VAL:-0}" \
    FLOW_LEVEL_ADDR="${FLOW_LEVEL_ADDR:-0}" FLOW_MIS_ADDR="${FLOW_MIS_ADDR:-0}" \
    FLOW_SHIP_ADDR="${FLOW_SHIP_ADDR:-0}" \
    FLOW_CELL_RING_ADDR="${FLOW_CELL_RING_ADDR:-0}" \
    FLOW_CELL_PHI_ADDR="${FLOW_CELL_PHI_ADDR:-0}" \
    FLOW_BEST="${FLOW_BEST_VAL:-0}" FLOW_BEST_RETURN="${FLOW_BEST_RETURN_VAL:-0}" \
    FLOW_BEST_ADDR="${FLOW_BEST_ADDR:-0}" \
    FLOW_STATE_ADDR="${FLOW_STATE_ADDR:-0}" ENTRY_STATE_ADDR="${ENTRY_STATE_ADDR:-0}" \
    ENTRY_FC_ADDR="${ENTRY_FC_ADDR:-0}" FLOW_ENTRY_FINISH="${FLOW_ENTRY_FINISH_VAL:-0}" \
    FLOW_BLINK_ACTIVE_ADDR="${FLOW_BLINK_ACTIVE_ADDR:-0}" \
    ENTRY_CASE="${ENTRY_CASE_VAL:-}" \
    FLOW_BEST_AES="${FLOW_BEST_AES_VAL:-0}" FLOW_CARDLOG_ADDR="${FLOW_CARDLOG_ADDR:-0}" \
    SOUND_LOG_ADDR="${SOUND_LOG_ADDR:-0}" SOUND_LOGN_ADDR="${SOUND_LOGN_ADDR:-0}" \
    SOUND_TITLE_FC_ADDR="${SOUND_TITLE_FC_ADDR:-0}" \
    SOUND_DEMO="${SOUND_DEMO_VAL:-0}" \
    SOUND_GLOG_ADDR="${SOUND_GLOG_ADDR:-0}" SOUND_GN_ADDR="${SOUND_GN_ADDR:-0}" \
    SOUND_FRAMECNT_ADDR="${SOUND_FRAMECNT_ADDR:-0}" \
    SOUND_RADAR_MODE="${SOUND_RADAR_VAL:-0}" \
    SOUND_GAME_POLICY="${SOUND_GAME_POLICY:-centred}" \
    DEMO_MODE="${DEMO_MODE_VAL:-cycle}" \
    DEMO_EPOCH_ADDR="${DEMO_EPOCH_ADDR:-0}" DEMO_FC_ADDR="${DEMO_FC_ADDR:-0}" \
    DEMO_HASH_EPOCH_ADDR="${DEMO_HASH_EPOCH_ADDR:-0}" \
    DEMO_HASH_FC_ADDR="${DEMO_HASH_FC_ADDR:-0}" \
    DEMO_HASH_DONE_ADDR="${DEMO_HASH_DONE_ADDR:-0}" \
    DEMO_HASH_ADDR="${DEMO_HASH_ADDR:-0}" \
    DEMO_FRAMECNT_ADDR="${DEMO_FRAMECNT_ADDR:-0}" \
    DEMO_RULES_ADDR="${DEMO_RULES_ADDR:-0}" DEMO_SHIP_ADDR="${DEMO_SHIP_ADDR:-0}" \
    DEMO_MIS_ADDR="${DEMO_MIS_ADDR:-0}" DEMO_RADAR_ADDR="${DEMO_RADAR_ADDR:-0}" \
    DEMO_TITLE_SEED_ADDR="${DEMO_TITLE_SEED_ADDR:-0}" \
    DEMO_BEST_ADDR="${DEMO_BEST_ADDR:-0}" \
    DEMO_PAGE_ADDR="${DEMO_PAGE_ADDR:-0}" DEMO_T_ADDR="${DEMO_T_ADDR:-0}" \
    DEMO_LEVEL_ADDR="${DEMO_LEVEL_ADDR:-0}" \
    DEMO_AES_ON_ADDR="${DEMO_AES_ON_ADDR:-0}" \
    DEMO_TOGGLES_ADDR="${DEMO_TOGGLES_ADDR:-0}" \
    PROPS_ANGLE_ADDR="${PROPS_ANGLE_ADDR:-0}" \
    DEMO_START_DFC="${DEMO_START_DFC:-0}" \
    WORK_START_ADDR="${WORK_START_ADDR:-0}" WORK_END_ADDR="${WORK_END_ADDR:-0}" \
    WORK_MAX_ADDR="${WORK_MAX_ADDR:-0}" WORK_MIN_ADDR="${WORK_MIN_ADDR:-0}" \
    SKY_FRAMECNT_ADDR="${SKY_FRAMECNT_ADDR:-0}" \
    GROUND_FRAMECNT_ADDR="${GROUND_FRAMECNT_ADDR:-0}" \
    MTN_FRAMECNT_ADDR="${MTN_FRAMECNT_ADDR:-0}" MTN_SHIP_ADDR="${MTN_SHIP_ADDR:-0}" \
    BAND_FRAMECNT_ADDR="${BAND_FRAMECNT_ADDR:-0}" BAND_SHIP_ADDR="${BAND_SHIP_ADDR:-0}" \
    CON_FRAMECNT_ADDR="${CON_FRAMECNT_ADDR:-0}" \
    PROPS_FRAMECNT_ADDR="${PROPS_FRAMECNT_ADDR:-0}" \
    PROPS_SHIP_ADDR="${PROPS_SHIP_ADDR:-0}" TEAR_DRIVE="${TEAR_DRIVE:-spin}" \
    CENSUS_EVERY="${CENSUS_EVERY:-10}" \
    MVS_START="${MVS_START_VAL:--100}" \
    MIS_SEED_ADDR="${MIS_SEED_ADDR:-0}" MIS_ADDR="${MIS_ADDR:-0}" \
    MIS_R_SPAWN_ADDR="${MIS_R_SPAWN_ADDR:-0}" \
    MIS_CELL_RING_ADDR="${MIS_CELL_RING_ADDR:-0}" \
    MIS_CELL_PHI_ADDR="${MIS_CELL_PHI_ADDR:-0}" \
    MIS_PROBE_FIRST="${MIS_FIRST_VAL:-0}" \
    SPIDER_SHIP_ADDR="${SPIDER_SHIP_ADDR:-0}" \
    SPIDER_RULES_ADDR="${SPIDER_RULES_ADDR:-0}" \
    SPIDER_MIS_ADDR="${SPIDER_MIS_ADDR:-0}" \
    SPIDER_FRAMECNT_ADDR="${SPIDER_FRAMECNT_ADDR:-0}" \
    SPIDER_DEMO_EPOCH_ADDR="${SPIDER_DEMO_EPOCH_ADDR:-0}" \
    SPIDER_DEMO_FC_ADDR="${SPIDER_DEMO_FC_ADDR:-0}" \
    SPIDER_DEMO_HASH_ADDR="${SPIDER_DEMO_HASH_ADDR:-0}" \
    SPIDER_MIS_CELL_RING_ADDR="${SPIDER_MIS_CELL_RING_ADDR:-0}" \
    SPIDER_MIS_CELL_PHI_ADDR="${SPIDER_MIS_CELL_PHI_ADDR:-0}" \
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
elif [[ "$MODE" == tear ]]; then
    python3 "$REPO/tests/check_tear.py" "$OUT/probe.txt"
elif [[ "$MODE" == ship-respawn || "$MODE" == ship-respawn-nodeath ]]; then
    SHIP_NODEATH="${NODEATH_VAL:-0}" python3 "$REPO/tests/check_ship_respawn.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$SHIP_FRAMECNT_ADDR" "$SHIP_RC_ADDR"
elif [[ "$MODE" == spider ]]; then
    python3 "$REPO/tests/check_spider.py" "$OUT/probe.txt"
elif [[ "$MODE" == hud ]]; then
    python3 "$REPO/tests/check_hud.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" "$HUD_EVENTS_ADDR"
elif [[ "$MODE" == gameover-draw ]]; then
    python3 "$REPO/tests/check_gameover_draw.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"  \
        "$GO_TEST_ADDR" "$GO_FRESH_ADDR"
elif [[ "$MODE" == radar ]]; then
    python3 "$REPO/tests/check_radar.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$RADAR_MIS_ADDR" "$RADAR_SHIP_ADDR" "$RADAR_FRAMECNT_ADDR"
    # the snapshot with a locked missile on the radar, for the user and the
    # orchestrator (the task's proof 5)
    cp "${SNAP:-$OUT/snap.png}" "$REPO/docs/superpowers/m5-radar.png"
elif [[ "$MODE" == sound || "$MODE" == sound-mvs ]]; then
    # the sound checks: the AES leg (M7 Task 1) proves every send
    # acknowledged and each sample silent-before / loud-after / right
    # length; the MVS leg (Attract A4) proves the demo's commands match
    # the model with DEMO SOUND ON, none with it OFF, a real game after
    # OFF still sounds, and the ROM header names the DIP.
    [[ -f "$SOUND_WAV" ]] || { echo "boot_test: FAIL — no sound WAV at $SOUND_WAV"; exit 1; }
    if [[ "$MODE" == sound-mvs ]]; then
        python3 "$REPO/tests/check_sound.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" "$SOUND_WAV" demo "$DEMO_ELF"
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
elif [[ "$MODE" == sky ]]; then
    python3 "$REPO/tests/check_sky.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"
elif [[ "$MODE" == mountains ]]; then
    # dome-scenery Task 6: the mountains. The probe presses Start, walks the
    # ship up to the peak and spins the dome left through the panorama (and
    # back right to 230), reading the driver's SCB3/SCB4 and all 21 chain
    # columns' SCB1 words at dome angles 0, 1, 160, 161, 239 and 230, and
    # snapshotting the title (fc 0) and a wrapping frame with a scroll phase
    # (da 161). tests/check_mountains.py compares every read with the model
    # and the WINDOW snapshot's band with the generated picture.
    python3 "$REPO/tests/check_mountains.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"
elif [[ "$MODE" == band ]]; then
    # dome-scenery Task 17: the band. The probe presses Start, walks the
    # ship up to the peak and spins the dome left through the panorama (and
    # back right to 230), reading the driver's SCB3/SCB4 and all 21 chain
    # columns' SCB1 words at eight dome angles, and snapshotting the title
    # (fc 0) and a wrapping frame with a scroll phase (da 232).
    python3 "$REPO/tests/check_band.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"
elif [[ "$MODE" == console ]]; then
    python3 "$REPO/tests/check_console.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"
elif [[ "$MODE" == props ]]; then
    python3 "$REPO/tests/check_props.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"
elif [[ "$MODE" == ground ]]; then
    python3 "$REPO/tests/check_ground.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"
elif [[ "$MODE" == ripple ]]; then
    python3 "$REPO/tests/check_ripple.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt"
elif [[ "$MODE" == demo || "$MODE" == demo-start ]]; then
    python3 "$REPO/tests/check_demo.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" "$MODE"
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
    # the NORMAL game, and NORMAL's board-page return; flow-return-best (M6
    # Task 9) adds the backup-RAM high-score proof on the returned title.
    python3 "$REPO/tests/check_flow.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$FLOW_FRAMECNT_ADDR" "0" "$MODE"
elif [[ "$MODE" == entry-lives || "$MODE" == entry-ruin ]]; then
    # high-score boards Task B6: the entry-screen checker (ring tables,
    # dome angle, typed initials/erase/auto-jump/END, board + card save,
    # census, and the returned title's blink).
    python3 "$REPO/tests/check_entry.py" "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$FLOW_FRAMECNT_ADDR" "$ENTRY_STATE_ADDR" "$ENTRY_FC_ADDR" \
        "$FLOW_STATE_ADDR" "$FLOW_CARDLOG_ADDR" "$ENTRY_CASE_VAL"
elif [[ "$MODE" == best-mvs ]]; then
    # high-score boards Task B2: the checker keys the nvram state on
    # BEST_REUSE / BEST_OLD / BEST_FRESH (2 = run 2, sharing; 3 = run 3,
    # old 'ESRG' magic; 4 = run 4, fresh; else run 1).
    if [[ "${BEST_REUSE:-0}" == "1" && "${BEST_OLD:-0}" == "1" ]]; then
        BEST_LEG=3
    elif [[ "${BEST_REUSE:-0}" == "1" ]]; then
        BEST_LEG=2
    elif [[ "${BEST_FRESH:-0}" == "1" ]]; then
        BEST_LEG=4
    else
        BEST_LEG=1
    fi
    BEST_NVRAM_LEG="$BEST_LEG" python3 "$REPO/tests/check_flow.py" \
        "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$FLOW_FRAMECNT_ADDR" "0" "$MODE"
elif [[ "$MODE" == best-aes ]]; then
    # high-score boards Task B2: the checker keys the card state on
    # BEST_REUSE / BEST_OLD / BEST_NOCARD (2 = run 2, sharing the card; 3 =
    # run 3, old 'ESRG' magic; 4 = run 4, no card; else run 1).
    if [[ "${BEST_REUSE:-0}" == "1" && "${BEST_OLD:-0}" == "1" ]]; then
        BEST_CARD_LEG=3
    elif [[ "${BEST_REUSE:-0}" == "1" ]]; then
        BEST_CARD_LEG=2
    elif [[ "${BEST_NOCARD:-0}" == "1" ]]; then
        BEST_CARD_LEG=4
    else
        BEST_CARD_LEG=1
    fi
    BEST_CARD_LEG="$BEST_CARD_LEG" python3 "$REPO/tests/check_flow.py" \
        "${SNAP:-$OUT/snap.png}" "$OUT/probe.txt" \
        "$FLOW_FRAMECNT_ADDR" "0" "$MODE"
else
    python3 "$REPO/tests/check_snapshot.py" "${SNAP:-$OUT/snap.png}" "$MODE"
fi
