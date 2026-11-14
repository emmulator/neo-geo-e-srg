-- mvs_input.lua: the M6 Task 2 MVS input helper, dofiled by probes that run
-- the cart under the MVS BIOS (`neogeo -bios euro -cart1 esrg`).
--
-- The AES Start helper (start_game.lua) presses "P1 Start" in the
-- :ctrl1:joy:START_SELECT port, which does not exist on the MVS machine; the
-- MVS runs its own coin and Start fields instead:
--   "Coin 1"          port :AUDIO_COIN    (the coin slot)
--   "1 Player Start"  port :edge:joy:START (the P1 Start button)
-- This helper holds "Coin 1" on MAME frames MVS_COIN..MVS_COIN+4 and "1
-- Player Start" on MVS_START..MVS_START+4. Either can be off: set the env
-- var to "-100" (or anything below frame 1) and the field is never pressed.
-- A probe dofiles this and calls MI.mi_apply(n) once per tick with its MAME
-- frame counter.
--
-- It exposes:
--   MI.mi_apply(n)     apply this MAME frame's coin/Start holds.
--   MI.mvs_start       the Start field, or nil on AES (a probe may want to
--                      know it is on MVS and gate its own input on it).
local machine = manager.machine
local coin_field = machine.ioport.ports[":AUDIO_COIN"] and
    machine.ioport.ports[":AUDIO_COIN"].fields["Coin 1"]
local start_field = machine.ioport.ports[":edge:joy:START"] and
    machine.ioport.ports[":edge:joy:START"].fields["1 Player Start"]
local COIN = tonumber(os.getenv("MVS_COIN") or "1500")
local START = tonumber(os.getenv("MVS_START") or "-100")

local function mi_apply(n)
    if coin_field and n >= COIN and n <= COIN + 4 then
        coin_field:set_value(1)
    elseif coin_field then
        coin_field:set_value(0)
    end
    if start_field and n >= START and n <= START + 4 then
        start_field:set_value(1)
    elseif start_field then
        start_field:set_value(0)
    end
end

return { mi_apply = mi_apply, mvs_start = start_field }
