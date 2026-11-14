-- hud_probe.lua: the M4 Task 3 HUD boot-test (HUD-layout Task 2: the probe
-- now covers all 30 fix rows and snapshots the icon cells).
--
-- Drives the normal cart through a deterministic game and proves the fix
-- layer's text. The game's input comes from the BIOS joypad RAM (bios_p1
-- current = 0x10fd96, change = 0x10fd97), which the BIOS fills every frame
-- from the joypad ioports; this probe sets the ioports (the BIOS does its
-- own edge detection -> bios_p1change) and, every record, RECORDS the
-- read-back of both bytes. tests/check_hud.py replays the model of the
-- rules (tests/hud_model.py) with exactly the recorded inputs in order, so
-- the probe's sampling phase never matters — the model runs the same game
-- the cart saw, frame for frame.
--
-- Record ordinals vs cart frames: the AES BIOS spends ~470 MAME frames in
-- preamble before the cart's code runs, and the cart's startup (crt0 then
-- main's init) takes a few more, so the cart's frame counter (hud_framecnt,
-- a BSS u32, incremented once per main-loop frame) is 0 for the first ~477
-- records and counts from 1 after that. The input script below is keyed on
-- the CART frame (fc), not the MAME frame, so the A-restart lands on the
-- right game frame whatever the preamble length.
--
-- Script (by cart frame; the input is applied at the frame's end and read
-- back next frame, so the recorded I records are ground truth):
--   hold Up            game 1 plays itself: the ship rests out of the wave
--                      's reach, the dome keeps breaking until integrity 0,
--                      three deaths, then GAME OVER (fc 17525 under Task 1's
--                      seed at the default Start 600; 6509 with RNG_SEED, and
--                      4340 before): starting values, a crack (integ < 100),
--                      a death (lives < 3), GAME OVER all occur.
--   GAME OVER + 71: press A   the Vectrex's button 1 (inside
--                      the 295-frame window the cart waits before returning
--                      to the title): a new game -> GAME OVER gone, lives
--                      back to 3, integ 100, score 0.
--   restart+40+: Right  game 2 with fire (A tapped every 20 frames): kills,
--                      the score grows with its trailing 0.
--
-- Output:
--   I <rec> <fc> <current> <change>  every record (rec = ordinal since the
--                                    cart's code was reached; fc = the cart
--                                    frame number, 0 during startup)
--   F <fc>                           a FIXMAP read follows (at cart frame fc)
--   E <fc> <events>                  hud_dbg_events at that frame
--   R <r> <40 chars>                 fix row r decoded (tile = ASCII; the
--                                    icons are S ROM tiles 128/129, written
--                                    raw for the checker)
--   V <fc> <lives>                    the rules' lives byte (rules + 78), read
--                                    on the same fc a snapshot follows
--   SNAP <fc>                        a snapshot was taken this frame
-- Env: OUT, FRAMES (MAME frames to run), HUD_EVENTS_ADDR (0 disables),
-- HUD_FRAMECNT_ADDR (0 disables the exact-frame alignment; then I records
-- record the record number as fc too), HUD_RULES_ADDR (the static `rules`,
-- 0 disables the V record and the after-death snapshot).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "8160")
local events_addr = tonumber(os.getenv("HUD_EVENTS_ADDR") or "0")
local framecnt_addr = tonumber(os.getenv("HUD_FRAMECNT_ADDR") or "0")
local rules_addr = tonumber(os.getenv("HUD_RULES_ADDR") or "0")

local BI, CHG = 0x10fd96, 0x10fd97
local FR = 0x7000
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

local function hold(name, on)
    joy.fields[name]:set_value(on and 1 or 0)
end

local f = assert(io.open(out, "w"))
local n, in_cart, rec = 0, 0, 0
local snapped = false
local death_pending = 0    -- ticks until the after-death snapshot (0: not due)
local death_snap_done = false

-- the cart's frame counter (0 until the first main-loop frame)
local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec                              -- (fallback: the record number)
end

-- Task 1: the A-restart's frame — GAME OVER + 71, inside the 295-frame
-- window; the game over is read from the cart's RAM (rules.game_over) each
-- frame, so the press follows whatever timeline Task 1's seed gives (it was
-- keyed on a fixed fc 6580 before; the default 600 Start now ends at fc
-- 17525). Latch the first game-over frame.
local restart_at = nil
local function go_restart_at(fc, go)
    if go ~= 0 and restart_at == nil then
        restart_at = fc
    end
    if restart_at ~= nil and fc >= restart_at + 71 then
        return restart_at + 71
    end
    return nil
end

