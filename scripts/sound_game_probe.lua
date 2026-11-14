-- sound_game_probe.lua: the M7 Task 2 sound-game boot-test.
--
-- Boots the -DSOUND_TEST cart (build/rom-soundtest.zip) and drives the
-- normal game through the plan's centred policy: no stick (the ship rests
-- on the start cell), A tapped when fc % 11 == 0 (taps stop at the last
-- launch, fc 27105), to GAME OVER at fc ~27142 (Task 1's seed: the
-- Start at MAME 600 gives seed 0xaede; 24963 was the 0xACE1 game). The
-- model gives this game 1624 fire, 89 crack and 15 hit sends, no jumps
-- and no pips (the centred ship never moves, so no jumps; the plain
-- soundtest cart has no radar); the checker replays the model from the
-- recorded inputs and proves the logged sends equal its predicted
-- commands frame for frame.
-- The cart records EVERY game sound command in the sound_test_glog RAM
-- log (fc_lo, fc_hi, cmd, ok per record; sound_test_gn counts; found by
-- nm in boot_test.sh).
--
-- Every MAME frame the probe:
--   I <rec> <fc> <cur> <chg>     the BIOS joypad read-back (the ground
--                                truth the checker replays into the models)
--   G <n> <logfc> <cmd> <ok>     a new game-log record noticed (the
--                                checker aligns it to the cart frame)
-- and at the end a snapshot for boot_test.sh's boilerplate.
--
-- The policy drives ONLY while the game session has started (fc >= 1);
-- before that (the title), no input of ours reaches the cart — the Start
-- press comes from scripts/start_game.lua. The probe reads the game log's
-- RECORD count (sound_test_gn, +1 per record) once per frame; the cart
-- stores fc_lo, fc_hi, cmd, ok then bumps gn, so the notifier may land
-- between the stores — a mid-write record's bytes are incomplete. The
-- count is read AFTER the frame's work, so a record the cart wrote this
-- frame is complete by the time the probe reads it (the frame notifier
-- runs at vblank, outside the frame).
--
-- Env: OUT, FRAMES (25600), SOUND_GLOG_ADDR, SOUND_GN_ADDR,
-- SOUND_FRAMECNT_ADDR, SOUND_RADAR_MODE, REPO.
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "25600")
local glog_addr = tonumber(os.getenv("SOUND_GLOG_ADDR") or "0")
local gn_addr = tonumber(os.getenv("SOUND_GN_ADDR") or "0")
local REPO = os.getenv("REPO") or "."

local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
local SG = dofile(REPO .. "/scripts/start_game.lua")
local MS = dofile((os.getenv("REPO") or ".") .. "/scripts/mis_seed.lua")
-- the radar leg holds NO input: the game's lock-on is forced by the
-- cart's RADAR_TEST hook (the first missile aims at the resting ship).
local radar_mode = os.getenv("SOUND_RADAR_MODE") == "1"

local function hold(name, on)
    joy.fields[name]:set_value(on and 1 or 0)
end

-- the plan's centred policy: no stick at all (the ship rests on the start
-- cell), A tapped when fc % 11 == 0 (taps stop at fc 27105, the last
-- launch). The % here is Lua's (in the probe only — the cart's own
-- per-frame code has no modulo).
--
-- SOUND_GAME_POLICY=trial selects a policy used ONLY for the mutation-(a)
-- demo (a same-frame hit+crack at fc 2135): segments (1112,Right-Down),
-- (444,Down-Left), (507,Left-Right), (1130,Right-Down), (384,Down-Left);
-- A tapped when fc % 5 == 0 until fc 3112; GAME OVER ~fc 4577 (the model
-- derivation; this game's whole span is before the model/cart divergence
-- the long games show, so the checker can prove the same-frame rule).
local game_policy = os.getenv("SOUND_GAME_POLICY") or "centred"
local function drive(fc)
    if radar_mode then
        return                          -- no input at all
    end
    if not SG.game_started(fc) then
        return
    end
    if game_policy == "trial" then
        -- the trial policy's direction map: 10 = Down|Right, 6 = Down|Left
        -- (the ship_model direction bits), 8 = Up|Right, 4 = Up|Left
        local inp
        local f = fc
        if f <= 1112 then inp = 10
        else f = f - 1112
            if f <= 444 then inp = 6
            else f = f - 444
                if f <= 507 then inp = 8
                else f = f - 507
                    if f <= 1130 then inp = 10
                    else inp = 6 end
                end
            end
        end
        hold("P1 Left",  (inp & 4) ~= 0); hold("P1 Up", (inp & 1) ~= 0)
        hold("P1 Right", (inp & 8) ~= 0); hold("P1 Down", (inp & 2) ~= 0)
        hold("P1 A", (fc <= 3112) and (fc % 5 == 0))
        return
    end
    hold("P1 Left",  false); hold("P1 Up", false)
    hold("P1 Right", false); hold("P1 Down", false)
    hold("P1 A", (fc <= 27105) and (fc % 11 == 0))
end

local f = assert(io.open(out, "w"))
local n, in_cart, rec, logged = 0, 0, 0, 0

local function tick()
    n = n + 1
    if in_cart == 0 and cpu.state["PC"].value >= 0x100000 then
        in_cart = 1
    end
    SG.sg_apply(n)
    if in_cart then
        rec = rec + 1
        local fc = sp:read_u32(tonumber(os.getenv("SOUND_FRAMECNT_ADDR") or "0"))
        f:write(string.format("I %d %d %d %d\n", rec, fc, sp:read_u8(0x10fd96),
                              sp:read_u8(0x10fd97)))
        MS.poll(f, n, fc)
        drive(fc)
        if gn_addr ~= 0 then
            local cnt = sp:read_u16(gn_addr)   -- the cart's RECORD count
            if cnt > logged then
                for i = logged, cnt - 1 do
                    local off = glog_addr + i * 4
                    local logfc = sp:read_u8(off) | (sp:read_u8(off + 1) << 8)
                    f:write(string.format("G %d %d %d %d\n", n, logfc,
                                          sp:read_u8(off + 2), sp:read_u8(off + 3)))
                end
                logged = cnt
            end
        end
    end
    if n >= run_len then
        machine.video:snapshot()
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d glog=%d\n",
                              in_cart, n, rec, logged))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__soundg = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
