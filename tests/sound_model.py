"""Reference model of src/sound.h's sound_frame_cmds (R1): the game's
per-frame sound command list.

The C function is the one src/flow.c's game_sound calls, and
tests/test_sound_host.py runs it in build/sound_sim beside this model on a
scripted game; the MAME sound legs (tests/check_sound.py's demo mode and
tests/check_sound_game.py) predict the cart's sends with the same model.
So the cart's command list and the model cannot drift apart.

The order is the Vectrex's: jump, fire, the death/hit/crack (a crack wins
over a hit in the same frame), the scuttle, the collapse's alternating
rumble, the lock pip.

The scuttle (the design's call):
  - on the first frame of every walk move (move_left == mlen ==
    SHIP_MOVE_FRAMES);
  - at the peak, while spinning, on the spin's first frame and every
    SHIP_MOVE_FRAMES frames after (the period restarts when the spin
    stops and starts again);
  - never on a jump's frame, and never while the ship is dead.

The collapse's five beats are the death's HIT (frame 0), then CRACK at
collapse_frac 9, HIT at 18, CRACK at 27 and HIT at 36: the two explosions
alternate.
"""
import mis_model as mm
import rules_model as rm
import ship_model as sm

SND_FIRE, SND_JUMP, SND_HIT, SND_CRACK, SND_PIP, SND_MOVE = 4, 5, 6, 7, 8, 9


class Sound:
    """the frame-to-frame state: the scuttle's spin period and the pip's
    0..19 counter (src/sound.h's sound_state_t)."""

    def __init__(self):
        self.spin_t = 0
        self.spin_was = 0
        self.pip_t = 0

    def cmds(self, ship, mis, rules, radar, died):
        """-> the frame's command list, as src/sound.h's sound_frame_cmds."""
        out = []
        if ship.jumped:
            out.append(SND_JUMP)
        if mis.sfx & mm.SFX_FIRE:
            out.append(SND_FIRE)
        if died:
            out.append(SND_HIT)
        elif mis.sfx & mm.SFX_CRACK:
            out.append(SND_CRACK)
        elif mis.sfx & mm.SFX_HIT:
            out.append(SND_HIT)

        alive = not (rules.dead_t or rules.game_over)
        scuttle = False
        if alive:
            if ship.left == sm.MOVE and ship.mlen == sm.MOVE:
                scuttle = True                      # a walk's first frame
            elif ship.spinning:
                if not self.spin_was or self.spin_t == 0:
                    scuttle = True
                    self.spin_t = sm.MOVE
                else:
                    self.spin_t -= 1
                    if self.spin_t == 0:
                        scuttle = True
                        self.spin_t = sm.MOVE
            else:
                self.spin_t = 0
        else:
            self.spin_t = 0
        self.spin_was = ship.spinning
        if scuttle and not ship.jumped:
            out.append(SND_MOVE)

        if rules.dead_t and rules.dome_dead:
            f = rm.DEAD_FRAMES_NEO - rules.dead_t
            if f in (9, 27):
                out.append(SND_CRACK)
            elif f in (18, 36):
                out.append(SND_HIT)

        if radar.locked:
            if self.pip_t == 0:
                out.append(SND_PIP)
            self.pip_t += 1
            if self.pip_t == 20:
                self.pip_t = 0
        else:
            self.pip_t = 0
        return out
