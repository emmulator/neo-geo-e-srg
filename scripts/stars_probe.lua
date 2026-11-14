-- stars_probe.lua: for the M5 Task 2 stars boot-test.
--
-- Boots the normal cart and holds the stick right from cart frame 60, so
-- the ship spins the dome (dome_angle walks the ring, one whole turn per
-- ~69 frames of hold-right at the peak) and the stars turn with it. On 100
-- sampled cart frames it records the ship's dome_angle read straight from
-- RAM (ANGLE_ADDR, the address of the static `ship` in build/rom.elf,
-- found by m68k-neogeo-elf-nm in boot_test.sh) and reads every star slot's
-- SCB4 X, SCB3 Y and height from VRAM.
--
-- The output:
--   I <rec> <fc> <cur> <chg>      every record (the input read-back truth)
--   A <fc> <dome_angle>           a sampled frame; the star slot lines
--                                 follow
--   S <slot> <x> <y> <h>          SCB4>>7, 496-(SCB3>>7), SCB3 height
-- tests/check_stars.py replays the model from the records, proves the RAM
-- angle equals the model's, and every star slot equals stars_pos.
--
-- Env: OUT, FRAMES (1600), STARS_FRAMECNT_ADDR (the cart's frame counter),
-- ANGLE_ADDR (the ship's RAM address, from the ELF).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "1600")
local framecnt_addr = tonumber(os.getenv("STARS_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")
local angle_addr = tonumber(os.getenv("ANGLE_ADDR")
                          or os.getenv("STARS_ANGLE_ADDR") or "0")

local BI, CHG = 0x10fd96, 0x10fd97
local SCB3, SCB4 = 0x8200, 0x8400
-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local STAR0, NSTARS = S.STAR_SPRITE, S.NSTARS

local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
local f = assert(io.open(out, "w"))
local n, in_cart, rec, sample = 0, 0, 0, 0
-- the cart now boots to a title: this helper presses Start to begin a game
-- (M6 Task 1), and exposes game_started(fc) to keep our input off the title
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")
local MS = dofile((os.getenv("REPO") or ".") .. "/scripts/mis_seed.lua")

-- VRAM is read (and, by the leftover probe, written) through MAME's own copy
-- of it, never through the LSPC registers at 0x3c0000/2: writing the address
-- register from a frame callback changes the cart's VRAM pointer under it, and
-- the cart's next writes land at the probe's address (it zeroed title rows).
local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(a)
    return vram:read(a)
end

local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec
end

local function dump_sample(fc)
    local da = sp:read_u8(angle_addr)
    local s, i
    f:write(string.format("A %d %d\n", fc, da))
    for i = 0, NSTARS - 1 do
        local slot = STAR0 + i
        local scb3 = vread(SCB3 + slot)
        local x = vread(SCB4 + slot) >> 7
        local y = 496 - (scb3 >> 7)
        local h = scb3 & 0x3f
        f:write(string.format("S %d %d %d %d\n", slot, x, y, h))
    end
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
        MS.poll(f, n, fc)
        -- hold Right from the moment the main loop runs (the BIOS preamble
        -- is ~477 records of fc == 0; holding earlier can trigger the
        -- BIOS's own boot handling). Set it every frame, as the other
        -- probes' drive() does; the game_started guard keeps the title
        -- untouched.
        if SG.game_started(fc) then
            joy.fields["P1 Right"]:set_value(fc >= 60 and 1 or 0)
        end
        if fc >= 60 and sample < 100 and (fc - 60) % 10 == 0 then
            dump_sample(fc)
            sample = sample + 1
        end
    end
    if n >= run_len then
        machine.video:snapshot()
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d samples=%d\n",
                              in_cart, n, rec, sample))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__stars = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