-- the input script, keyed on the cart frame; applied on the way out of the
-- current frame so the next one sees it (the recorded read-back is truth).
-- Since M6 Task 1 the cart spends GAME OVER inside a 295-frame window: the
-- A press must land within it (GAME OVER + 71), not 500 frames later, or
-- the cart would return to the title. Task 1 seeds the missiles from the
-- title's time, so the game's timeline depends on SG_BEGIN: at the default
-- 600 window GAME OVER is at fc 17525 (the model derivation; 6509 before
-- Task 1), so the A press is keyed on game_over itself, not a frame.
local function drive(fc)
    if not SG.game_started(fc) then     -- the title: no input of our own
        return
    end
    local go = sp:read_u8(rules_addr + 82)  -- rules.game_over (the m68k layout)
    local restart = go_restart_at(fc, go)
    if not restart then                     -- game 1: Up only (never C)
        hold("P1 Up", true)
        hold("P1 A", false)
        hold("P1 Right", false)
    elseif fc < restart + 20 then           -- press A at GAME OVER + 71 (inside
                                            -- the 295-frame window): the new game
        hold("P1 Up", true)
        hold("P1 A", true)
        hold("P1 Right", false)
    elseif fc < restart + 40 then           -- release A, start turning right
        hold("P1 Up", true)
        hold("P1 A", false)
        hold("P1 Right", true)
    else                                    -- game 2: Right + A taps
        hold("P1 Up", false)
        hold("P1 A", (fc - (restart + 40)) % 20 == 0)
        hold("P1 Right", true)
    end
end

-- decode the 30 fix rows (0..29) and write them for tests/check_hud.py:
-- the icons are S ROM tiles 128/129, written as their raw bytes (a tile
-- > 0x7f cannot go into the ASCII stream: 128 and 129 are sent as chars,
-- which don't survive a UTF-8 assumptions — write the 2-digit codes for
-- every tile >= 0x80 and let the checker decode them)
local function row_tile(v)
    if v < 0x80 then return string.char(v) end
    return string.format("<%d>", v)
end

local function sample(fc)
    f:write(string.format("F %d\n", fc))
    if events_addr ~= 0 then
        f:write(string.format("E %d %d\n", fc, sp:read_u32(events_addr)))
    end
    for r = 0, 29 do
        local line = ""
        for c = 0, 39 do
            local tile = vread(FR + c * 32 + r) & 0x0fff
            line = line .. row_tile(tile)
        end
        f:write(string.format("R %d %s\n", r, line))
    end
end

-- the actual loop: this probe is driven from the frame notifier. The AES
-- BIOS preamble runs at low addresses (0x00c0xxxx); the cart's code lives at
-- 0x100000+, so "in cart space" means PC >= 0x100000.
local function tick()
    n = n + 1
    if in_cart == 0 and cpu.state["PC"].value >= 0x100000 then
        in_cart = 1
    end
    SG.sg_apply(n)
    if in_cart then
        rec = rec + 1
        local fc = framecnt()
        f:write(string.format("I %d %d %d %d\n", rec, fc, sp:read_u8(BI), sp:read_u8(CHG)))
        MS.poll(f, n, fc)
        drive(fc)                            -- input for the frames ahead
        -- sample on cart frames 60,80,...: compare each against the model
        if fc >= 60 and (fc - 60) % 20 == 0 then
            sample(fc)
        end
        if not snapped and fc >= 100 then
            machine.video:snapshot()
            f:write(string.format("SNAP %d\n", fc))
            snapped = true
        end
        -- the icon-cell proof (HUD-layout Task 2): snapshot right after
        -- the FIRST death of game 1 (the rules' lives byte reads 2: the
        -- deaths count down 3 -> 2 -> 1 -> 0). The rules' end-of-frame
        -- lives (read here) is shown by hud_frame THE SAME frame, but the
        -- MAME snapshot captures the frame buffer from the previous
        -- frame's composition (fix writes made later in THIS frame's tick
        -- are not in it), so the snapshot is taken on the NEXT tick, where
        -- the frame buffer holds the frame hud_frame drew with lives 2.
        -- The V record carries the lives read, so the checker knows which
        -- snapshot is which and can verify the death actually happened.
        if rules_addr ~= 0 and not death_snap_done then
            local lives = sp:read_u8(rules_addr + 78)
            if death_pending > 0 then
                death_pending = death_pending - 1
                if death_pending == 0 then
                    machine.video:snapshot()
                    f:write(string.format("V %d %d\n", fc, lives))
                    f:write(string.format("SNAP %d\n", fc))
                    death_snap_done = true
                end
            elseif fc >= 60 and lives == 2 then
                -- first death seen in the rules; the display lags the fix
                -- writes by ~4 MAME frames (measured: snapshots right at
                -- detection show 3 ships, +6 ticks show 2), and the lag
                -- varies a frame or two between runs, so wait 8: the
                -- lives stay 2 for the whole DEAD_FRAMES (118) countdown,
                -- well past the margin
                death_pending = 8
            end
        end
    end
    if n >= run_len then
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d\n", in_cart, n, rec))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__hud = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
