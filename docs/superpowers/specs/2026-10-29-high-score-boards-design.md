# High-score boards with a halo initials ring (design, 2026-10-29)

## Intent

E-SRG is a retro arcade video game. Today it keeps one best score per
difficulty. It gets proper arcade high-score boards: five entries per
difficulty, each with three initials, entered on a ring of letters that
floats like a halo over the dome (or the ruin, if the game ended in a
collapse) and turns with the scene as the player pushes left and right.
Separately, the title text is hard to read over the attract demo, so the
title font gets a thicker black outline.

The mockup the user approved (10-29), playable:
`~/Downloads/esrg-hiscore-ring.html` (generator in the orchestrator's
scratch; the look is reproduced by the generators below, not the page).

## What the user decided

- **Five slots per difficulty**, three initials each.
- **The characters** are A–Z, space and `. ! ? - & '`, a star and a heart
  (no digits), plus **←** (erase the last initial) and **END** (finish):
  37 positions on the ring, in that order, wrapping round.
- **The ring hovers over the dome**, or over the ruin when the game ended in
  a collapse, and **turns with the scene**: left/right turn the ring one
  position, and the dome, scenery and ruin turn with it. **A** picks the
  letter at the front.
- **Letters only, the whole ring** (no halo band): all 37 positions shown,
  the back half smaller and dimmer, the front letter bright white with a
  blinking pointer under it.
- **After the third initial the ring turns to END by itself.**
- **No time limit** on the entry (on the MVS too).
- **Three title pages**, one board per difficulty, in the title's page
  rotation. They replace today's HIGH SCORES page, as pages 1, 2 and 3
  (EASY, NORMAL, HARD); each shows `HIGH SCORES`, the level's name and five
  rows `1ST  SRG   50000` (the orchestrator's layout). Page 0 keeps its
  best line, showing that level's top entry (the orchestrator's call).
- **A fresh board has default entries**: SRG 50,000, HEX 40,000, DOM 30,000,
  ZAP 20,000, VEC 10,000, the same on every difficulty.
- **Old saved bests are dropped**: the new board format replaces the old
  table (backup RAM and the memory card).
- **Title text: the thicker outline** (mockup option 2): the title font's
  black outline becomes 2 px, not 1. The colours stay as they are.

## Behaviour

- **Qualifying:** a game's final score enters its difficulty's board if it
  is strictly greater than the 5th entry; it goes below any equal scores.
- **When:** at GAME OVER, the GAME OVER text shows as today for 2 seconds
  (the orchestrator's call: 118 frames), then a qualifying game goes to the
  entry screen; a game that does not qualify keeps today's GAME OVER window
  (295 frames, A restarts). On the entry screen there is no A-restart: A
  picks letters.
- **The entry screen** (fix text in the title font, as in the mockup):
  row 2 `NEW HIGH SCORE`, row 4 `<LEVEL>  <RANK>  <SCORE>`, row 6 the three
  initials (`A B _`, the next slot blinking). The HUD (radar, score,
  integrity, lives) stays as at GAME OVER. No ship is drawn.
- **The ring** starts with A at the front. Right turns the next position
  (to the right on screen) to the front; left the previous. One press, one
  position; holding repeats (the orchestrator's call: after 16 frames, then
  every 8). Each step animates over 6 frames, ring and scene together; the
  scene turns 240/37 dome-angle steps per position, accumulated so that 37
  positions are exactly one full turn of the dome. The dome turns **with**
  the ring (the user's pick, 10-30, from MAME footage of both): Right lowers
  the dome angle, as Right spins the dome in play, so the dome's near side
  moves the same way as the ring's front letters.
- **A** on a letter or symbol appends it (at most three); on **←** removes
  the last initial (nothing if none); on **END** finishes, padding missing
  initials with spaces (the orchestrator's call). After the third initial
  the ring turns to END the short way round, animated like the player's
  steps but at twice their rate (two sub-steps a frame: the user's ask,
  10-30).
- **B does nothing** on the entry screen (the orchestrator's call: A
  picks, ← erases).
- **Stored initials** are bytes: ASCII for the letters, space and
  punctuation; the star and heart get two fixed codes that the title font
  draws (the orchestrator's call; the generator defines them).
- **After END** the board is saved (backup RAM on the MVS; on the AES the
  memory card, as the best table is today) and the cart returns to the
  title, which opens on that difficulty's board page, the new entry
  blinking for the first page (the orchestrator's call).

## The look (the orchestrator's art, generated)

- **Ring geometry** (screen px, from the mockup): centre x 160, y 94 over
  the dome and 92 over the ruin; radii 94 x 23; position k at angle
  2πk/37 from the front, the front at the ellipse's bottom (nearest the
  camera). Each glyph is one 16 x 16 sprite tile (END fits in one), its
  shrink 0.45 at the back to 1.0 at the front (SCB2), back half in a dim
  palette, the front letter in a white-hot palette, the rest gold. The
  pointer is a small white triangle under the front letter, blinking every
  8 frames.
- **Glyphs**: the game's 5 x 7 font doubled to 10 x 14 with a 1-px black
  outline; the star, heart, ← and the small-caps END are new glyphs. The
  generator (`tools/render_ring.py`, the orchestrator's) writes the tiles,
  the three palettes and a header.
- **The title font's 2-px outline** spills into the neighbouring 8 x 8
  cells (a 5 x 7 glyph with 2 px each side is 9 x 11). The generator
  (`tools/generate_srom.py`, the orchestrator's) adds the edge tiles (the
  outline that falls in the cell to the right, above, below and on the
  corners), and the title's row writer composes them where a glyph
  borders a space or a blank row. The star, heart and `&` join the title
  font so the boards can show every initial.

## Constraints

- **Sprites per line:** the Neo Geo draws at most 96 sprites on a scanline.
  The ring adds 37 sprites, many on the same lines at its left and right
  ends; the busiest line must stay at most 96 with the ring over the dome
  and over the ruin. If it does not, the builder stops and reports the
  census (the user chose the whole ring; a cut is the user's call).
- **The demo** is the real game and its cycle is 9 title pages x 295
  frames today; three board pages make 11. The orchestrator regenerates the
  demo script for the new cycle (`tools/gen_demo.py`). The demo never
  enters initials (the demo's score does not save, as today).
- **Saving** stays outside play frames (GAME OVER, END, an entry), like
  today's best table. The board is a packed struct with a magic and a sum
  like `best_t`, a new magic (so an old table reads as invalid and the
  board starts from the defaults).
- **No time limit** includes the MVS: the entry waits for END.

## Non-goals

- No change to scoring, the game's rules, or the game's frame.
- No digits in initials; no name longer than three.
- No high-score entry from the attract demo.

## Left to the builder

The board's struct layout and API (pure logic, host-tested like
`best.c`), the flow state for the entry screen, the ring's sprite slots and
their back-to-front order, the card's save size, and how the title's row
writer places the outline's edge tiles.
