-- boot_probe.lua: run FRAMES frames, optionally hold an input from frame 120,
-- record whether the 68k ever ran in cart space, snapshot, exit.
-- Env: FRAMES (900 default — the AES BIOS preamble alone takes ~470 frames),
-- HOLD (an input field name, e.g. "P1 Right"), OUT (probe.txt).
--
-- Since M6 Task 1 the cart boots to a title and only starts a game on a
-- Start press (start_game.lua holds it on frames 600..604), so the first
-- game frame (hud_framecnt 1) is START_DELAY frames later than before
-- (measured once: with today's fc 1 at MAME frame ~477 and the title's at
-- frame 603, START_DELAY = 603 - 477 = 126). The input hold and the
-- snapshot both shift by that constant, so the held game the probe
-- snapshots is the same game the pre-M6 probe saw at the same offset.
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local frames = tonumber(os.getenv("FRAMES") or "900")
-- the leg list's VAR=value has no spaces, so the port field's name
-- (e.g. "P1 Up") is written with underscores and mapped back here.
local hold = (os.getenv("HOLD") or ""):gsub("_", " ")
local out = os.getenv("OUT")
local START_DELAY = 126
local hold_at = 120 + START_DELAY
local snap_at = frames + START_DELAY
local n, in_cart, held = 0, 0, false
-- the Start press that leaves the title for a game (M6 Task 1)
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")

local function tick()
  n = n + 1
  SG.sg_apply(n)
  if cpu.state["PC"].value < 0x100000 then in_cart = 1 end
  if hold and hold ~= "" and n == hold_at and not held then
    machine.ioport.ports[":ctrl1:joy:JOY"].fields[hold]:set_value(1)
    held = true
  end
  if n == snap_at then
    machine.video:snapshot()
    local f = io.open(out, "w")
    f:write(string.format("pc_in_cart=%d frames=%d\n", in_cart, n))
    f:close()
    machine:exit()
  end
end

if emu.add_machine_frame_notifier then
  _G.__probe = emu.add_machine_frame_notifier(tick)
else
  emu.register_frame(tick)
end
