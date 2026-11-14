-- frame_mark_probe.lua: the M4 Task 4 frame-budget measurement.
--
-- Boots the -DFRAME_MARK cart (which records, every frame, the LSPC line
-- counter at the end of the frame's work in work_end_mark, a BSS u16) and
-- drives the same deterministic full game as collapse_probe.lua (centred
-- stick, A every 11 cart frames (the taps stop at the last launch, fc
-- 27105 under Task 1's seed — the game's GAME OVER is at fc 27142):
-- Task 1 seeds the missiles from the title's time, so the dome deaths
-- moved (8359, 16715, 27105; 8202, 16386, 24845 before) — the Vectrex
-- 1.1.0 rule opens the rings at 6 cell-breaking hits on the
-- dome), so the collapse and the busiest crack/missile frames all happen.
-- Each MAME frame it reads work_end_mark (which holds the LAST completed
-- frame's value) and tracks the worst line; the checker turns that into
-- the frame time and asserts no frame's work reached the bottom of the
-- visible area (a dropped frame would: the work would spill into the
-- next frame's vblank or beyond).
--
-- The marks are a signed u16 vpos (main.c's lspc_vpos): 0..263 as-is,
-- and the vblank tail past the 264-line frame-end shows as a negative
-- (e.g. 0xFFFE = vpos -2 = line 262). A frame's work span is
-- (end - start) mod 264.
--
-- Output:
--   I <rec> <fc> <cur> <chg>      every record (the input read-back truth)
--   M <fc> <end> <max> <min> <start>
--                                 each frame: the LAST completed frame's
--                                 work-end line, the run's max/min so far,
--                                 and its work-start line (the vblank
--                                 return, which brackets the work span).
-- Env: OUT, FRAMES, HUD_FRAMECNT_ADDR, END_ADDR, MAX_ADDR, MIN_ADDR,
-- START_ADDR.
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "25700")
local framecnt_addr = tonumber(os.getenv("COLLAPSE_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")
local end_addr = tonumber(os.getenv("END_ADDR") or "0")
local max_addr = tonumber(os.getenv("MAX_ADDR") or "0")
local min_addr = tonumber(os.getenv("MIN_ADDR") or "0")
local start_addr = tonumber(os.getenv("START_ADDR") or "0")

local BI, CHG = 0x10fd96, 0x10fd97
local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
-- the cart now boots to a title: this helper presses Start to begin a game
-- (M6 Task 1), and exposes game_started(fc) to keep our drive() off the title
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")

local function hold(name, on)
    joy.fields[name]:set_value(on and 1 or 0)
end

local f = assert(io.open(out, "w"))
local n, in_cart, rec = 0, 0, 0

local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec
end

-- the centred policy, keyed on the cart frame (same as collapse_probe.lua):
-- the stick centred always, A (fire) tapped every 11 frames
local function drive(fc)
    if not SG.game_started(fc) then     -- the title: no input of our own
        return
    end
    hold("P1 Left", false)
    hold("P1 Up", false)
    hold("P1 Right", false)
    hold("P1 Down", false)
    hold("P1 A", fc <= 27105 and (fc % 11) == 0)
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
        f:write(string.format("I %d %d %d %d\n", rec, fc, sp:read_u8(BI), sp:read_u8(CHG)))
        drive(fc)
        if end_addr ~= 0 then
            f:write(string.format("M %d %d %d %d %d\n", fc,
                                  sp:read_u16(end_addr),
                                  sp:read_u16(max_addr),
                                  sp:read_u16(min_addr),
                                  sp:read_u16(start_addr)))
        end
    end
    if n >= run_len then
        machine.video:snapshot()
        f:write(string.format("M %d %d %d %d %d\n", framecnt(),
                              sp:read_u16(end_addr),
                              sp:read_u16(max_addr),
                              sp:read_u16(min_addr),
                              sp:read_u16(start_addr)))
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d\n", in_cart, n, rec))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__fmark = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
