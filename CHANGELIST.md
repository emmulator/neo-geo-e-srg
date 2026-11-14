# Changelist

## 2.0.0

No longer only a port: the Vectrex game's rules, with a new look, a new
sound, a landscape and a high-score table.

- The player is a cherry-red 1950s hovercraft, a finned automobile crossed
  with a desert landspeeder: it hovers, dips and launches for a jump, is
  pushed down by the recoil when it fires, and turns to face the way it
  moves. It fires short laser bolts; the missiles are flickering rockets.
  New sounds: a soft hover, a pew, two explosions.
- A landscape: parallax mountains, a band of towns and forests, trees and
  rocks in woods and outcrops (they pass in front of the dome and darken in
  its shadow), and grass whose colours ripple as the dome turns.
- The dome leaves a ruin when it dies: a fireball, flying glass, smoke.
- The title is drawn over a game that plays itself, in gold lettering with
  a black outline, and the version below "press start".
- High-score boards: five entries per level with initials, entered on a
  halo ring (a letter flies to its slot, with tick, typewriter, bell and
  backspace sounds; the typewriter is a CC0 recording, see CREDITS.md),
  kept in backup RAM (MVS) and on the memory card (AES). Scores saved by
  1.0.0 are not carried over (the cart has its own NGH number, 7278).
- GAME OVER in the title's outlined lettering; the shot has its own sound
  channel, so walking no longer cuts it off.

## 1.0.0

The first release: every element of Vectrex E-SRG 1.1.1 on the Neo Geo.

- The rotating geodesic dome, its cracks, broken windows and collapse,
  pre-rendered from the Vectrex geometry; the ship, bullets, missiles and
  their explosions; the radar and the stars.
- The Vectrex rules: rings opening at 6 hits, EASY's slower missiles, the
  dome staying gone under GAME OVER after a dome death.
- Every game opens with different missiles: the RNG is seeded from how long
  the title was up when Start was pressed.
- Title pages (B changes level, C turns the page), high scores kept in
  backup RAM (MVS) and on the memory card (AES), MVS coin, countdown and no
  free restart.
- The sound effects, rendered from the Vectrex AY scripts as ADPCM-A samples.
- Neo Geo art: the E-SRG logo, a 5x7 font in its style, tracer bullets; no
  BIOS eye-catcher.
