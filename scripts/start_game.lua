-- start_game.lua: a helper every MAME probe dofiles (M6 Task 1).
--
-- The cart now boots to a title instead of straight into a game, so every
-- probe that plays a game must press the AES Start button once. This helper
-- holds "P1 Start" at the cart's title frame count, which leaves the title
-- for a game. The game-session frame counter (hud_framecnt) then becomes 1
-- on the game's first frame, so a probe that keyed its drive() on the cart
-- frame keeps working — the game has always begun at fc 1.
--
-- Plan P2 amendment 3: the game's missile seed is mis_seed_from(title_seed_t
-- at the Start). Pressing on a fixed MAME frame gives a different seed when
-- the title's frame work changes (P2's title frames are cheaper: 577 title
-- frames run before MAME 600 instead of HEAD's 575). So the helper presses
-- on the CART's title count instead: TITLE_SEED_ADDR is title_seed_t's RAM
-- address (found by nm in boot_test.sh), and SG_TITLE_BEGIN is the title
-- count that gives HEAD's seed. The hold is SG_TITLE_END-SG_TITLE_BEGIN+1
-- frames, the same number as the old MAME window.
--
-- It exposes:
--   SG.sg_apply(n)     hold "P1 Start" once title_seed_t reaches
--                      SG_TITLE_BEGIN (or, without a title address, on MAME
--                      frames SG_BEGIN..SG_END). Call once per tick with the
--                      probe's MAME frame counter n.
--   SG.game_started(fc)  true once the cart's game-session frame >= 1 (the
--                      game has begun; drive() may act).
--
-- Without TITLE_SEED_ADDR/SG_TITLE_BEGIN (tests that do not play a game,
-- or a probe run outside boot_test.sh) the old MAME window is used; its
-- default is the confirmed 600..604. The flow boot-test (proof a..d of the
-- task) overrides it to 1200..1204 with SG_BEGIN. SG_ENABLE=0 disables the
-- Start press entirely (the title must stay up: used to measure the title
-- frame's time with a framemark cart).
--
-- EVERY probe's own drive(fc) / holds / taps must do nothing while fc == 0
-- (the title), with `if SG.game_started(fc) then ... end` or an equivalent
-- fc >= 1 guard, so no B / C / probe-input press reaches the title — only
-- the Start press here.
local machine = manager.machine
-- the AES Start button lives in the :ctrl1:joy:START_SELECT port's "P1
-- Start" field (the confirmed map), not in the :JOY joypad port the
-- probes use to drive the stick and A/B/C/D.
local start_field = machine.ioport.ports[":ctrl1:joy:START_SELECT"] and
    machine.ioport.ports[":ctrl1:joy:START_SELECT"].fields["P1 Start"]
local SG_BEGIN = tonumber(os.getenv("SG_BEGIN") or "600")
local SG_END   = tonumber(os.getenv("SG_END") or "604")
local enabled  = (os.getenv("SG_ENABLE") ~= "0") and start_field ~= nil
-- Plan P2 amendment 3: the title count to press at (0 disables).
local TITLE_SEED_ADDR = tonumber(os.getenv("TITLE_SEED_ADDR") or "0")
local SG_TITLE_BEGIN = tonumber(os.getenv("SG_TITLE_BEGIN") or "-1")
local SG_TITLE_END   = tonumber(os.getenv("SG_TITLE_END") or "-1")
local sp = machine.devices[":maincpu"].spaces["program"]
local armed = false      -- saw the title count reach SG_TITLE_BEGIN
local hold  = 0          -- Start frames left in this press

local function sg_apply(n)
    if not enabled then return end
    if TITLE_SEED_ADDR ~= 0 and SG_TITLE_BEGIN >= 0 then
        -- the notifier runs at the frame's start, before this frame's
        -- title_frame increments title_seed_t: a press whose game_begin
        -- reads SG_TITLE_BEGIN is applied when the counter still shows one
        -- less (the Start is seen by the BIOS in this frame).
        local ts = sp:read_u16(TITLE_SEED_ADDR)
        if not armed and ts + 1 >= SG_TITLE_BEGIN then
            armed = true
            hold = SG_TITLE_END - SG_TITLE_BEGIN + 1
        end
        if armed and hold > 0 then
            start_field:set_value(1)
            hold = hold - 1
        else
            start_field:set_value(0)
        end
    else
        start_field:set_value((n >= SG_BEGIN and n <= SG_END) and 1 or 0)
    end
end

local function game_started(fc)
    return fc >= 1
end

return { sg_apply = sg_apply, game_started = game_started }
