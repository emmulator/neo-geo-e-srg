-- ship_respawn_probe.lua: the M4-fixes Task 1 boot-test.
--
-- Drives the normal cart through a deterministic death and respawn (the
-- hold-Up policy: centred for the first 60 cart frames, Up held from then
-- on, no fire — the ship rests at the start cell until a missile breaks
-- it, then dies and comes back) and proves, from VRAM and snapshots, that
-- the respawned ship is exactly the ship at the start of the game:
--
--   1. the ship slots' SCB2/3/4 and SCB1 rows read at the
--      respawn frame equal the same words read at the start of the game
--      (the cart frame 45 read is the "start of game" truth; the respawn
--      read is at +DEAD_FRAMES_NEO frames after the model's first death,
--      itself read from the rules' debug exports);
--   2. the respawned ship's RC (respawn-complete) flag is set at that
--      frame (proves the respawn frame was the actual one);
--   3. the snapshot's ship pixel count at the respawn frame equals the
--      count at the start of the game (the same whole ship — the bug's
--      right column, a non-sticky sprite with height 0, draws nothing).
--
-- The policy and every expected frame come from the model (the ship_model /
-- mis_model / rules_model reference), and tests/check_ship_respawn.py
-- replays the model from the recorded inputs — the checker states the
-- death and respawn frames, and the probe's RC flag proves the cart had
-- really respawned at the dump.
--
-- The ship is 2 columns x 2 tiles; its two slots are a sticky chain
-- (column 1's SCB3 is the sticky word $0040, height 0). The game's stable
-- boot picture (fc 45, before the first launch) has nothing else in the
-- ship's slots: the ship, full size, on the start cell.
--
-- Output (all ship slots):
--   I <rec> <fc> <cur> <chg> <rc>          every record (input read-back
--                                          + the rules' respawn-complete
--                                          debug bit)
--   D <fc> <death> <rc>                    the first death is seen (rc
--                                          cleared, dead_t > 0)
--   X <fc> <death> <rc>                    the dump at the respawn frame
--   W <slot> <scb2> <scb3> <scb4> <attr> <tile0> <tile1> <tile2> <tile3>
--      slot row of a dump (both columns; SCB1 row 0..3, the 2x2 picture)
--   C <fc> <death> <rc>                    the dump at the start of the
--                                          game (fc 45)
--   S1 <fc>                                first snapshot (start of game)
--   S2 <fc>                                second snapshot (after the respawn)
-- Env: OUT, FRAMES (MAME frames to run), SHIP_FRAMECNT_ADDR,
-- SHIP_RC_ADDR (the cart's frame counter and the rules' respawn-complete
-- debug bit; 0 disables the exact alignment). The NODEATH mode (a centred
-- ship the whole run, ~230 cart frames): the ship never breaks, and the
-- checker proves the ship slots are bit-identical between the C dump and a
-- later dump, so a fresh boot can never mask the hide bug.
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "3500")
local framecnt_addr = tonumber(os.getenv("SHIP_FRAMECNT_ADDR") or "0")
local rc_addr = tonumber(os.getenv("SHIP_RC_ADDR") or "0")
local nodeath = os.getenv("SHIP_NODEATH") == "1"

local BI, CHG = 0x10fd96, 0x10fd97
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local SHIP_SPRITE, SHIP_COLS, SHIP_ROWS = S.SHIP_SPRITE, S.SHIP_COUNT, 2
local DEAD_FRAMES_NEO = 118            -- rules.h: 100 Vectrex frames x 59/50
local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
-- the cart now boots to a title: this helper presses Start to begin a game
-- (M6 Task 1), and exposes game_started(fc) to keep our drive() off the title
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")
local MS = dofile((os.getenv("REPO") or ".") .. "/scripts/mis_seed.lua")

-- VRAM is read (and, by the leftover probe, written) through MAME's own copy
-- of it, never through the LSPC registers at 0x3c0000/2: writing the address
-- register from a frame callback changes the cart's VRAM pointer under it, and
-- the cart's next writes land at the probe's address (it zeroed title rows).
local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(a)
    return vram:read(a)
end

local f = assert(io.open(out, "w"))
local n, in_cart, rec = 0, 0, 0
local death = nil          -- cart frame of the first death
local was_alive = 1        -- the last-seen alive flag (for the edges)
local dumped_start, dumped_after = false, false
local respawn_pending = false   -- the next frame is the first shown respawn

-- the cart's frame counter (0 until the first main-loop frame)
local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec
end

-- the rules' respawn-complete flag: 1 while the ship is alive and the game
-- is on (cleared during a death's countdown; the frame it comes back, the
-- flag is 1 again and the ship is whole)
local function rc()
    if rc_addr ~= 0 then
        return sp:read_u8(rc_addr)
    end
    return 1
end

-- the hold-Up policy: centred for the first 60 cart frames (so the first
-- launches reach the dome before the ship is ever in the way), Up held
-- from then on (the ship parks out of the wave), never A. The NODEATH
-- mode stays centred the whole run instead.
local function drive(fc)
    if not SG.game_started(fc) then     -- the title: no input of our own
        return
    end
    if nodeath then
        joy.fields["P1 Up"]:set_value(0)
    else
        joy.fields["P1 Up"]:set_value(fc >= 60 and 1 or 0)
    end
    joy.fields["P1 A"]:set_value(0)
end

-- one ship slot's full state: SCB2/3/4, the SCB1 attribute, and the 4
-- SCB1 tile rows of the 2x2 picture
local function slot_line(slot)
    local line = string.format("W %d %04x %04x %04x %04x",
                               slot, vread(SCB2 + slot), vread(SCB3 + slot),
                               vread(SCB4 + slot), vread(SCB1 + slot * 64 + 1))
    for r = 0, SHIP_ROWS - 1 do
        line = line .. string.format(" %04x", vread(SCB1 + slot * 64 + r * 2))
    end
    f:write(line .. "\n")
end

-- the start-of-game dump (cart frame 45: the labels drawn, the ship on the
-- start cell, the first launch still ~14 frames away), or the after-death
-- dump (death + DEAD_FRAMES_NEO, when the respawned ship is at [27, 27]
-- and the only broken cell is far from it on screen)
local function dump(tag, fc, death, rcnow)
    f:write(string.format("%s %d %s %d\n", tag, fc, death or "-", rcnow or 0))
    for c = 0, SHIP_COLS - 1 do
        slot_line(SHIP_SPRITE + c)
    end
end

-- the actual loop, driven from the frame notifier (the AES BIOS preamble
-- runs at low addresses; the cart's code lives at 0x100000+)
local function tick()
    n = n + 1
    if in_cart == 0 and cpu.state["PC"].value >= 0x100000 then
        in_cart = 1
    end
    SG.sg_apply(n)
    if in_cart then
        rec = rec + 1
        local fc = framecnt()
        local rcnow = rc()
        f:write(string.format("I %d %d %d %d %d\n", rec, fc, sp:read_u8(BI),
                              sp:read_u8(CHG), rcnow))
        MS.poll(f, n, fc)
        drive(fc)                          -- input for the frames ahead
        -- the first death: the alive flag's 1 -> 0 edge (the death lands
        -- in rules_end, so the flag clears on the frame AFTER the death
        -- frame — the fall is the flag re-rising to 1 on the exact frame
        -- the ship comes back, which is the frame the dump must hit).
        if not death and fc >= 60 and was_alive == 1 and rcnow == 0 then
            death = fc
            f:write(string.format("D %d %d %d\n", fc, death, rcnow))
        end
        local respawned = death ~= nil and was_alive == 0 and rcnow == 1
        if respawned then
            -- the ship_gfx_prepare's SCB1/SCB3 commit is one vblank behind
            -- the state (Task S2), so the frame whose slots show the
            -- respawned ship is the one AFTER the RC flag rises.
            respawn_pending = true
        end
        -- the start-of-game truth, taken before the first launch arrives
        if not dumped_start and fc == 45 then
            dump("C", fc, death, rcnow)
            dumped_start = true
            machine.video:snapshot()       -- the first snapshot
            f:write(string.format("S1 %d\n", fc))
        end
        -- after the respawn: the model's death + DEAD_FRAMES_NEO (the frame
        -- the countdown ends and the ship comes back, whole, at rest on the
        -- start cell). The RC flag must be back to 1 (the ship really is
        -- back), and the slots must hold the same words the start-of-game
        -- dump read (the ship sits at [27, 27], and cell 0's crack is far
        -- above it on screen).
        if nodeath then
            -- the no-death robustness leg: dump and snapshot again before
            -- the first missile can reach the dome (the first landing is
            -- at cart frame ~285, aimed at the peak — far from the ship);
            -- the ship has never died, so a hide never ran
            if not dumped_after and fc >= 200 then
                dump("X", fc, death, rcnow)
                dumped_after = true
                machine.video:snapshot()
                f:write(string.format("S2 %d\n", fc))
            end
        elseif not dumped_after and respawn_pending and not respawned then
            dump("X", fc, death, rcnow)
            dumped_after = true
            respawn_pending = false
            machine.video:snapshot()       -- the second snapshot
            f:write(string.format("S2 %d\n", fc))
        end
        was_alive = rcnow
        -- Task 1: the hold-Up game's first death is at fc 3687 (seed 0xaede),
        -- not the 0xACE1 game's 486; its respawn is at 3687 + 118 = 3805,
        -- so the give-up bound (4000) sits past it
        local quit = (not nodeath) and not dumped_after and fc > 4000
        if quit and not dumped_after then
            f:write(string.format("NODEATH %d\n", fc))
        end
        -- stop after the second dump (the run's purpose is done; the
        -- MAME frames after the dump can only risk the ship breaking)
        if n >= run_len or (death and dumped_after) or (nodeath and dumped_after) or quit then
            f:write(string.format("pc_in_cart=%d frames=%d rec=%d death=%s "
                                  .. "dumped_start=%d dumped_after=%d\n",
                                  in_cart, n, rec, tostring(death or 0),
                                  dumped_start and 1 or 0,
                                  dumped_after and 1 or 0))
            f:close()
            machine:exit()
        end
    end
end

if emu.add_machine_frame_notifier then
    _G.__ship_respawn = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
