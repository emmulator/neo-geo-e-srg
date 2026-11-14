#!/usr/bin/env bash
# boot_test_all.sh — every boot-test leg (what `make boot-test` runs), in
# parallel. Each leg is one headless MAME run plus its checker
# (scripts/boot_test.sh MODE); run one at a time they took ~13 minutes,
# most of it the dozen legs that play a whole game (16k-28k frames). Each
# MAME is single-threaded, so the legs run side by side, BOOT_JOBS at a
# time (default: half the cores), each in its own output directory
# (BOOT_OUT=build/boot-legs/NN-MODE). Their outputs are printed in the
# list's order once all have finished, with each leg's wall time; the
# script exits 1 if any leg failed (every leg still runs, so one failure
# doesn't hide another).
#
# A job is one leg, or legs that must run in order (they share state):
# the two high-score groups, whose four runs share one nvram directory /
# one memory-card file.
#
# The cart paths come from the Makefile: CRKTEST_CART GET_CART RADTEST_CART.
#
#   scripts/boot_test_all.sh              all legs
#   BOOT_JOBS=1 scripts/boot_test_all.sh  one at a time (the old order)
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1
: "${CRKTEST_CART:?}" "${GET_CART:?}" "${RADTEST_CART:?}"
JOBS="${BOOT_JOBS:-$(( $(nproc) / 2 ))}"
(( JOBS < 1 )) && JOBS=1
LEGS_DIR="$REPO/build/boot-legs"

# the legs, in the old `make boot-test` order. A line is one job; ";;"
# separates legs that run in order within the job. Each leg is
# "[VAR=value ...] MODE"; values may not contain spaces.
BEST_NVRAM="$REPO/build/best-nvram"
BEST_CARD="$REPO/build/best-card"
LEGS=(
    "dome"
    "dome-lift"
    "ship"
    "BOOT_HOLD=P1_Up ship-top"
    "FRAMES=1000 missile"
    "FRAMES=1500 leftovers"
    "CRACK_CART=$CRKTEST_CART cracks"
    "CRACK_CART=$CRKTEST_CART CRACK_ANGLE=56 cracks"
    "hud"
    "collapse"
    "framemark"
    "crackframemark"
    "ship-respawn"
    "ship-respawn-nodeath"
    # Task S2: the stopper-spider animation (one demo cycle + a scripted
    # game: walk -> jump, a shot on the landing frame, a heave restart,
    # death and respawn)
    "spider"
    "GO_DRAW_CART=$GET_CART gameover-draw"
    "RADAR_CART=$RADTEST_CART radar"
    "flow"
    "flow-restart"
    "flow-pages"
    "flow-pages-c"
    "flow-level"
    "flow-return"
    "flow-return-best"
    # Attract A3: the demo cycle (state every frame, two cycles, B restart,
    # best scores, census, framemark) then the START-at-the-first-jump and
    # GAME OVER return run.
    "demo ;; demo-start"
    "flow-mvs"
    "flow-mvs-start"
    "flow-mvs-norestart"
    # high-score boards Task B6: the entry screen — the aiming game to a
    # lives-out GAME OVER over the dome, and the centred collapse game to
    # the ruin, each with the typed initials, erase, auto-jump and END.
    "entry-lives"
    "entry-ruin"
    # high-score boards Task B2: the backup-RAM board on MVS — four runs
    # sharing one fresh nvram directory: run 1 plays the aiming game to GAME
    # OVER, run 2 proves the board (including the game's entry) persisted
    # before any game, run 3 reuses it with the saved magic patched to the
    # old 'ESRG' (the entry must start from the defaults), run 4 (a fresh
    # nvram) proves the defaults.
    "BEST_NVRAM_DIR=$BEST_NVRAM best-mvs ;; BEST_NVRAM_DIR=$BEST_NVRAM BEST_REUSE=1 best-mvs ;; BEST_NVRAM_DIR=$BEST_NVRAM BEST_REUSE=1 BEST_OLD=1 best-mvs ;; BEST_NVRAM_DIR=$BEST_NVRAM BEST_FRESH=1 best-mvs"
    # high-score boards Task B2: the AES memory-card board — runs 1 and 2
    # share one -memcard file (run 2 with a FRESH nvram/cfg, proving the
    # card kept the board), run 3 reuses it with the saved magic patched to
    # the old 'ESRG' (the entry must start from the defaults), run 4 passes
    # no card (the 0x80 no-card path).
    "BEST_CARD_DIR=$BEST_CARD best-aes ;; BEST_CARD_DIR=$BEST_CARD BEST_REUSE=1 best-aes ;; BEST_CARD_DIR=$BEST_CARD BEST_REUSE=1 BEST_OLD=1 best-aes ;; BEST_CARD_DIR=$BEST_CARD BEST_NOCARD=1 best-aes"
    # M7: the sound pipeline and the game's sounds; Attract A4: the MVS
    # demo-sound soft DIP (the normal cart under the MVS BIOS)
    "sound"
    "sound-mvs"
    "sound-game"
    "sound-radar"
    # dome-scenery: the sky, the grass, the mountains, the band of towns and
    # forests, the console, the props
    "sky"
    "ground"
    # Task 19: the grass's ripple (palette rotation in vblank) on the props
    # leg's spin and the first dome death's gone frames
    "ripple"
    "mountains"
    "band"
    "console"
    "props"
    # Task 18: the props spin with the LSPC write tap (the tear check);
    # Task 18b adds the fire drive (missiles, explosions and the radar blink)
    "TEAR_DRIVE=spin tear"
    "TEAR_DRIVE=fire tear"
    # Attract A2: the cart left on the title for 600 frames; the scene's
    # vblank commits and every title fix write are tapped.
    "TEAR_DRIVE=title SG_ENABLE=0 tear"
)

