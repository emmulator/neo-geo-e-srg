-- start_game.lua: a helper every MAME probe dofiles (M6 Task 1).
--
-- The cart now boots to a title instead of straight into a game, so every
-- probe that plays a game must press the AES Start button once. This helper
-- holds "P1 Start" on MAME frames SG_BEGIN..SG_END (the plan's confirmed
-- 600..604: a Start held there is seen by the BIOS), which leaves the title
-- for a game. The game-session frame counter (hud_framecnt) then becomes 1
-- on the game's first frame, so a probe that keyed its drive() on the cart
-- frame keeps working — the game has always begun at fc 1.
--
-- It exposes:
--   SG.sg_apply(n)     hold "P1 Start" when MAME frame n is in
--                      [SG_BEGIN, SG_END], else release it. Call once per
--                      tick with the probe's MAME frame counter n.
--   SG.game_started(fc)  true once the cart's game-session frame >= 1 (the
--                      game has begun; drive() may act).
--
-- The default window is the confirmed 600..604. The flow boot-test (proof
-- a..d of the task) overrides it to 1200..1204 with SG_BEGIN. SG_ENABLE=0
-- disables the Start press entirely (the title must stay up: used to
-- measure the title frame's time with a framemark cart).
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

local function sg_apply(n)
    if not enabled then return end
    start_field:set_value((n >= SG_BEGIN and n <= SG_END) and 1 or 0)
end

local function game_started(fc)
    return fc >= 1
end

return { sg_apply = sg_apply, game_started = game_started }
