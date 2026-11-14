-- sky_probe.lua: for the dome-scenery Task 4 sky boot-test.
--
-- Boots the normal cart, lets the title come up, snapshots it, presses
-- Start once (the standard start_game.lua window, MAME frames 600..604),
-- lets the game run a few dozen frames, snapshots it, and exits.
-- tests/check_sky.py reads the two snapshots in order and proves the
-- backdrop pixel is the sky colour on the title and in play (attract Task
-- A2 put the game's scene behind the title, so the title's backdrop is the
-- sky too).
--
-- The snapshot pair: MAME writes 0000.png, 0001.png, ... under its snapshot
-- directory in order; boot_test.sh copies the first to $OUT/snap.png while
-- the checker walks the whole directory (the same pattern check_hud.py and
-- check_ship_respawn.py use).
--
-- Output:
--   TITLE <n> <fc>     the title snapshot was taken (fc == 0)
--   PLAY  <n> <fc>     the in-play snapshot was taken (fc >= 30)
--   pc_in_cart=1 frames=N rec=R
-- Env: OUT, FRAMES, SKY_FRAMECNT_ADDR (the cart's game-session frame
-- counter, hud_framecnt, from nm; 0 disables the fc reads), SG_BEGIN /
-- SG_END (the Start window, 600..604).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "900")
local framecnt_addr = tonumber(os.getenv("SKY_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")

local f = assert(io.open(out, "w"))
local n, in_cart, rec = 0, 0, 0
local title_snap, play_snap = false, false

local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return 0
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
        -- the title: a confirmed title frame (fc 0) after the BIOS preamble
        -- has settled, snapshotted once
        if not title_snap and n >= 200 and fc == 0 then
            machine.video:snapshot()
            f:write(string.format("TITLE %d %d\n", n, fc))
            title_snap = true
        end
        -- in play: a few dozen game frames after the Start window, so the
        -- title's rows are gone and the game's first frames have drawn
        if title_snap and not play_snap and fc >= 30 then
            machine.video:snapshot()
            f:write(string.format("PLAY %d %d\n", n, fc))
            play_snap = true
        end
    end
    if n >= run_len then
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d\n",
                              in_cart, n, rec))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__sky = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
