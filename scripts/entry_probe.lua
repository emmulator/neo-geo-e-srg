-- entry_probe.lua: the high-score boards Task B6 entry-screen boot-test.
--
-- Runs one of two scripted games on the AES NORMAL cart:
--   ENTRY_CASE=lives: the aiming game (Left held, A only when a missile is
--     aligned with the ship's cell) until the score qualifies, then Up held
--     to a lives-out GAME OVER over the whole dome.
--   ENTRY_CASE=ruin: the same aiming game until the score qualifies, then
--     no input to the dome death whose collapse leaves the ruin.
-- After GAME OVER it waits the 118 GAME OVER frames, then drives the entry
-- screen: A (first initial), Right held through a full circle (the target
-- passes every ring position, so the ruin and its plumes are seen at every
-- angle the leg reaches) back to B (second), a held Left round to ERASE
-- (erase the second), a held Right back to A (third), Right to B (fourth, the
-- third stored → the auto-jump to END), and A at END. The expected initials
-- are therefore A A B:  A, B, erase B, A, B.
--
-- Records (all addresses from nm, like flow_probe):
--   I <n> <fc> <cur> <chg>                  every frame's BIOS input
--   GO <n> <fc> <level> <base> <score10>    the GAME OVER frame (the entry's
--                                           base dome angle and the score)
--   E <n> <entry_fc> <phase> <target> <ninit> <init0> <init1> <init2>
--     <hold> <dir> <done> <sfx> <fly_t> <fly_k> <cur> <chg> every entry
--                                           frame: entry_state after the
--                                           previous frame (sfx and K2's
--                                           flight fields included), and the
--                                           input that produced it
--   SND <n> <entry_fc> <cmd...>             every REG_SOUND write the cart
--                                           made during that entry frame
--                                           (the tap, like sound_probe.lua)
--   ANG <n> <entry_fc> <angle>              ship.dome_angle, every entry frame
--   R <n> <j> <scb1> <scb2> <scb3> <scb4>   every ring slot (j 0..37) every
--                                           entry frame
--   FLY <n> <entry_fc> <tile> <attr> <scb2> <scb3> <scb4>
--                                           K2: the FLY_SPRITE slot's words
--                                           every entry frame
--   CEN <entry_fc> <count> <line>           the sprites-per-scanline worst line
--                                           every entry frame
--   EF <n> <entry_fc> + EW <row> <40 chars> the entry fix rows 7..2 (descending)
--                                           every entry frame
--   B <n> <fc> <b0> <b1> <b2> <126 hex>     flow_board (before the entry, after
--                                           END, and on the returned title)
--   CARD <n> <fc> <cmd:ans,...>             card_log, every entry frame
--   T <n> <fc> <page> <t> <cred>            the returned title's state
--   F/W ...                                 the returned title's 30 fix rows
--   W <worst_fc> <count> <line> + w <slot> <scb3>
--                                           the worst entry census's raw dump
--   SNAP <n> <fc>                           one snapshot at GAME OVER
--   EXIT <n> <fc> <mod1>
--   pc_in_cart=1 ...
--
-- Env: OUT, FRAMES, REPO, ENTRY_CASE, FLOW_STATE_ADDR, ENTRY_STATE_ADDR,
-- ENTRY_FC_ADDR, FLOW_SHIP_ADDR, FLOW_MIS_ADDR, FLOW_RULES_ADDR,
-- FLOW_BEST_ADDR, FLOW_LEVEL_ADDR, FLOW_CARDLOG_ADDR, FLOW_PAGE_ADDR,
-- FLOW_T_ADDR, FLOW_CELL_RING_ADDR, FLOW_CELL_PHI_ADDR, TITLE_SEED_ADDR,
-- SG_* (the Start window).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "32000")
local case = os.getenv("ENTRY_CASE") or "lives"
local flow_addr = tonumber(os.getenv("FLOW_STATE_ADDR") or "0")
local entry_addr = tonumber(os.getenv("ENTRY_STATE_ADDR") or "0")
local entry_fc_addr = tonumber(os.getenv("ENTRY_FC_ADDR") or "0")
local ship_addr = tonumber(os.getenv("FLOW_SHIP_ADDR") or "0")
local mis_addr = tonumber(os.getenv("FLOW_MIS_ADDR") or "0")
local rules_addr = tonumber(os.getenv("FLOW_RULES_ADDR") or "0")
local best_addr = tonumber(os.getenv("FLOW_BEST_ADDR") or "0")
local level_addr = tonumber(os.getenv("FLOW_LEVEL_ADDR") or "0")
local cardlog_addr = tonumber(os.getenv("FLOW_CARDLOG_ADDR") or "0")
local page_addr = tonumber(os.getenv("FLOW_PAGE_ADDR") or "0")
local t_addr = tonumber(os.getenv("FLOW_T_ADDR") or "0")
local cell_ring_addr = tonumber(os.getenv("FLOW_CELL_RING_ADDR") or "0")
local cell_phi_addr = tonumber(os.getenv("FLOW_CELL_PHI_ADDR") or "0")

