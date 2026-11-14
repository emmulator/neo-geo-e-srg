-- radar_probe.lua: the M5 Task 4 radar boot-test (proof 2).
--
-- Boots the RADAR_TEST cart (built with -DRADAR_TEST: its first missile of
-- each game is forced to target the ship's start cell 27, so with no input
-- the ship rests on that cell and the lock-on happens by itself — see the
-- flag's comment in src/main.c). Holds NO input, and plays ~2400 MAME frames
-- (~1920 cart frames after the ~477-frame AES BIOS preamble). Every cart
-- frame it reads, straight from RAM and VRAM:
--
--   - the ship (cell, move_left, dome_angle) and every missile object
--     (state, kind, ring, phi, life, r, dr) — the static `ship`/`mis` in
--     build/rom-radartest.elf, found by m68k-neogeo-elf-nm in boot_test.sh;
--     the field offsets are the C structs' m68k layout (checked against the
--     ELF's DWARF): ship_t: cell@2, move_left@3, dome_angle@0; mis_obj_t:
--     state@0 kind@1 ring@2 phi@3 life@4 r@s32@6 dr@s32@10, obj[i] at
--     mis + i*14; mis_t is 106 bytes;
--   - the cart's own radar_t (the static `radar`): blip[k] {shown@0,
--     locked@1, sx@s16@2, sy@s16@4, h@6, hx@s16@8, hy@s16@10}, then
--     lock_t@36, locked@37, ellipse_bright@38 — the very struct the drawing
--     read, so the checker can prove the drawing's fields against it;
--   - every radar sprite slot's VRAM: SCB2/SCB3/SCB4 and SCB1 row-0 tile +
--     attribute;
--   - the ellipse's palette entry (bank RADAR_PAL_BANK 20, entry 1 =
--     0x400282);
--   - every 30th cart frame, ALL 381 sprite slots' SCB3/SCB4, so the
--     checker can count the most sprites on any line in the radar rows.
--
-- tests/check_radar.py computes the expected radar_t from the RAM (via
-- tests/radar_model.py), proves the C's blips match it within 1 px and the
-- VRAM matches the C's blips exactly (within 1 px), proves the palette
-- entry matches the blink, and asserts >= 50 sampled frames are locked.
--
-- Output:
--   I <rec> <fc> <cur> <chg>      every record (the input read-back truth)
--   A <fc> <cell> <move_left> <dome_angle>
--   O <fc> <i> <state> <kind> <ring> <phi> <life> <r> <dr>
--   B <fc> <k> <shown> <locked> <sx> <sy> <h> <hx> <hy>
--   R <fc> <lock_t> <locked> <bright>
--   T <fc> <slot> <attr> <tile0> <scb2> <scb3> <scb4>
--   P <fc> <pal15>
--   W <fc>                          a full sprite census follows:
--   w <slot> <scb3> <scb4> ...      (all 381 slots)
--   SNAP <fc>                       snapshot taken on a frame showing both
--                                   blips (locked + diagonal, for the user)
--
-- Env: OUT, FRAMES (2400), RADAR_MIS_ADDR, RADAR_SHIP_ADDR,
-- RADAR_FRAMECNT_ADDR / HUD_FRAMECNT_ADDR, RADAR_RADAR_ADDR,
-- RADAR_W_EVERY (30), RADAR_SAMPLE_EVERY (6).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "2400")
local w_every = tonumber(os.getenv("RADAR_W_EVERY") or "30")
local framecnt_addr = tonumber(os.getenv("RADAR_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")
local mis_addr = tonumber(os.getenv("RADAR_MIS_ADDR") or "0")
local ship_addr = tonumber(os.getenv("RADAR_SHIP_ADDR") or "0")
-- the static `radar` in build/rom-radartest.elf (found by nm in boot_test.sh)
local radar_addr = tonumber(os.getenv("RADAR_RADAR_ADDR") or "0")
-- sample this many cart frames apart (the run is ~1900 cart frames, so
-- sample_every 6 gives ~260 samples covering the whole first game: the
-- first missile's ~580-frame lock, its landing, the death, the respawn and
-- the second game's first missile locking again)
local sample_every = tonumber(os.getenv("RADAR_SAMPLE_EVERY") or "6")

local BI, CHG = 0x10fd96, 0x10fd97
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local RADAR0, RADAR_COUNT = S.RADAR_SPRITE, S.RADAR_COUNT
local RADAR_PAL_ENTRY = 0x400000 + (20 * 16 + 1) * 2   -- bank 20, entry 1

-- the C structs' m68k layout (checked against the ELF's DWARF; see the
-- header comment): the offsets never change mid-task
local OBJ = 14                  -- mis_obj_t's byte size on m68k
local R_OFF = 6                 -- mis_obj_t.r (s32)
local DR_OFF = 10               -- mis_obj_t.dr (s32)

local f = assert(io.open(out, "w"))
local n, in_cart, rec, sample = 0, 0, 0, 0
local snapped = false
-- the cart now boots to a title: this helper presses Start to begin a game
-- (M6 Task 1), and exposes game_started(fc). The radar probe holds no
-- input (the RADAR_TEST cart's first missile locks by itself), so it only
-- needs the game_started guard so it never reads the title as a game.
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

local function s32(v)
    if v >= 0x80000000 then v = v - 0x100000000 end
    return v
end

local function s16(v)
    if v >= 0x8000 then v = v - 0x10000 end
    return v
end

local function dump_sample(fc)
    local i, s, k
    local cell = sp:read_u8(ship_addr + 2)
    local left = sp:read_u8(ship_addr + 3)
    local da = sp:read_u8(ship_addr + 0)
    f:write(string.format("A %d %d %d %d\n", fc, cell, left, da))
    for i = 0, 4 do
        local o = mis_addr + i * OBJ
        f:write(string.format("O %d %d %d %d %d %d %d %d %d\n",
                              fc, i, sp:read_u8(o + 0), sp:read_u8(o + 1),
                              sp:read_u8(o + 2), sp:read_u8(o + 3),
                              sp:read_u8(o + 4), s32(sp:read_u32(o + R_OFF)),
                              s32(sp:read_u32(o + DR_OFF))))
    end
    for k = 0, 2 do
        local b = radar_addr + k * 12
        f:write(string.format("B %d %d %d %d %d %d %d %d %d\n",
                              fc, k, sp:read_u8(b + 0), sp:read_u8(b + 1),
                              s16(sp:read_u16(b + 2)), s16(sp:read_u16(b + 4)),
                              sp:read_u8(b + 6), s16(sp:read_u16(b + 8)),
                              s16(sp:read_u16(b + 10))))
    end
    f:write(string.format("R %d %d %d %d\n", fc,
                          sp:read_u8(radar_addr + 36),
                          sp:read_u8(radar_addr + 37),
                          sp:read_u8(radar_addr + 38)))
    for s = 0, RADAR_COUNT - 1 do
        local slot = RADAR0 + s
        local attr = vread(SCB1 + slot * 64 + 1)
        local t0 = vread(SCB1 + slot * 64)
        f:write(string.format("T %d %d %04x %04x %04x %04x %04x\n",
                              fc, slot, attr, t0, vread(SCB2 + slot),
                              vread(SCB3 + slot), vread(SCB4 + slot)))
    end
    f:write(string.format("P %d %04x\n", fc, sp:read_u16(RADAR_PAL_ENTRY)))
end

-- the full sprite census (every slot's SCB3/SCB4) for the per-line count
local function dump_all(fc)
    local s
    f:write(string.format("W %d\n", fc))
    for s = 1, 381 do
        f:write(string.format("w %d %04x %04x\n", s, vread(SCB3 + s),
                              vread(SCB4 + s)))
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
        -- the samples key on the game-session frame (fc) so they never read
        -- the title; nothing of the probe's own is ever held
        if SG.game_started(fc) and sample < 320 and (fc - 1) % sample_every == 0 then
            dump_sample(fc)
            if (fc - 1) % w_every == 0 then
                dump_all(fc)
            end
            -- snapshot the first sampled frame that shows BOTH blips (the
            -- locked vertical missile AND the diagonal second one, so
            -- docs/superpowers/m5-radar.png shows the two heading styles),
            -- from the cart's radar_t in RAM
            local locked = sp:read_u8(radar_addr + 37)
            local blip1_shown = sp:read_u8(radar_addr + 12)  -- blip[1].shown
            if not snapped and locked ~= 0 and blip1_shown ~= 0 then
                machine.video:snapshot()
                f:write(string.format("SNAP %d\n", fc))
                snapped = true
            end
            sample = sample + 1
        end
    end
    if n >= run_len then
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d samples=%d snapped=%d\n",
                              in_cart, n, rec, sample, snapped and 1 or 0))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__radar = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
