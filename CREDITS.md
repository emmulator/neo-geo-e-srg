# Credits

E-SRG is a retro arcade video game. Everything in this repository is the
project's own work except the assets below.

## Sounds

- **`assets/sfx/type.wav`**, the typewriter strike when a letter is picked
  on the high-score entry screen. Cut from
  ["old typewriter"](https://freesound.org/s/145534/) by
  [monotraum](https://freesound.org/people/monotraum/) on Freesound,
  dedicated to the public domain under
  [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). Chosen by
  ear from eight CC0 recordings on 2026-10-31.

  How it was made: Freesound's high-quality MP3 preview of sound 145534,
  decoded to mono and resampled to 18,500 Hz (the ADPCM-A encoder's rate)
  with sox, normalised, one keystroke cut from 10.928 s (12 ms before its
  onset at 10.94 s) for 299 ms with a 30 ms fade-out, then soft-limited
  (tanh, drive 3.75) and scaled to a 0.95 peak, so that its loudest 100 ms
  (RMS 0.257) sits with the game's other effects.
