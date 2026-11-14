-- mis_seed.lua: the shared Task 1 helper the missile-model probes dofile.
--
-- A game's missile RNG now starts from mis_seed_from(title frames at Start)
-- (src/flow.c game_begin), not RNG_SEED: the cart stores the seed it used in
-- the debug export `mis_seed_used` (found by nm, like rules_dbg_alive), and
-- scripts/boot_test.sh passes its RAM address as MIS_SEED_ADDR. The probes
-- write one line:
--
--   SEED <mame frame> <seed>       mis_seed_used, once the game has begun
--
-- so tests/check_*.py can start tests/mis_model.py's Missiles at the cart's
-- seed (mis_model.cart_seed) instead of 0xACE1. With MIS_PROBE_FIRST=1 and
-- MIS_ADDR (the static `mis`) the probe also writes, at the first missile
-- launch:
--
--   FIRST <mame frame> <ring> <phi>   mis.obj[0]'s state/ring/phi (mis_t's
--                                    obj[0] at +0; the m68k layout)
--
-- which is the variety proof's "the first missile each launches": two runs
-- with Start at different MAME frames must show different ring/phi.
--
-- Both records are written at most once and only once the game has begun
-- (cart frame >= 1) and after the MVS BIOS's RAM clear (MAME frame >= 280):
-- before the clear the MVS work RAM holds 0x55555555 garbage, and the seed
-- word would read nonzero without a game. Env: MIS_SEED_ADDR, MIS_ADDR (0
-- disables that record), MIS_PROBE_FIRST.
local machine = manager.machine
local sp = machine.devices[":maincpu"].spaces["program"]
local seed_addr = tonumber(os.getenv("MIS_SEED_ADDR") or "0")
local mis_addr = tonumber(os.getenv("MIS_ADDR") or "0")
local want_first = os.getenv("MIS_PROBE_FIRST") == "1"
local seed_done, first_done = false, false

local S = {}

-- mis_seed_used, or nil when the address is unknown
function S.seed()
    if seed_addr == 0 then return nil end
    return sp:read_u16(seed_addr)
end

-- call once per probe frame: f is the probe's output file, n the MAME frame,
-- fc the cart's game-session frame (hud_framecnt).
function S.poll(f, n, fc)
    if fc >= 1 and n >= 280 then
        if not seed_done and seed_addr ~= 0 then
            local s = S.seed()
            if s ~= 0 then
                f:write(string.format("SEED %d %d\n", n, s))
                seed_done = true
            end
        end
        if want_first and not first_done and mis_addr ~= 0 then
            if sp:read_u8(mis_addr + 0) == 1 and sp:read_u8(mis_addr + 1) == 0 then
                f:write(string.format("FIRST %d %d %d\n", n,
                                      sp:read_u8(mis_addr + 2),
                                      sp:read_u8(mis_addr + 3)))
                first_done = true
            end
        end
    end
end

return S
