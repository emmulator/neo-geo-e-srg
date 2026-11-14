-- demo_probe.lua: the attract mode's self-playing game boot-test (Attract
-- Task A3).
--
-- Two runs, chosen by DEMO_MODE:
--   cycle  no Start: the title runs the demo for three full restarts (the
--          first entry's page 0 is 3242 frames because title_t starts at 2,
--          then two full 3245-frame cycles), a B press restarts it again
--          from the script's first frame, and a census/framemark measurement
--          covers one whole cycle.
--   start  at the demo's first jump over a crack (DEMO_START_DFC, set by
--          boot_test.sh from build/demo.json) the probe presses Start; the
--          game begins fresh, plays itself (no input) to GAME OVER, and the
--          returned title restarts the demo at frame 0.
--
-- Every cart title frame while the demo runs writes one D line with the
-- cart's rules / ship / missiles / radar state, its script frame and the
-- restart's ordinal. The checker replays build/demo_map.h through
-- tests/hud_model.frame_model (with DEMO_SEED) and compares every field.
--
-- Output:
--   D <mame_n> <epoch> <demo_fc> <page> <title_t> <level_valid> <level>
--     <rules.level> <rules.nbroken> <rules.lives> <rules.integ>
--     <rules.dead_t> <rules.dome_dead> <rules.game_over>
--     <ship.angle> <ship.lat> <ship.cell> <ship.move_left> <ship.lift>
--     <ship.jumped> <ship.broken: 10 bytes hex>
--     <mis.rng> <mis.timer> <mis.level> <mis.kills> <mis.dome_hits>
--     <mis.score10> <mis.fire_req> <mis.sfx>
--     <radar.lock_t> <radar.locked>
--     then 3 x (state kind ring phi life r dr)
--     <cart frame hash> <props_dbg_last_angle>
--   G <mame_n> <fc> <title_seed_t> <mis_seed_used> and the same state fields
--   T <mame_n> <epoch> <demo_fc> <title_seed_t>   at the Start press
--   B <mame_n> <epoch> <demo_fc> <126 hex bytes>  flow_board at a restart
--   GO <mame_n> <fc>                              GAME OVER first seen
--   C <mame_n> <epoch> <demo_fc> <worst> <line>   the sprite census
--   M <mame_n> <epoch> <demo_fc> <end> <max> <min> <start>  framemark
--   P <mame_n> <epoch> <demo_fc> <page> <title_t> <aes_on> <toggles>
--     the AES demo-sound toggle state (softdip_dbg_aes_on / _toggles)
--   F <mame_n> <epoch> <demo_fc> <page> <title_t> <row 21, 40 hex bytes>
--     whenever fix row 21 changes (the confirmation / prompt)
--   S <mame_n> <epoch> <demo_fc> <cmd>   a REG_SOUND write (cmd 4..9)
--   SNAP <mame_n> <epoch> <demo_fc>
--   EXIT ...
--
-- Env: OUT, FRAMES, DEMO_MODE, DEMO_EPOCH_ADDR, DEMO_FC_ADDR,
-- DEMO_FRAMECNT_ADDR, DEMO_RULES_ADDR, DEMO_SHIP_ADDR, DEMO_MIS_ADDR,
-- DEMO_RADAR_ADDR, DEMO_TITLE_SEED_ADDR, DEMO_BEST_ADDR, MIS_SEED_ADDR,
-- DEMO_PAGE_ADDR, DEMO_T_ADDR, DEMO_LEVEL_ADDR, WORK_START_ADDR,
-- WORK_END_ADDR, WORK_MAX_ADDR, WORK_MIN_ADDR, CENSUS_EVERY,
-- DEMO_AES_ON_ADDR, DEMO_TOGGLES_ADDR (the AES toggle state),
-- DEMO_START_DFC (the start run's press frame) and PROPS_ANGLE_ADDR
-- (src/props.c's props_dbg_last_angle, proof P2).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local mode = os.getenv("DEMO_MODE") or "cycle"
local run_len = tonumber(os.getenv("FRAMES") or "9000")
local census_every = tonumber(os.getenv("CENSUS_EVERY") or "10")

local EPOCH = tonumber(os.getenv("DEMO_EPOCH_ADDR") or "0")
local DEMOFC = tonumber(os.getenv("DEMO_FC_ADDR") or "0")
local FRAMECNT = tonumber(os.getenv("DEMO_FRAMECNT_ADDR") or "0")
local RULES = tonumber(os.getenv("DEMO_RULES_ADDR") or "0")
local SHIP = tonumber(os.getenv("DEMO_SHIP_ADDR") or "0")
local MIS = tonumber(os.getenv("DEMO_MIS_ADDR") or "0")
local RADAR = tonumber(os.getenv("DEMO_RADAR_ADDR") or "0")
local TSEED = tonumber(os.getenv("DEMO_TITLE_SEED_ADDR") or "0")
local BEST = tonumber(os.getenv("DEMO_BEST_ADDR") or "0")
local MISSEED = tonumber(os.getenv("MIS_SEED_ADDR") or "0")
local PAGE = tonumber(os.getenv("DEMO_PAGE_ADDR") or "0")
local TT = tonumber(os.getenv("DEMO_T_ADDR") or "0")
local LEVEL = tonumber(os.getenv("DEMO_LEVEL_ADDR") or "0")
local HEPOCH = tonumber(os.getenv("DEMO_HASH_EPOCH_ADDR") or "0")
local HDONE = tonumber(os.getenv("DEMO_HASH_DONE_ADDR") or "0")
local HCUR = tonumber(os.getenv("DEMO_HASH_ADDR") or "0")
local HFC = tonumber(os.getenv("DEMO_HASH_FC_ADDR") or "0")
local WSTART = tonumber(os.getenv("WORK_START_ADDR") or "0")
local WEND = tonumber(os.getenv("WORK_END_ADDR") or "0")
local WMAX = tonumber(os.getenv("WORK_MAX_ADDR") or "0")
local WMIN = tonumber(os.getenv("WORK_MIN_ADDR") or "0")
local AES_ON = tonumber(os.getenv("DEMO_AES_ON_ADDR") or "0")
local TOGGLES = tonumber(os.getenv("DEMO_TOGGLES_ADDR") or "0")
local START_DFC = tonumber(os.getenv("DEMO_START_DFC") or "0")
local PROPS_ANGLE = tonumber(os.getenv("PROPS_ANGLE_ADDR") or "0")

local BI, CHG = 0x10fd96, 0x10fd97
local USER_MODE = 0x10fdaf
local SCB3 = 0x8200
local PAL_BASE = 0x400000

local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(a)
    return vram:read(a)
end

-- Attract D1 / high-score boards Task B4: fix row 21 as text. The title's
-- text tiles are TITLE2_ROW_BASE + title2_idx[char] * TITLE2_NPROF +
-- title2_rprof[left] (build/title_font.h); the character is recovered from
-- the tile's index block.
local FIXMAP = 0x7000
local TITLE2_ROW_BASE = 512
local TITLE2_NPROF = 21
-- tools/generate_srom.py's TITLE2_CHARS in tile-index order: star, heart,
-- space, the FONT57 punctuation/digits/letters and '_'.
local TITLE2_CHARS = "\1\2 !%&'()+,-./0123456789:<=>?ABCDEFGHIJKLMNOPQRSTUVWXYZ_"

local function row_text(row)
    local s = ""
    for c = 0, 39 do
        local tile = vread(FIXMAP + c * 32 + row) & 0xfff
        local ch = tile
        if tile >= TITLE2_ROW_BASE then
            local idx = math.floor((tile - TITLE2_ROW_BASE) / TITLE2_NPROF)
            ch = TITLE2_CHARS:byte(idx + 1) or 32
        end
        if ch < 32 or ch > 126 then ch = 32 end
        s = s .. string.char(ch)
    end
    return s
end

local function hex40(s)
    local out = ""
    for i = 1, #s do
        out = out .. string.format("%02x", string.byte(s, i))
    end
    return out
end

local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
local start_port = machine.ioport.ports[":ctrl1:joy:START_SELECT"]
local start_field = start_port and start_port.fields["P1 Start"]

local f = assert(io.open(out, "w"))
local n, in_cart = 0, 0
local last_epoch, last_fc = 0, 0
local last_hash = 0
local start_at = nil
local start_hold = 0
local game_started = false
local returned = false
local game_logged = 0
local go_seen = false
local snap_done = false
local b_done = false
local c_done, c_epoch = false, nil
local start_title_seed = nil
-- Attract D1: the demo cycle's D presses and the toggle/row-21 records.
local last_f_row = nil
local last_p_epoch, last_p_aes, last_p_toggles = -1, -1, -1
local d_epoch2, d_epoch3, d_epoch4 = false, false, false
local d_until = 0
local function start_d_press(until_n)
    joy.fields["P1 D"]:set_value(1)
    d_until = until_n
end

local function framecnt()
    if FRAMECNT ~= 0 then return sp:read_u32(FRAMECNT) end
    return 0
end

local function u8a(a) return sp:read_u8(a) end
local function u16a(a) return sp:read_u16(a) end
local function u32a(a) return sp:read_u32(a) end

-- Attract D1: the cycle run taps the 68k's REG_SOUND writes (0x320000). The
-- tap sees the command byte as a 16-bit value with the byte in both halves
-- (0x0404 for fire), like scripts/sound_probe.lua's; 3 (the entry reset) is
-- ignored, so only the demo's effects 4..9 are recorded.
if mode == "cycle" then
    local function on_sound(offset, data, mask)
        local cmd = data & 0xff
        if offset >= 0x320000 and offset <= 0x320001
           and cmd >= 4 and cmd <= 9 then
            local ep = EPOCH ~= 0 and u16a(EPOCH) or 0
            local fc = DEMOFC ~= 0 and u16a(DEMOFC) or 0
            f:write(string.format("S %d %d %d %d\n", n, ep, fc, cmd))
        end
        return data
    end
    _G.__demo_sound_tap = sp:install_write_tap(0x320000, 0x320001, "sound",
                                               on_sound)
end

-- the same field block D and G carry after their tag-specific header.
local function state_fields()
    local i, hex = 0, ""
    for i = 0, 9 do
        hex = hex .. string.format("%02x", u8a(SHIP + 28 + i))
    end
    local s = string.format(
        "%d %d %d %d %d %d %d %d %d %d %d %d %d %s " ..
        "%d %d %d %d %d %d %d %d %d %d",
        u8a(RULES), u8a(RULES + 77), u8a(RULES + 78), u8a(RULES + 79),
        u8a(RULES + 80), u8a(RULES + 81), u8a(RULES + 82),
        u8a(SHIP), u8a(SHIP + 1), u8a(SHIP + 2), u8a(SHIP + 3),
        u8a(SHIP + 5), u8a(SHIP + 8), hex,
        u16a(MIS + 70), u8a(MIS + 72), u8a(MIS + 73), u8a(MIS + 74),
        u8a(MIS + 75), u32a(MIS + 76), u8a(MIS + 81), u8a(MIS + 106),
        u8a(RADAR + 36), u8a(RADAR + 37))
    for i = 0, 4 do
        local o = MIS + i * 14
        s = s .. string.format(" %d %d %d %d %d %d %d",
                               u8a(o), u8a(o + 1), u8a(o + 2), u8a(o + 3),
                               u8a(o + 4), u32a(o + 6), u32a(o + 10))
    end
    return s
end

-- the effective level (flow_level_get): a valid marker with 0..2, else
-- NORMAL (1).
local function eff_level()
    local v = u8a(LEVEL)
    local l = u8a(LEVEL + 1)
    if v == 0x53 and l <= 2 then return l end
    return 1
end

local function best_rec()
    if BEST == 0 then return end
    local i, hex = 0, ""
    for i = 0, 125 do
        hex = hex .. string.format("%02x", u8a(BEST + i))
    end
    f:write(string.format("B %d %d %d %s\n", n, u16a(EPOCH), u16a(DEMOFC), hex))
end

-- the sprite census, exactly scripts/ground_probe.lua's scan(): every slot's
-- effective box (sticky chains inherit the previous Y and height), counted
-- per scanline.
local function scan()
    local rows = {}
    local prev_top, prev_h = 0, 0
    local s
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
            local bot = top + h * 16 - 1
            local y0 = math.max(0, top)
            local y1 = math.min(223, bot)
            local y
            for y = y0, y1 do
                rows[y] = (rows[y] or 0) + 1
            end
        end
    end
    local best, bestline = 0, -1
    local y
    for y = 0, 223 do
        local c = rows[y] or 0
        if c > best then best, bestline = c, y end
    end
    return best, bestline
end

local function tick()
    n = n + 1
    if in_cart == 0 and cpu.state["PC"].value >= 0x100000 then
        in_cart = 1
    end
    if in_cart == 0 then
        if n >= run_len then
            f:write(string.format("EXIT %d 0 0\n", n))
            f:write(string.format("pc_in_cart=%d frames=%d\n", in_cart, n))
            f:close()
            machine:exit()
        end
        return
    end

    local fc = framecnt()
    local epoch = u16a(EPOCH)
    local dfc = u16a(DEMOFC)
    local page = PAGE ~= 0 and u8a(PAGE) or 0
    local tt = TT ~= 0 and u16a(TT) or 0

    -- Attract D1: the AES toggle state and fix row 21, logged on change.
    if AES_ON ~= 0 and epoch >= 1 and epoch <= 100 and dfc <= 2700 then
        local aes = u8a(AES_ON)
        local togs = TOGGLES ~= 0 and u16a(TOGGLES) or 0
        if epoch ~= last_p_epoch or aes ~= last_p_aes
           or togs ~= last_p_toggles then
            f:write(string.format("P %d %d %d %d %d %d %d\n", n, epoch, dfc,
                                  page, tt, aes, togs))
            last_p_epoch, last_p_aes, last_p_toggles = epoch, aes, togs
        end
        local row21 = row_text(21)
        if row21 ~= last_f_row then
            f:write(string.format("F %d %d %d %d %d %s\n", n, epoch, dfc,
                                  page, tt, hex40(row21)))
            last_f_row = row21
        end
    end

    -- Attract D1: the demo cycle's D presses. Epoch 2 (page 0) turns the
    -- demo sound ON; epoch 3's page 1 turns it OFF after demo frame 300; a
    -- 60-frame hold at epoch 4's start toggles it ON once (a press, not a
    -- hold: bios_p1change has the edge only on the first frame). The port
    -- is set after this frame's notifier, so the edge lands on the next
    -- cart frame.
    if mode == "cycle" then
        if epoch == 2 and not d_epoch2 then
            d_epoch2 = true
            start_d_press(n + 2)
        elseif epoch == 3 and dfc >= 300 and not d_epoch3 then
            d_epoch3 = true
            start_d_press(n + 2)
        elseif epoch == 4 and not d_epoch4 then
            d_epoch4 = true
            start_d_press(n + 60)
        end
        if d_until > 0 and n >= d_until then
            joy.fields["P1 D"]:set_value(0)
            d_until = 0
        end
    end

    -- the demo cycle's B press: after two full cycles (epoch 3 ends) and a
    -- mid-page 0 frame of epoch 4, press B; the cart changes the level,
    -- returns to page 0 / title_t 0, and demo_restart() makes epoch 5 frame 0
    -- the script's first frame.
    if mode == "cycle" and not b_done and epoch >= 4 and dfc == 500 then
        joy.fields["P1 B"]:set_value(1)
        b_done = true
    elseif b_done then
        joy.fields["P1 B"]:set_value(0)
    end

    -- the C page-through (10-30 fix): the post-B epoch's frames 120..160
    -- tap C 11 times (every 4 frames), turning the title through all 11
    -- pages back to page 0. A wrap by C must restart the demo like the
    -- timer's wrap does (the user's report: after paging with C the script
    -- ran out mid-cycle and the ship froze).
    if mode == "cycle" and b_done and not c_done and epoch >= 5 then
        if c_epoch == nil then c_epoch = epoch end
        if epoch ~= c_epoch or dfc >= 164 then
            c_done = true
            joy.fields["P1 C"]:set_value(0)
        elseif dfc >= 120 then
            joy.fields["P1 C"]:set_value((dfc % 4 == 0) and 1 or 0)
        end
    end

    -- the start run: press Start just after the first crack-jump frame
    -- (boot_test.sh passes that frame + 1 from build/demo.json).
    if mode == "start" and not game_started and start_at == nil
       and epoch == 1 and START_DFC > 0 and dfc >= START_DFC
       and start_field then
        start_field:set_value(1)
        start_at = n
        start_hold = 5
        start_title_seed = u16a(TSEED)
        f:write(string.format("T %d %d %d %d\n", n, epoch, dfc,
                              start_title_seed))
    elseif start_at ~= nil and start_hold > 0 then
        start_hold = start_hold - 1
        if start_hold == 0 and start_field then
            start_field:set_value(0)
        end
    end

    -- the game is real only while the BIOS says so: hud_framecnt can be
    -- caught at 1 for an instant while the title's demo body is mid-frame
    -- (between hud_frame and the restore), and that is not a game.
    if u8a(USER_MODE) == 2 and fc >= 1 then
        if not game_started then
            game_started = true
            start_title_seed = u16a(TSEED)
        end
        if game_logged < 3 then
            f:write(string.format("G %d %d %d %d %s\n", n, fc,
                                  u16a(TSEED), u16a(MISSEED),
                                  state_fields()))
            game_logged = game_logged + 1
            if mode == "start" and game_logged == 1 and not snap_done then
                machine.video:snapshot()
                f:write(string.format("SNAP %d %d %d\n", n, epoch, dfc))
                snap_done = true
            end
        end
        if not go_seen and u8a(RULES + 82) ~= 0 then
            go_seen = true
            f:write(string.format("GO %d %d\n", n, fc))
        end
    else
        -- the title: a new restart logs the best table. A D line is
        -- written only when the cart's frame hash has changed: the notifier
        -- can catch the cart after demo_input advanced the frame counter
        -- but before game_frame/hash, and then the state fields are a frame
        -- ahead of the hash. Logging on the hash change guarantees the
        -- fields and hash are the same completed frame.
        local h = HCUR ~= 0 and u32a(HCUR) or 0
        local hash_fc = HFC ~= 0 and u16a(HFC) or 0
        if epoch ~= 0 and (epoch ~= last_epoch or h ~= last_hash) then
            if epoch ~= last_epoch then
                best_rec()
                if HDONE ~= 0 and u32a(HDONE) ~= 0 then
                    f:write(string.format("H %d %d %d\n", n,
                                          u16a(HEPOCH), u32a(HDONE)))
                end
                last_hash = 0
            end
            if dfc > 0 and h ~= last_hash
               and (HFC == 0 or hash_fc == dfc) then
                f:write(string.format("D %d %d %d %d %d %d %d %s %d %d\n",
                                      n, epoch, dfc,
                                      PAGE ~= 0 and u8a(PAGE) or 0,
                                      TT ~= 0 and u16a(TT) or 0,
                                      u8a(LEVEL), u8a(LEVEL + 1),
                                      state_fields(), h,
                                      PROPS_ANGLE ~= 0 and u8a(PROPS_ANGLE) or 0))
                if mode == "cycle" and epoch == 2 and not snap_done
                   and dfc >= 100 then
                    machine.video:snapshot()
                    f:write(string.format("SNAP %d %d %d\n", n, epoch, dfc))
                    snap_done = true
                end
                if dfc % census_every == 0 then
                    local c, line = scan()
                    f:write(string.format("C %d %d %d %d %d\n", n, epoch,
                                          dfc, c, line))
                end
                if WEND ~= 0 then
                    f:write(string.format("M %d %d %d %d %d %d %d\n", n,
                                          epoch, dfc,
                                          u16a(WEND), u16a(WMAX),
                                          u16a(WMIN), u16a(WSTART)))
                end
                last_hash = h
            end
            last_epoch, last_fc = epoch, dfc
        end
        -- GAME OVER -> BIOS -> the cart's next entry: hud_framecnt is reset
        -- and demo_restart() starts frame 0. Only after that first frame
        -- (dfc 1) can the 100-frame return proof run; the BIOS transition
        -- still shows the last title dfc (1487) with user_mode != 2.
        -- the first post-GO cart frame the notifier can see may be fc 3
        -- (it can catch demo_input's fc bump before game_frame/hash for
        -- fc 1 and 2); the last title dfc is 1487, so this is unambiguous.
        if go_seen and dfc <= 3 then
            returned = true
        end
        if mode == "start" and returned and dfc >= 100 then
            f:write(string.format("EXIT %d %d %d\n", n, fc, epoch))
            f:write(string.format("pc_in_cart=%d frames=%d\n", in_cart, n))
            f:close()
            machine:exit()
            return
        end
    end

    if n >= run_len then
        f:write(string.format("EXIT %d %d %d\n", n, fc,
                              start_title_seed or 0))
        f:write(string.format("pc_in_cart=%d frames=%d\n", in_cart, n))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__demo = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