# one job: its legs in order, each with its own BOOT_OUT; stops at the
# job's first failing leg (a later run of a group depends on the earlier).
run_job() {
    local idx="$1" job="$2" log="$3" leg rc=0 n=0
    : > "$log"
    IFS=$'\n' read -r -d '' -a parts < <(printf '%s' "$job" | sed 's/ ;; /\n/g'; printf '\0')
    for leg in "${parts[@]}"; do
        n=$((n + 1))
        local words=($leg) envs=() mode t0
        mode="${words[-1]}"
        for w in "${words[@]:0:${#words[@]}-1}"; do
            envs+=("${w//P1_Up/P1 Up}")         # BOOT_HOLD's value has a space
        done
        t0=$SECONDS
        env "${envs[@]}" BOOT_OUT="$LEGS_DIR/$(printf '%02d' "$idx")-$n-$mode" \
            scripts/boot_test.sh "$mode" >> "$log" 2>&1
        rc=$?
        echo "boot_test_all: leg $mode ($leg) exit $rc after $((SECONDS - t0)) s" >> "$log"
        (( rc != 0 )) && break
    done
    return "$rc"
}

rm -rf "$LEGS_DIR" "$BEST_NVRAM" "$BEST_CARD"
mkdir -p "$LEGS_DIR"
t_all=$SECONDS
i=0
for job in "${LEGS[@]}"; do
    i=$((i + 1))
    while (( $(jobs -rp | wc -l) >= JOBS )); do wait -n; done
    # each job leaves its exit status in a file: `wait -n` above may reap
    # a job before the final wait, so statuses aren't taken from wait
    ( run_job "$i" "$job" "$LEGS_DIR/job-$(printf '%02d' "$i").log"
      echo $? > "$LEGS_DIR/job-$(printf '%02d' "$i").rc" ) &
done
wait
fails=()
for k in $(seq 1 "$i"); do
    [[ "$(cat "$LEGS_DIR/job-$(printf '%02d' "$k").rc" 2>/dev/null)" == 0 ]] || fails+=("$k")
done
for k in $(seq 1 "$i"); do
    cat "$LEGS_DIR/job-$(printf '%02d' "$k").log"
done
echo "boot_test_all: ${#LEGS[@]} jobs, $JOBS at a time, $((SECONDS - t_all)) s"
if (( ${#fails[@]} )); then
    for k in "${fails[@]}"; do
        echo "boot_test_all: FAIL — job $k: ${LEGS[$((k - 1))]}"
    done
    exit 1
fi
