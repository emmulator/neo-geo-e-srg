-- gameover_draw_probe.lua: the M4-fixes Task 4 "dome stays gone" boot-test.
--
-- Drives the -DGAMEOVER_DRAW_TEST cart (a one-life test build of the normal
-- cart; its hook lives in src/main.c under that flag and mirrors this
-- script's policy — the two must stay in lockstep) through a two-phase
-- scripted game and proves, from VRAM, snapshots and the model:
--
--   Phase 1 (the dome-death GAME OVER): no input at all. Missiles break
--   the dome until the 38th cell and the one life means the dome death
--   (fc 8359 under Task 1's seed; 8202 before it) ends the game at fc 8477
--   (the model's frames). The probe
--   samples the dome slots' SCB3 words, the broken-overlay range, and the
--   fix rows through the GAME OVER and snapshots once. What must be true
--   the whole time:
--     * the fix layer says GAME OVER (row 7);
--     * every dome slot has SCB3 height 0 (the dome is gone);
--     * no broken-overlay slot is shown — the bug's whole-dome-with-38-
--       broken-cells reappears here;
--     * the snapshot's dome box has no dome pixels.
--
--   fc ~8537: press A -> a new game (the rules' new_game rebuilds a
--   fresh, whole dome). The probe dumps the dome slots just after (the
--   checker compares them against the fresh dump, fc 60 of the first
--   game) and checks no overlay is shown, and snapshots the fresh dome.
--
--   Phase 2 (a non-dome GAME OVER, the "keeps today's look" proof): the
--   hook seeds 13 broken cells (rings 0..4's top-facing half visible at
--   view 0) and parks the ship on the broken cell 5, so the ship dies a
--   CELL death (not the dome's) and the game ends at the model's frame.
--   Under that GAME OVER the dome must stay WHOLE and its real broken tiles
--   shown.
--
-- The hook/cart exports a BSS byte every main-loop frame (go_test_dbg,
-- read through go_test_addr): bit0 alive (the ship is alive and the game
-- on), bit1 saw_go (a GAME OVER has been reached), bit2 seeded (the
-- phase-2 hook has seeded). The probe records it with every input
-- read-back so the checker can align the samples to the model's frames.
--
-- Output:
--   I <rec> <fc> <cur> <chg> <flags>             every record (flags =
--                                                the go_test_dbg byte)
--   S <fc> <slot> <scb2> <scb3> <scb4> <attr> <tile0..tile7>  a SHOWN
--       slot's full state (dome or overlay)
--   D <fc> <w DOME_SPRITE..DOME_SPRITE+10>   the 11 dome slots' full SCB3 words
--   O <fc> <n>          the number of shown overlay slots
--   F <fc>              the fix rows follow (10 rows, decoded)
--   W <r> <40 chars>
--   FRESH <fc>          a fresh dome's slot dump follows (11 h lines)
--   h <...>             one slot line, same fields as S
--   SNAP <n> <fc>       snapshot n taken this frame
--   DONE <key> <fc>     an event was detected this frame
-- Env: OUT, FRAMES (MAME frames; the default 9500 covers the cart to fc
-- ~8589 + the ~477-frame BIOS preamble), GO_TEST_ADDR, GO_FRESH_ADDR (the
-- cart frame counter; 0 disables the exact alignment).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "9500")
local go_test_addr = tonumber(os.getenv("GO_TEST_ADDR") or "0")
local framecnt_addr = tonumber(os.getenv("GO_FRESH_ADDR") or "0")

local BI, CHG = 0x10fd96, 0x10fd97
local FR = 0x7000
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local DOME_SPRITE, DOME_COLS, DOME_ROWS = S.DOME_SPRITE, S.DOME_COUNT, 8
local OVERLAY_BASE, OVERLAY_AFTER = S.BROKEN_SLOT_BASE, S.BROKEN_SLOT_AFTER
local GO_ROW, GO_COL = 7, 15          -- 'GAME OVER' is centred, col 15..23
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

local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec
end

local function goflags()
    if go_test_addr ~= 0 then
        return sp:read_u8(go_test_addr)
    end
    return 0
end

-- is the GAME OVER text on the fix layer (row 7, cols 15..23)?
local function go_text()
    local want = "GAME OVER"
    local c
    for c = 1, #want do
        local tile = vread(FR + (GO_COL + c - 1) * 32 + GO_ROW) & 0x0fff
        if tile ~= string.byte(want, c, c) then
            return 0
        end
    end
    return 1
end

local f = assert(io.open(out, "w"))
local n, in_cart, rec = 0, 0, 0
local snap_n = 0
local p1_go, a_fc, p2_go = nil, nil, nil
local fresh_boot, fresh_new = false, false
local snap1, snap2, snap3 = false, false, false
local a_pressed = false

-- one slot's full line (SCB2/3/4, the attr word, SCB1 tiles 0..7)
local function slot_line(slot)
    local line = string.format("%d %04x %04x %04x %04x",
                               slot, vread(SCB2 + slot), vread(SCB3 + slot),
                               vread(SCB4 + slot), vread(SCB1 + slot * 64 + 1))
    for r = 0, DOME_ROWS - 1 do
        line = line .. string.format(" %04x", vread(SCB1 + slot * 64 + r * 2))
    end
    return line
end

-- the shown slots of a range, one S line each (tagged with fc)
local function dump_shown(fc, first, last)
    local s
    for s = first, last do
        if (vread(SCB3 + s) & 0x3f) ~= 0 then
            f:write(string.format("S %d %s\n", fc, slot_line(s)))
        end
    end
end

-- the 11 dome slots' full SCB3 words, one D line
local function dome_words(fc)
    local c
    local line = string.format("D %d", fc)
    for c = 0, DOME_COLS - 1 do
        line = line .. string.format(" %04x", vread(SCB3 + DOME_SPRITE + c))
    end
    f:write(line .. "\n")
end

-- the number of shown overlay slots
local function overlay_count()
    local s, count = OVERLAY_BASE, 0
    for s = OVERLAY_BASE, OVERLAY_AFTER - 1 do
        if (vread(SCB3 + s) & 0x3f) ~= 0 then
            count = count + 1
        end
    end
    return count
end

-- the fix rows 0..9, decoded
local function dump_fix(fc)
    local r, c
    f:write(string.format("F %d\n", fc))
    for r = 0, 9 do
        local line = ""
        for c = 0, 39 do
            local tile = vread(FR + c * 32 + r) & 0x0fff
            if tile > 0xff then line = line .. "?" else line = line .. string.char(tile) end
        end
        f:write(string.format("W %d %s\n", r, line))
    end
end

-- a fresh dome dump: the 11 dome slots regardless of shown state
local function dump_fresh(fc)
    local c
    f:write(string.format("FRESH %d\n", fc))
    for c = 0, DOME_COLS - 1 do
        f:write(string.format("h %s\n", slot_line(DOME_SPRITE + c)))
    end
end

local function snapshot(fc)
    snap_n = snap_n + 1
    machine.video:snapshot()
    f:write(string.format("SNAP %d %d\n", snap_n, fc))
end

-- the input policy, keyed on the cart frame (applied at the frame's end so
-- the next frame sees it — the recorded read-backs are ground truth): one
-- A press 60 frames after the phase-1 GAME OVER starts a new game; then
-- nothing.
local function drive(fc)
    if not SG.game_started(fc) then     -- the title: no input of our own
        joy.fields["P1 A"]:set_value(0)
        return
    end
    local press = (p1_go ~= nil and not a_pressed and fc >= p1_go + 59
                   and fc <= p1_go + 62)
    if press then
        a_pressed = true
        a_fc = p1_go + 60
    end
    joy.fields["P1 A"]:set_value(press and 1 or 0)
end

local function tick()
    n = n + 1
    if in_cart == 0 and cpu.state["PC"].value >= 0x100000 then
        in_cart = 1
    end
    SG.sg_apply(n)
    if in_cart then
        rec = rec + 1
        local fc = framecnt()
        local g = goflags()
        f:write(string.format("I %d %d %d %d %d\n", rec, fc, sp:read_u8(BI),
                              sp:read_u8(CHG), g))
        MS.poll(f, n, fc)
        drive(fc)
        local sawgo, seeded = (g >> 1) & 1, (g >> 2) & 1

        -- phase 1: the GAME OVER from the dome death. Once the text is on
        -- the fix layer, sample through to just before the A press.
        if p1_go == nil and fc >= 8253 and go_text() == 1 then
            p1_go = fc
            f:write(string.format("DONE p1_go=%d\n", fc))
        end
        if p1_go ~= nil and not a_pressed then
            if fc <= p1_go + 58 and (fc - p1_go) % 12 == 0 then
                dome_words(fc)
                f:write(string.format("O %d %d\n", fc, overlay_count()))
                dump_shown(fc, OVERLAY_BASE, OVERLAY_AFTER - 1)
                dump_fix(fc)
            end
            if not snap1 and fc >= p1_go + 4 then
                snapshot(fc)
                f:write(string.format("O %d %d\n", fc, overlay_count()))
                snap1 = true
            end
        end
        -- the fresh dome at the start of the FIRST game (the reference)
        if fc == 60 and not fresh_boot then
            dump_fresh(fc)
            f:write(string.format("O %d %d\n", fc, overlay_count()))
            fresh_boot = true
        end
        -- the fresh dome just after the A press (the new game's dome)
        if a_fc ~= nil and not fresh_new and fc >= a_fc + 1 and fc <= a_fc + 8 then
            dump_fresh(fc)
            f:write(string.format("O %d %d\n", fc, overlay_count()))
            if not snap2 then
                snapshot(fc)
                snap2 = true
            end
            fresh_new = true
        end
        -- phase 2: after the hook seeded, the GAME OVER from the cell death
        if p2_go == nil and seeded == 1 and fc >= 8477 and go_text() == 1 then
            p2_go = fc
            f:write(string.format("DONE p2_go=%d\n", fc))
        end
        if p2_go ~= nil then
            if fc <= p2_go + 84 and (fc - p2_go) % 12 == 0 then
                dome_words(fc)
                f:write(string.format("O %d %d\n", fc, overlay_count()))
                dump_shown(fc, OVERLAY_BASE, OVERLAY_AFTER - 1)
                dump_fix(fc)
            end
            if not snap3 and fc >= p2_go + 4 then
                snapshot(fc)
                snap3 = true
            end
        end
    end
    -- key the phase-2 exit on the game-session frame (fc), NOT on rec: the
    -- cart now spends ~600 MAME frames on the title before Start, so rec
    -- has shifted ahead of fc by that constant and rec already exceeds
    -- p2_go + 477 the moment p2_go is seen. The phase-2 samples run to
    -- fc p2_go + 84 and snap3 lands at p2_go + 4, so exit 1 fc after the
    -- sampling window (each fc ticks once per game-session frame).
    if n >= run_len or (p2_go ~= nil and fc >= p2_go + 85) then
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d p1=%s a=%s p2=%s "
                              .. "fresh=%d%d snaps=%d\n",
                              in_cart, n, rec, tostring(p1_go or 0),
                              tostring(a_fc or 0), tostring(p2_go or 0),
                              fresh_boot and 1 or 0, fresh_new and 1 or 0, snap_n))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__gameover_draw = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