-- K1: every 68k REG_SOUND write is queued here; tick() takes the queue once
-- per frame, so the writes made during the frame that just ran are labelled
-- with the same n as that frame's entry_state read. A non-entry frame's
-- queue is simply dropped.
local sound_pending = {}
local function on_sound(offset, data, mask)
    sound_pending[#sound_pending + 1] = data & 0xff
    return data
end
_G.__entry_sound_tap = sp:install_write_tap(0x320000, 0x320001, "sound",
                                            on_sound)

local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")
local BI, CHG = 0x10fd96, 0x10fd97
local MOD1 = 0x10fdb6
local FR = 0x7000
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local RING_SPRITE, RING_COUNT = S.RING_SPRITE, S.RING_COUNT
local FLY_SPRITE = S.FLY_SPRITE
local DOME0, DOME_COLS = S.DOME_SPRITE, S.DOME_COUNT
local SMOKE_BACK_SPRITE, SMOKE_BACK_COUNT = S.SMOKE_BACK_SPRITE,
    S.SMOKE_BACK_COUNT
local SMOKE_SPRITE, SMOKE_COUNT = S.COLLAPSE_SMOKE_SPRITE, S.COLLAPSE_SMOKE_COUNT
local SMOKE_TOTAL = SMOKE_BACK_COUNT + SMOKE_COUNT
local SMOKE_ROWS = 7
local RUIN_ROWS = 5
local joy = machine.ioport.ports[":ctrl1:joy:JOY"]

local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(a) return vram:read(a) end
local function hold(name, on)
    if joy and joy.fields[name] then joy.fields[name]:set_value(on and 1 or 0) end
end
local function release_all()
    hold("P1 Left", false)
    hold("P1 Up", false)
    hold("P1 Right", false)
    hold("P1 Down", false)
    hold("P1 A", false)
end

local f = assert(io.open(out, "w"))
local n, in_cart, rec = 0, 0, 0
local fc = 0
local p1_go = nil
local base_angle = 0
local snap_taken = false
local entry_snap = false
local entry_started = false
local entry_done = false
local entry_samples = 0
local title_samples = 0
local title_next = 0

-- the game's deterministic policies --------------------------------------
local framecnt_addr = tonumber(os.getenv("FLOW_FRAMECNT_ADDR") or "0")
local function cart_fc()
    if framecnt_addr ~= 0 then return sp:read_u32(framecnt_addr) end
    return rec
end
local function rules_over()
    return rules_addr ~= 0 and sp:read_u8(rules_addr + 82) ~= 0
end
local function aim_fire()
    if ship_addr == 0 or cell_ring_addr == 0 or cell_phi_addr == 0
       or mis_addr == 0 then
        return false
    end
    local cell = sp:read_u8(ship_addr + 2)
    local r = sp:read_u8(cell_ring_addr + cell)
    local phi = sp:read_u8(cell_phi_addr + cell)
    local i
    for i = 0, 2 do
        local o = mis_addr + i * 14
        if sp:read_u8(o) == 1 and sp:read_u8(o + 1) == 0
           and sp:read_u8(o + 2) == r and sp:read_u8(o + 3) == phi then
            return true
        end
    end
    return false
end

-- the entry's scripted input ---------------------------------------------
-- 0: A (first initial), 1: Right -> B, 2: A (second initial),
-- 3: hold Left to ERASE, 4: A (erase), 5: hold Right to A,
-- 6: A (A again), 7: Right -> B, 8: A (third initial, auto-jump),
-- 9: A at END.
local step = 0
local first_turn_moved = false
local first_turn_wrapped = false
local function at_rest(e)
    return e.phase == e.target and (e.phase % 6) == 0
end
local function entry_state()
    return {
        phase = sp:read_u8(entry_addr + 0),
        target = sp:read_u8(entry_addr + 1),
        ninit = sp:read_u8(entry_addr + 2),
        init0 = sp:read_u8(entry_addr + 3),
        init1 = sp:read_u8(entry_addr + 4),
        init2 = sp:read_u8(entry_addr + 5),
        hold = sp:read_u8(entry_addr + 6),
        dir = sp:read_u8(entry_addr + 7),
        done = sp:read_u8(entry_addr + 8),
        sfx = sp:read_u8(entry_addr + 9),
        fly_t = sp:read_u8(entry_addr + 10),
        fly_k = sp:read_u8(entry_addr + 11),
    }
end
local function entry_drive()
    local e = entry_state()
    if e.done ~= 0 then return end
    if step == 0 then
        if at_rest(e) and e.phase == 0 and e.ninit == 0 then
            hold("P1 A", true); step = 1
        end
    elseif step == 1 then
        hold("P1 A", false)
        if e.ninit == 1 and at_rest(e) and e.phase == 0 then
            hold("P1 Right", true); step = 2
        end
    elseif step == 2 then
        -- Task V2: keep the Right turn held through a full circle: the
        -- target passes every position (36, ..., 0) and comes back to B
        -- (position 1, phase 6). Only then release and press A as today.
        if e.target ~= 0 then first_turn_moved = true end
        if first_turn_moved and e.target == 0 then first_turn_wrapped = true end
        if first_turn_wrapped and e.target == 6
           and at_rest(e) and e.phase == 6 then
            hold("P1 Right", false)
            hold("P1 A", true)
            step = 3
        end
    elseif step == 3 then
        hold("P1 A", false)
        if e.ninit == 2 then
            hold("P1 Left", true)
            -- the ring still turns after the second initial; hold the left
            -- turn until the target reaches ERASE (position 35, phase 210).
            if e.target == 210 then
                hold("P1 Left", false); step = 4
            end
        end
    elseif step == 4 then
        if e.ninit == 2 and at_rest(e) and e.phase == 210 then
            hold("P1 A", true); step = 5
        end
    elseif step == 5 then
        hold("P1 A", false)
        if e.ninit == 1 then
            hold("P1 Right", true)
            if e.target == 0 then
                hold("P1 Right", false); step = 6
            end
        end
    elseif step == 6 then
        if e.ninit == 1 and at_rest(e) and e.phase == 0 then
            hold("P1 A", true); step = 7
        end
    elseif step == 7 then
        hold("P1 A", false)
        if e.ninit == 2 and at_rest(e) and e.phase == 0 then
            hold("P1 Right", true); step = 8
        end
    elseif step == 8 then
        hold("P1 Right", false)
        if e.ninit == 2 and at_rest(e) and e.phase == 6 then
            hold("P1 A", true); step = 9
        end
    elseif step == 9 then
        hold("P1 A", false)
        if e.ninit == 3 and at_rest(e) and e.phase == 216 then
            hold("P1 A", true); step = 10
        end
    elseif step == 10 then
        hold("P1 A", false)
    end
end

-- VRAM/fix/board/card sampling -------------------------------------------
local function read_row_text(row)
    local line = ""
    local c
    for c = 0, 39 do
        local tile = vread(FR + c * 32 + row) & 0x0fff
        if tile >= 0x80 then
            line = line .. string.format("<%d>", tile)
        else
            line = line .. string.char(tile)
        end
    end
    return line
end

local function dump_entry_fix(nn, efc)
    local row
    f:write(string.format("EF %d %d\n", nn, efc))
    -- descending: a text row can corrupt rows read after it, so read 8
    -- first (the entry owns rows 2..7; row 8 is GAME OVER's Task G1 cap
    -- row and must be blank from the entry's first frame).
    for row = 8, 2, -1 do
        f:write(string.format("EW %d %s\n", row, read_row_text(row)))
    end
end

local function dump_fix(nn, fcv)
    local row
    f:write(string.format("F %d %d\n", nn, fcv))
    for row = 0, 2 do
        f:write(string.format("W %d %s\n", row, read_row_text(row)))
    end
    f:write(string.format("W 3 %s\n", read_row_text(3)))
    for row = 4, 8 do
        f:write(string.format("W %d %s\n", row, read_row_text(row)))
    end
    f:write(string.format("W 9 %s\n", read_row_text(9)))
    for row = 10, 23 do
        f:write(string.format("W %d %s\n", row, read_row_text(row)))
    end
    for row = 29, 24, -1 do
        f:write(string.format("W %d %s\n", row, read_row_text(row)))
    end
end

local function best_rec(nn, fcv)
    if best_addr == 0 then return end
    local hex = {}
    local i
    for i = 0, 125 do
        hex[#hex + 1] = string.format("%02x", sp:read_u8(best_addr + i))
    end
    f:write(string.format("B %d %d %d %d %d %s\n", nn, fcv,
                          sp:read_u32(best_addr + 8),
                          sp:read_u32(best_addr + 48),
                          sp:read_u32(best_addr + 88),
                          table.concat(hex)))
end

local function cardlog_rec(nn, fcv)
    if cardlog_addr == 0 then return end
    local pairs = {}
    local i
    for i = 0, 6, 2 do
        local cmd = sp:read_u16(cardlog_addr + i * 2)
        local ans = sp:read_u16(cardlog_addr + (i + 1) * 2)
        if cmd == 0xffff then break end
        pairs[#pairs + 1] = string.format("%x:%x", cmd, ans)
    end
    f:write(string.format("CARD %d %d %s\n", nn, fcv, table.concat(pairs, ",")))
end

local function ring_slots(nn, j)
    local s = RING_SPRITE + j
    f:write(string.format("R %d %d %04x %04x %04x %04x %04x\n", nn, j,
                          vread(SCB1 + s * 64), vread(SCB1 + s * 64 + 1),
                          vread(SCB2 + s), vread(SCB3 + s), vread(SCB4 + s)))
end

-- K2: the flying letter's one slot, every entry frame.
local function fly_slots(nn, efc)
    f:write(string.format("FLY %d %d %04x %04x %04x %04x %04x\n", nn, efc,
                          vread(SCB1 + FLY_SPRITE * 64),
                          vread(SCB1 + FLY_SPRITE * 64 + 1),
                          vread(SCB2 + FLY_SPRITE), vread(SCB3 + FLY_SPRITE),
                          vread(SCB4 + FLY_SPRITE)))
end

-- Task V1/V2: the dome columns' SCB4 box chain, their SCB3 chain words (the
-- ruin's driver one row shorter, RUIN_TOP px down the box) and their SCB1 rows
-- 0..RUIN_ROWS-1 (the ruin view the scene angle selects), every entry frame.
local function dump_entry_ruin(efc)
    local c, r
    local line = string.format("U %d", efc)
    for c = 0, DOME_COLS - 1 do
        line = line .. string.format(" %04x %04x",
            vread(SCB4 + DOME0 + c), vread(SCB3 + DOME0 + c))
        for r = 0, RUIN_ROWS - 1 do
            line = line .. string.format(" %04x %04x",
                vread(SCB1 + (DOME0 + c) * 64 + r * 2),
                vread(SCB1 + (DOME0 + c) * 64 + r * 2 + 1))
        end
    end
    f:write(line .. "\n")
end

-- Task V1: the twelve plume columns' words (SCB2/3/4 and SCB1 rows 0..6),
-- every entry frame. The six BACK slots sit below DOME0, the six FRONT slots
-- in the overlay range.
local function dump_entry_smoke(efc)
    local i, r, slot
    for i = 0, SMOKE_TOTAL - 1 do
        if i >= SMOKE_BACK_COUNT then
            slot = SMOKE_SPRITE + i - SMOKE_BACK_COUNT
        else
            slot = SMOKE_BACK_SPRITE + i
        end
        local line = string.format("SM %d %d %04x %04x %04x", efc, slot,
            vread(SCB2 + slot), vread(SCB3 + slot), vread(SCB4 + slot))
        for r = 0, SMOKE_ROWS - 1 do
            line = line .. string.format(" %04x %04x",
                vread(SCB1 + slot * 64 + r * 2),
                vread(SCB1 + slot * 64 + r * 2 + 1))
        end
        f:write(line .. "\n")
    end
end

local worst_count, worst_line, worst_fc, worst_raw = 0, -1, 0, nil
local function scan()
    local rows = {}
    local raw = {}
    local prev_top, prev_h = 0, 0
    for s = 0, 380 do
        local scb3 = vread(SCB3 + s)
        local h = scb3 & 0x3f
        local top
        if (scb3 & 0x40) ~= 0 then
            top, h = prev_top, prev_h
        else
            top = 496 - (scb3 >> 7)
        end
        prev_top, prev_h = top, h
        if h > 0 then
            local y0 = math.max(0, top)
            local y1 = math.min(223, top + h * 16 - 1)
            for y = y0, y1 do
                rows[y] = (rows[y] or 0) + 1
            end
        end
        raw[s] = scb3
    end
    local best, bestline = 0, -1
    for y = 0, 223 do
        local c = rows[y] or 0
        if c > best then best, bestline = c, y end
    end
    return best, bestline, raw
end

local function title_state()
    local page = page_addr ~= 0 and sp:read_u8(page_addr) or -1
    local t = t_addr ~= 0 and sp:read_u16(t_addr) or -1
    return page, t
end

local function tick()
    n = n + 1
    local pending = sound_pending
    sound_pending = {}
    local bi = sp:read_u8(BI)
    local chg = sp:read_u8(CHG)
    if in_cart == 0 and cpu.state["PC"].value >= 0x100000 then
        in_cart = 1
    end
    fc = cart_fc()
    SG.sg_apply(n)
    if in_cart then
        local fl = flow_addr ~= 0 and sp:read_u32(flow_addr) or 0
        if fc >= 1 and not entry_started then
            if not entry_done then
                if not rules_over() then
                    -- the game's scripted policy
                    if case == "lives" then
                        -- score with the aiming game, then (once the board
                        -- qualifies) hold Up: the Up-held game's lives-out
                        -- death comes well before the centred collapse, so
                        -- the backdrop stays the whole dome.
                        local sc10 = mis_addr ~= 0
                            and sp:read_u32(mis_addr + 76) or 0
                        if sc10 < 1100 then
                            hold("P1 Left", true)
                            hold("P1 Up", false)
                            hold("P1 Right", false)
                            hold("P1 Down", false)
                            hold("P1 A", aim_fire())
                        else
                            release_all()
                            hold("P1 Up", true)
                        end
                    else
                        -- the ruin run: score with the aim game until the
                        -- board qualifies (score10 >= 1100), then stop
                        -- firing and let the dome collapse (the centred
                        -- policy's ruin death). The score is kept.
                        local sc10 = mis_addr ~= 0
                            and sp:read_u32(mis_addr + 76) or 0
                        if sc10 < 1100 then
                            hold("P1 Left", true)
                            hold("P1 Up", false)
                            hold("P1 Right", false)
                            hold("P1 Down", false)
                            hold("P1 A", aim_fire())
                        else
                            release_all()
                        end
                    end
                else
                    release_all()
                    if p1_go == nil then
                        p1_go = fc
                        base_angle = ship_addr ~= 0 and sp:read_u8(ship_addr) or 0
                        local lvl = rules_addr ~= 0 and sp:read_u8(rules_addr) or 1
                        local sc10 = mis_addr ~= 0 and sp:read_u32(mis_addr + 76) or 0
                        f:write(string.format("GO %d %d %d %d %d\n", n, fc,
                                              lvl, base_angle, sc10))
                        local dome_pal = vread(SCB1 + DOME0 * 64 + 1) >> 8
                        f:write(string.format("RUIN %d %d %d\n", n, fc,
                                              dome_pal))
                        if rules_addr ~= 0 then
                            f:write(string.format("RULE %d %d %d %d %d\n",
                                                  n, fc,
                                                  sp:read_u8(rules_addr + 78),
                                                  sp:read_u8(rules_addr + 81),
                                                  sp:read_u8(rules_addr + 82)))
                        end
                        best_rec(n, fc)
                        cardlog_rec(n, fc)
                        if not snap_taken then
                            machine.video:snapshot()
                            f:write(string.format("SNAP %d %d\n", n, fc))
                            snap_taken = true
                        end
                    end
                end
                if p1_go ~= nil and fl == 3 then
                    entry_started = true
                    -- fall through to the entry branch this frame
                end
            end
        end
        if entry_started and not entry_done and fl == 3 then
            entry_samples = entry_samples + 1
            local e = entry_state()
            local efc = entry_fc_addr ~= 0 and sp:read_u16(entry_fc_addr) or entry_samples
            f:write(string.format(
                "E %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                n, efc, e.phase, e.target, e.ninit, e.init0, e.init1,
                e.init2, e.hold, e.dir, e.done, e.sfx, e.fly_t, e.fly_k,
                bi, chg))
            f:write(string.format("SND %d %d%s\n", n, efc,
                                  #pending > 0
                                  and " " .. table.concat(pending, " ") or ""))
            local ang = ship_addr ~= 0 and sp:read_u8(ship_addr) or 0
            f:write(string.format("ANG %d %d %d\n", n, efc, ang))
            dump_entry_ruin(efc)
            dump_entry_smoke(efc)
            local j
            for j = 0, RING_COUNT - 1 do ring_slots(n, j) end
            fly_slots(n, efc)
            if efc == 6 and not entry_snap then
                entry_snap = true
                machine.video:snapshot()
                f:write(string.format("ESNAP %d %d\n", n, efc))
                local s
                for s = 0, 380 do
                    f:write(string.format("X %d %d %04x %04x\n", n, s,
                        vread(SCB3 + s), vread(SCB4 + s)))
                end
            end
            dump_entry_fix(n, efc)
            local c, line, raw = scan()
            f:write(string.format("CEN %d %d %d\n", efc, c, line))
            if c > worst_count then
                worst_count, worst_line, worst_fc, worst_raw = c, line, efc, raw
            end
            best_rec(n, fc)
            cardlog_rec(n, fc)
            if e.done ~= 0 then
                entry_done = true
            else
                entry_drive()
            end
        elseif entry_started and entry_done and fl == 0 and fc == 0 then
            if title_next == 0 then title_next = n end
            if n >= title_next and title_samples < 40 then
                local page, t = title_state()
                -- sample every 2 frames, hidden blink phases included: the
                -- checker proves the row goes blank on the (t >> 4) & 1
                -- phases and comes back on the others.
                dump_fix(n, 0)
                best_rec(n, 0)
                cardlog_rec(n, 0)
                f:write(string.format("T %d 0 %d %d 0\n", n, page, t))
                title_samples = title_samples + 1
                title_next = n + 2
            end
        elseif entry_started then
            release_all()
            if entry_done then
                -- the END save's card calls span frames: keep sampling the
                -- log until the return's .data reset.
                cardlog_rec(n, fc)
            end
        end
    end
    if in_cart then
        rec = rec + 1
        f:write(string.format("I %d %d %d %d\n", n, fc, bi, chg))
    end
    if n >= run_len or title_samples >= 40 then
        if worst_raw then
            f:write(string.format("W %d %d %d\n", worst_fc, worst_count,
                                  worst_line))
            local s
            for s = 0, 380 do
                f:write(string.format("w %d %04x\n", s, worst_raw[s]))
            end
        end
        f:write(string.format("EXIT %d %d %d\n", n, fc,
                              sp:read_u8(MOD1)))
        f:write(string.format(
            "pc_in_cart=%d frames=%d rec=%d go=%s entry=%d done=%d\n",
            in_cart, n, rec, tostring(p1_go or 0),
            entry_started and 1 or 0, entry_done and 1 or 0))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__entry = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
