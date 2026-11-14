-- mvs_input.lua: the M6 Task 2 MVS input helper, dofiled by probes that run
-- the cart under the MVS BIOS (`neogeo -bios euro -cart1 esrg`).
--
-- The AES Start helper (start_game.lua) presses "P1 Start" in the
-- :ctrl1:joy:START_SELECT port, which does not exist on the MVS machine; the
-- MVS runs its own coin and Start fields instead:
--   "Coin 1"          port :AUDIO_COIN    (the coin slot)
--   "1 Player Start"  port :edge:joy:START (the P1 Start button)
-- This helper holds "Coin 1" on MAME frames MVS_COIN..MVS_COIN+4 and "1
-- Player Start" at the cart's title count (see Plan P2 amendment 3), or on
-- MVS_START..MVS_START+4 when no title address is given. Either can be off:
-- set the env var to "-100" (or anything below frame 1) and the field is
-- never pressed. A probe dofiles this and calls MI.mi_apply(n) once per tick
-- with its MAME frame counter.
--
-- Plan P2 amendment 3: the MVS game's seed is mis_seed_from(title_seed_t at
-- the Start), so pressing on the fixed MAME frame 1800 would seed a
-- different game when the title's frame work changes. boot_test.sh passes
-- TITLE_SEED_ADDR (title_seed_t's RAM address) and MVS_TITLE_START (HEAD's
-- title count at that MAME frame: 280, mis_seed_from(280) = 0xadf9). The
-- coin at 1500 makes the BIOS enter the cart title afresh, which resets
-- title_seed_t below MVS_TITLE_START; the helper waits for that reset, then
-- holds Start for MVS_TITLE_END-MVS_TITLE_START+1 frames.
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
local TITLE_SEED_ADDR = tonumber(os.getenv("TITLE_SEED_ADDR") or "0")
local MVS_TITLE_START = tonumber(os.getenv("MVS_TITLE_START") or "-1")
local MVS_TITLE_END   = tonumber(os.getenv("MVS_TITLE_END") or "-1")
local sp = machine.devices[":maincpu"].spaces["program"]
local saw_reset = false  -- title_seed_t dropped below MVS_TITLE_START after the coin
local armed     = false  -- saw the title count reach MVS_TITLE_START
local hold      = 0      -- Start frames left in this press

local function mi_apply(n)
    if coin_field and n >= COIN and n <= COIN + 4 then
        coin_field:set_value(1)
    elseif coin_field then
        coin_field:set_value(0)
    end
    if not start_field then return end
    if TITLE_SEED_ADDR ~= 0 and MVS_TITLE_START >= 0 then
        local ts = sp:read_u16(TITLE_SEED_ADDR)
        -- the coin makes the BIOS enter the cart title again; wait until
        -- the count has dropped below the target before arming, so the
        -- pre-coin title's count cannot press early
        if n >= COIN + 5 then
            if not saw_reset and ts < MVS_TITLE_START then
                saw_reset = true
            end
            -- the notifier runs at the frame's start, before this frame's
            -- title_frame increments title_seed_t: the press whose
            -- game_begin reads MVS_TITLE_START is applied one count early.
            if saw_reset and not armed and ts + 1 >= MVS_TITLE_START then
                armed = true
                hold = MVS_TITLE_END - MVS_TITLE_START + 1
            end
        end
        if armed and hold > 0 then
            start_field:set_value(1)
            hold = hold - 1
        else
            start_field:set_value(0)
        end
    else
        start_field:set_value((n >= START and n <= START + 4) and 1 or 0)
    end
end

return { mi_apply = mi_apply, mvs_start = start_field }
