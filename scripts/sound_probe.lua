-- sound_probe.lua: the M7 Task 1 sound-pipeline boot-test.
--
-- Boots the -DSOUND_TEST cart (build/rom-soundtest.zip), which on the title
-- sends the five sound commands — 4 fire @ title frame 100, 5 jump @ 160,
-- 6 hit @ 220, 7 crack @ 280, 8 pip @ 340 — and BOTH 6 and 8 in the same
-- frame @ 400, recording each send's title frame and acknowledgement
-- result in a RAM log (sound_test_log / sound_test_n, found by nm in
-- boot_test.sh). The cart boots to the title and never starts a game, so
-- the hook's own u16 counter is the title frame from the title's first
-- frame.
--
-- Every MAME frame the probe reads the log and writes the new records:
--   S <mame_n> <tf> <log_tf> <cmd> <ok>
--     mame_n  the MAME frame the record was noticed on (the send itself
--             happened on the previous frame: the notifier runs after the
--             cart's frame, so the WAV onset is at (mame_n-1)/59.1856)
--     tf      the hook's u16 title counter (sound_test_fc) in the same frame
--     log_tf  the title frame the CART stored in the log (must equal tf)
--     cmd     the command sent (4..8; 6 and 8 share the frame-400 record)
--     ok      the acknowledgement result (1 acked, 0 timed out)
-- A snapshot is taken at the end for boot_test.sh's shared boilerplate
-- (the checker does not use it).
--
-- Env: OUT, FRAMES, SOUND_LOG_ADDR, SOUND_LOGN_ADDR, SOUND_TITLE_FC_ADDR.
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "1100")
local log_addr = tonumber(os.getenv("SOUND_LOG_ADDR") or "0")
local log_n_addr = tonumber(os.getenv("SOUND_LOGN_ADDR") or "0")
local tf_addr = tonumber(os.getenv("SOUND_TITLE_FC_ADDR") or "0")

local f = assert(io.open(out, "w"))
local n, in_cart, logged, started = 0, 0, 0, false

local function tick()
  n = n + 1
  if cpu.state["PC"].value < 0x100000 then in_cart = 1 end
  if in_cart and log_n_addr ~= 0 then
    local cnt = sp:read_u8(log_n_addr)
    local tf = sp:read_u16(tf_addr)
    -- the MVS BIOS's RAM is garbage (0x5555/0xAAAA: cnt 85/170,
    -- tf 21845/43690) until its ~280-frame clear (lessons.md, 2026-10-18);
    -- the log address only holds real values once the cart's runtime has
    -- zeroed .bss and the title has started. Sane: cnt <= 32 (the log's
    -- whole capacity, 8 records) and tf <= 1000 (the run is 1100 frames).
    if not started then
      -- the MVS BIOS's RAM is garbage (0x5555/0xAAAA: cnt 85/170,
      -- tf 21845/43690) until its ~280-frame clear (lessons.md, 2026-10-18);
      -- the log address only holds real values once the cart's runtime has
      -- zeroed .bss and the title has started. Sane: cnt <= 32 (the log's
      -- whole capacity, 8 records), tf <= 1000 (the run is 1100 frames),
      -- AND the first logged command is one of 4..8 (garbage can pass the
      -- two numeric gates at some addresses — the M7 Task 2 game log
      -- shifted the BSS layout — but no garbage byte is ever 4..8).
      if cnt <= 32 and tf <= 1000 then
        -- check the first record's command byte (log_addr + 2): a real
        -- title send, or the log is still empty (cnt == 0)
        local first_cmd = sp:read_u8(log_addr + 2)
        if cnt == 0 or (first_cmd >= 4 and first_cmd <= 8) then
          started = true
        end
      end
    end
    if started then
      -- sound_test_n counts BYTES (4 per record); only whole records are
      -- emitted (a mid-write read would see a partial record: the cart
      -- stores tf_lo, tf_hi, cmd, ok then bumps n, and the probe's
      -- notifier can land between the stores)
      local whole = cnt - (cnt % 4)
      if whole > logged then
        local from = math.floor(logged / 4)
        local to = math.floor(whole / 4) - 1
        for i = from, to do
          local off = log_addr + i * 4
          local log_tf = sp:read_u8(off) | (sp:read_u8(off + 1) << 8)
          f:write(string.format("S %d %d %d %d %d\n", n, tf, log_tf,
                                sp:read_u8(off + 2), sp:read_u8(off + 3)))
        end
        logged = whole
      end
    end
  end
  if n >= run_len then
    machine.video:snapshot()
    f:write(string.format("pc_in_cart=%d frames=%d logged=%d\n",
                          in_cart, n, logged))
    f:close()
    machine:exit()
  end
end

if emu.add_machine_frame_notifier then
  _G.__sound = emu.add_machine_frame_notifier(tick)
else
  emu.register_frame(tick)
end
