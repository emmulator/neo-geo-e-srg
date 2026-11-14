-- spider_probe.lua: the stopper-spider animation boot-test (Task S2).
--
-- Runs one full demo cycle on the title (the attract mode's ship animates
-- exactly like the game's: Review Focus 4), then presses Start and plays a
-- scripted game:
--
--   fc  7..59   Up held (a walk); B at 11 (a jump latched while the walk
--               runs, so the jump starts the frame the walk ends: Review
--               Focus 1); A latched from 31, so the shot leaves on the
--               landing frame (Review Focus 2); A pressed again at 59, a
--               new shot inside the heave (the restart).
--   fc 70       the first flying missile is forced onto the ship's cell at
--               the dome (the tear leg's poke), so the ship dies while the
--               heave runs, and the probe waits for the respawn (Review
--               Focus 3: the respawned ship is REST).
--
-- Every title/demo cart frame writes a D line and every game cart frame a G
-- line with the ship state (its heading among it), the frame's shot event,
-- the driver's SCB3 and the 4 SCB1 tile words of the 2 x 2 picture.
-- tests/check_spider.py compares the SCB1 tiles on frame N with
-- ship_anim_tile[heading][lat][frame_of(state at N-1)] (the vblank commit
-- lags the state by one frame) and SCB3 with the same state's Y
-- (ship_oy[heading][lat], or height 0 while dead).
--
--   D <mame_n> <epoch> <dfc> <heading> <lat> <move_left> <mlen> <lift>
--     <spinning> <shot> <dead> <scb3> <tile00> <tile01> <tile10> <tile11>
--     <hash>
--   G <mame_n> <fc> <heading> ...same fields after the heading...
--
-- Env: OUT, FRAMES, REPO,
-- SPIDER_SHIP_ADDR, SPIDER_RULES_ADDR, SPIDER_MIS_ADDR,
-- SPIDER_FRAMECNT_ADDR, SPIDER_DEMO_EPOCH_ADDR, SPIDER_DEMO_FC_ADDR,
-- SPIDER_DEMO_HASH_ADDR, SPIDER_MIS_CELL_RING_ADDR,
-- SPIDER_MIS_CELL_PHI_ADDR.
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "7600")
local SHIP = tonumber(os.getenv("SPIDER_SHIP_ADDR") or "0")
local RULES = tonumber(os.getenv("SPIDER_RULES_ADDR") or "0")
local MIS = tonumber(os.getenv("SPIDER_MIS_ADDR") or "0")
local FRAMECNT = tonumber(os.getenv("SPIDER_FRAMECNT_ADDR") or "0")
local EPOCH = tonumber(os.getenv("SPIDER_DEMO_EPOCH_ADDR") or "0")
local DEMOFC = tonumber(os.getenv("SPIDER_DEMO_FC_ADDR") or "0")
local DEMOHASH = tonumber(os.getenv("SPIDER_DEMO_HASH_ADDR") or "0")
local CELL_RING = tonumber(os.getenv("SPIDER_MIS_CELL_RING_ADDR") or "0")
local CELL_PHI = tonumber(os.getenv("SPIDER_MIS_CELL_PHI_ADDR") or "0")

local USER_MODE = 0x10fdaf
local BI, CHG = 0x10fd96, 0x10fd97
local SCB1, SCB3 = 0x0000, 0x8200
local OBJ = 14                     -- mis_obj_t's byte size on m68k
local R_LAND = 1 << 19             -- missiles_tables.h MIS_R_LAND
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local SHIP_SPRITE, SHIP_ROWS = S.SHIP_SPRITE, 2
-- ship_t.heading is the struct's LAST field: the fields the probe reads
-- before it keep their offsets (lat 1, move_left 3, mlen 4, lift 5,
-- spinning 9), and heading is at 38 (tests/test_ship.c asserts it).
local SHIP_HEADING = SHIP + 38

local vram = emu.item(machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(a) return vram:read(a) end
local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
local start_port = machine.ioport.ports[":ctrl1:joy:START_SELECT"]
local start_field = start_port and start_port.fields["P1 Start"]

local f = assert(io.open(out, "w"))
local n, in_cart = 0, 0
local last_dfc, last_epoch, last_fc = -1, -1, -1
local start_requested, start_hold = false, 0
local forced, game_started = false, false
local death_fc, stopped = nil, false

local function release_joy()
    joy.fields["P1 Up"]:set_value(0)
    joy.fields["P1 Down"]:set_value(0)
    joy.fields["P1 Left"]:set_value(0)
    joy.fields["P1 Right"]:set_value(0)
    joy.fields["P1 A"]:set_value(0)
    joy.fields["P1 B"]:set_value(0)
end

local function record(tag, n, a, b)
    local scb3 = vread(SCB3 + SHIP_SPRITE)
    local t0 = vread(SCB1 + SHIP_SPRITE * 64)
    local t1 = vread(SCB1 + SHIP_SPRITE * 64 + 2)
    local t2 = vread(SCB1 + (SHIP_SPRITE + 1) * 64)
    local t3 = vread(SCB1 + (SHIP_SPRITE + 1) * 64 + 2)
    local head
    local heading = sp:read_u8(SHIP_HEADING)
    if tag == "D" then
        head = string.format("D %d %d %d %d", n, a, b, heading)
    else
        head = string.format("G %d %d %d", n, a, heading)
    end
    -- The cart's demo hash covers every frame it ran, so check_spider.py can
    -- prove the full demo cycle even when this notifier misses one D line
    -- (the same miss the demo probe documents and its hash tolerates).
    local hash = DEMOHASH ~= 0 and sp:read_u32(DEMOHASH) or 0
    f:write(head .. string.format(
        " %d %d %d %d %d %d %d %04x %04x %04x %04x %04x %08x\n",
        sp:read_u8(SHIP + 1),   -- lat
        sp:read_u8(SHIP + 3),   -- move_left
        sp:read_u8(SHIP + 4),   -- mlen
        sp:read_u8(SHIP + 5),   -- lift
        sp:read_u8(SHIP + 9),   -- spinning
        sp:read_u8(MIS + 106) & 1,          -- SFX_FIRE
        (sp:read_u8(RULES + 80) ~= 0 or sp:read_u8(RULES + 82) ~= 0) and 1 or 0,
        scb3, t0, t1, t2, t3, hash))
end

-- the scripted game: input for the game frame after `fc`
local function drive_game(fc)
    local nf = fc + 1
    local up, a, b = 0, 0, 0
    if nf >= 7 and nf <= 59 then up = 1 end
    if nf == 11 then b = 1 end
    if nf >= 31 and nf <= 55 then a = 1 end
    if nf == 59 then a = 1 end
    joy.fields["P1 Up"]:set_value(up)
    joy.fields["P1 A"]:set_value(a)
    joy.fields["P1 B"]:set_value(b)
    joy.fields["P1 Left"]:set_value(0)
    joy.fields["P1 Right"]:set_value(0)
    joy.fields["P1 Down"]:set_value(0)
end

-- force the first flying missile onto the ship's cell at the dome (the tear
-- leg's poke), so the resting ship dies next frame; the bullets already in
-- flight are cleared so none can shoot it down first.
local function force_missile()
    if forced or MIS == 0 or CELL_RING == 0 or CELL_PHI == 0 then return end
    local cell = sp:read_u8(SHIP + 2)
    if cell > 75 then return end
    local nr = sp:read_u8(CELL_RING + cell)
    local np = sp:read_u8(CELL_PHI + cell)
    for i = 0, 2 do
        local o = MIS + i * OBJ
        if sp:read_u8(o) == 1 and sp:read_u8(o + 1) == 0 then
            local dr = sp:read_u32(o + 10)
            sp:write_u8(o + 2, nr)
            sp:write_u8(o + 3, np)
            sp:write_u32(o + 6, R_LAND + dr)
            for j = 3, 4 do
                sp:write_u8(MIS + j * OBJ, 0)
            end
            forced = true
            return
        end
    end
end

-- the actual loop, driven from the frame notifier (the AES BIOS preamble
-- runs at low addresses; the cart's code lives at 0x100000+)
local function tick()
    n = n + 1
    if in_cart == 0 and cpu.state["PC"].value >= 0x100000 then
        in_cart = 1
    end
    if in_cart == 0 then
        if n >= run_len then
            f:write(string.format("EXIT %d 0\n", n))
            f:close()
            machine:exit()
        end
        return
    end

    local user_mode = sp:read_u8(USER_MODE)
    local fc = FRAMECNT ~= 0 and sp:read_u32(FRAMECNT) or 0
    local epoch = EPOCH ~= 0 and sp:read_u16(EPOCH) or 0
    local dfc = DEMOFC ~= 0 and sp:read_u16(DEMOFC) or 0

    if user_mode ~= 2 then
        release_joy()
        if epoch >= 1 and dfc > 0
                and (dfc ~= last_dfc or epoch ~= last_epoch) then
            record("D", n, epoch, dfc)
            last_dfc, last_epoch = dfc, epoch
        end
        -- one full demo cycle first (epoch 2's page 0 is the full 3245
        -- frames; epoch 1 is only 3242 on the first entry); then press
        -- Start on the next page 0
        if not start_requested and epoch >= 3 and start_field then
            start_field:set_value(1)
            start_requested = true
            start_hold = 5
        end
    else
        if not game_started and fc >= 1 then
            game_started = true
        end
        if game_started and fc >= 1 and fc ~= last_fc then
            record("G", n, fc, 0)
            last_fc = fc
            drive_game(fc)
            if fc >= 70 then
                force_missile()
            end
            local dead = sp:read_u8(RULES + 80) ~= 0
                    or sp:read_u8(RULES + 82) ~= 0
            if dead and death_fc == nil and fc > 2 then
                death_fc = fc
            end
            if death_fc ~= nil and not dead and fc >= death_fc + 118 then
                -- the respawn frame has run: five more frames show REST
                if fc >= death_fc + 123 then
                    stopped = true
                end
            end
        end
    end

    if start_hold > 0 then
        start_hold = start_hold - 1
        if start_hold == 0 and start_field then
            start_field:set_value(0)
        end
    end

    if stopped or n >= run_len then
        machine.video:snapshot()
        f:write(string.format(
            "EXIT %d %d %d %d %d %d\n", n, game_started and 1 or 0,
            death_fc or 0, fc, epoch, dfc))
        f:write(string.format("pc_in_cart=1 frames=%d death=%s\n", n,
                              tostring(death_fc or 0)))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__spider = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
