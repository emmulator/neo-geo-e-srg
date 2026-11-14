-- sound_probe.lua: the M7 Task 1 sound-pipeline boot-test.
--
-- Boots the -DSOUND_TEST cart (build/rom-soundtest.zip), which on the title
-- sends the six sound commands — 4 fire @ title frame 100, 5 jump @ 160,
-- 6 hit @ 220, 7 crack @ 280, 8 pip @ 340, 9 move @ 460 — and BOTH 6 and
-- 8 in the same frame @ 400, recording each send's title frame and
-- acknowledgement result in a RAM log (sound_test_log / sound_test_n,
-- found by nm in boot_test.sh). The cart boots to the title and never
-- starts a game, so the hook's own u16 counter is the title frame from the
-- title's first frame.
--
-- Every MAME frame the probe reads the log and writes the new records:
--   S <mame_n> <tf> <log_tf> <cmd> <ok>
--     mame_n  the MAME frame the record was noticed on (the send itself
--             happened on the previous frame: the notifier runs after the
--             cart's frame, so the WAV onset is at (mame_n-1)/59.1856)
--     tf      the hook's u16 title counter (sound_test_fc) in the same frame
--     log_tf  the title frame the CART stored in the log (must equal tf)
--     cmd     the command sent (4..9; 6 and 8 share the frame-400 record)
--     ok      the acknowledgement result (1 acked, 0 timed out)
-- A snapshot is taken at the end for boot_test.sh's shared boilerplate
-- (the checker does not use it).
--
-- Env: OUT, FRAMES, SOUND_LOG_ADDR, SOUND_LOGN_ADDR, SOUND_TITLE_FC_ADDR.
--
-- SOUND_DEMO=1 switches to Attract A4/D1's MVS demo-sound leg (the normal
-- cart, `neogeo -bios euro`): the probe taps the 68k's REG_SOUND writes and
-- taps bios_game_dip[6] (the DEMO SOUND enum at 0x10fd8a) and runs three
-- windows:
--   default  epoch 1 and the full epoch 2 cycle with the BIOS's header
--            default (OFF); they must send nothing. A 60-frame D hold at
--            epoch 1 proves MVS ignores D (no confirmation on row 21);
--   on       the full epoch 3 cycle with the DIP set ON; every command is
--            checked against the model (tests/check_sound.py demo mode);
--   game     a real game started after the OFF demo must still sound: the
--            probe coins in and presses Start, then holds A.
-- Records:
--   S <mame_n> <epoch> <demo_fc> <cmd> <user_mode>
--   E <mame_n> <prev_epoch> <epoch> <demo_fc> <dip>
--   D <mame_n> <epoch> <demo_fc> <dip>       a phase/DIP change
--   F <mame_n> <epoch> <demo_fc> <row 21, 40 hex bytes>
--   EXIT <mame_n> <epoch> <demo_fc> <game_frames>
-- Env: OUT, FRAMES, DEMO_EPOCH_ADDR, DEMO_FC_ADDR (plus SOUND_DEMO=1).
local demo_mode = os.getenv("SOUND_DEMO") == "1"

if demo_mode then
  local machine = manager.machine
  local cpu = machine.devices[":maincpu"]
  local sp = cpu.spaces["program"]
  local out = os.getenv("OUT")
  local run_len = tonumber(os.getenv("FRAMES") or "13000")
  local epoch_addr = tonumber(os.getenv("DEMO_EPOCH_ADDR") or "0")
  local fc_addr = tonumber(os.getenv("DEMO_FC_ADDR") or "0")
  local GAME_DIP = 0x10fd84 + 6       -- bios_game_dip[6]: enum DIP #0
  local USER_MODE = 0x10fdaf          -- bios_user_mode
  local DIP_ON, DIP_OFF = 0, 1        -- "ON" is enum index 0, "OFF" 1
  local f = assert(io.open(out, "w"))
  local n, in_cart = 0, 0
  local joy = machine.ioport.ports[":edge:joy:JOY1"]
  local coin_port = machine.ioport.ports[":AUDIO_COIN"]
  local coin = coin_port and coin_port.fields["Coin 1"]
  local start_port = machine.ioport.ports[":edge:joy:START"]
  local start = start_port and start_port.fields["1 Player Start"]

  -- Attract D1 / high-score boards Task B4: fix row 21 as text. The
  -- title's text tiles are TITLE2_ROW_BASE + title2_idx[char] *
  -- TITLE2_NPROF + title2_rprof[left] (build/title_font.h).
  local vram = emu.item(machine.devices[":spritegen"].items["0/m_videoram"])
  local FIXMAP = 0x7000
  local TITLE2_ROW_BASE = 512
  local TITLE2_NPROF = 21
  -- tools/generate_srom.py's TITLE2_CHARS in tile-index order: star, heart,
  -- space, the FONT57 punctuation/digits/letters and '_'.
  local TITLE2_CHARS = "\1\2 !%&'()+,-./0123456789:<=>?ABCDEFGHIJKLMNOPQRSTUVWXYZ_"

  local function vread(a) return vram:read(a) end

  local function row_text(row)
    local s = ""
    for c = 0, 39 do
      local tile = vread(FIXMAP + c * 32 + row) & 0xfff
      local ch = tile
      if tile >= TITLE2_ROW_BASE then
        local idx = math.floor((tile - TITLE2_ROW_BASE) / TITLE2_NPROF)
        ch = TITLE2_CHARS:byte(idx + 1) or 32
      end
      if ch < 32 or ch > 126 then ch = 32 end
      s = s .. string.char(ch)
    end
    return s
  end

  local function hex40(s)
    local out = ""
    for i = 1, #s do
      out = out .. string.format("%02x", string.byte(s, i))
    end
    return out
  end

  local function u8a(a) return sp:read_u8(a) end
  local function u16a(a) return sp:read_u16(a) end

  local phase = "default"             -- default -> on -> game
  local prev_ep = -1
  local game_stage = "coin"           -- coin -> wait -> start -> play
  local coin_n = 0
  local start_n = 0
  local game_frames = 0
  local d_hold_done, d_hold_until = false, 0
  local last_row21 = nil

  -- every command the 68k sends goes through REG_SOUND (0x320000). The tap
  -- sees the 68k write, not the Z80's `cmd|0x80` ack, so it is the command
  -- stream itself (4..9; the entry's sound_reset 3 is ignored). The phase
  -- is included because the coin re-enters the cart at main_mvs_title and
  -- resets the demo epoch to 1 again (the post-coin title's demo).
  local function on_sound(offset, data, mask)
    -- REG_SOUND is a byte port; the 68k's move.b reaches the tap as a
    -- 16-bit value with the byte in both halves (0x0404 for fire).
    local cmd = data & 0xff
    if offset >= 0x320000 and offset <= 0x320001 and cmd >= 4 and cmd <= 9 then
      local ep = epoch_addr ~= 0 and u16a(epoch_addr) or 0
      local fc = fc_addr ~= 0 and u16a(fc_addr) or 0
      f:write(string.format("S %d %s %d %d %d %d\n", n, phase, ep, fc, cmd,
                            u8a(USER_MODE)))
    end
    return data
  end
  _G.__sound_demo_tap = sp:install_write_tap(0x320000, 0x320001, "sound",
                                             on_sound)

  local function quit()
    machine.video:snapshot()
    f:write(string.format("EXIT %d %d %d %d\n", n,
                          epoch_addr ~= 0 and u16a(epoch_addr) or 0,
                          fc_addr ~= 0 and u16a(fc_addr) or 0,
                          game_frames))
    f:write(string.format("pc_in_cart=%d frames=%d\n", in_cart, n))
    f:close()
    machine:exit()
  end

  local function tick()
    n = n + 1
    if in_cart == 0 and cpu.state["PC"].value >= 0x100000 then in_cart = 1 end
    if in_cart == 0 then
      if n >= run_len then quit() end
      return
    end
    local ep = epoch_addr ~= 0 and u16a(epoch_addr) or 0
    local fc = fc_addr ~= 0 and u16a(fc_addr) or 0
    local um = u8a(USER_MODE)
    -- The MVS BIOS leaves 0x5555/0xaaaa garbage in the cart's .bss until
    -- its ~280-frame clear (lessons.md, 2026-10-18): 21845 epoch/frames
    -- must not be mistaken for a demo restart. The demo's epochs are small
    -- and its full cycle is 3245 frames.
    if ep < 1 or ep > 100 or fc > 3300 then
      if n >= run_len then quit() end
      return
    end
    if ep ~= prev_ep then
      f:write(string.format("E %d %d %d %d %d\n", n, prev_ep, ep, fc,
                            u8a(GAME_DIP)))
      prev_ep = ep
    end
    -- Attract D1: fix row 21 (the prompt) on change, so the checker can
    -- prove an MVS D press never writes the confirmation.
    local row21 = row_text(21)
    if row21 ~= last_row21 then
      f:write(string.format("F %d %d %d %s\n", n, ep, fc, hex40(row21)))
      last_row21 = row21
    end
    if phase == "default" then
      -- The operator's DIP default is OFF (the ROM header): leave the
      -- BIOS's copy alone, so epoch 1 and the full epoch-2 cycle run with
      -- the default. A 60-frame D hold at epoch 1 proves MVS ignores D.
      if not d_hold_done and ep == 1 and fc >= 300 then
        d_hold_done = true
        d_hold_until = n + 60
        if joy then joy.fields["P1 D"]:set_value(1) end
      end
      if d_hold_until > 0 and n >= d_hold_until then
        if joy then joy.fields["P1 D"]:set_value(0) end
        d_hold_until = 0
      end
      if ep >= 3 then
        phase = "on"
        sp:write_u8(GAME_DIP, DIP_ON)
        f:write(string.format("D %d %d %d %d\n", n, ep, fc, DIP_ON))
      end
    elseif phase == "on" then
      -- keep DEMO SOUND ON: the BIOS may still be writing its copy early
      -- in the cart, so rewrite it until the demo is well past its first
      -- sound (frame 140); after that it is never touched again.
      if fc < 160 then sp:write_u8(GAME_DIP, DIP_ON) end
      if ep >= 4 then
        phase = "game"
        sp:write_u8(GAME_DIP, DIP_OFF)
        coin_n = n
        game_stage = "coin"
        f:write(string.format("D %d %d %d %d\n", n, ep, fc, DIP_OFF))
      end
    elseif phase == "game" then
      sp:write_u8(GAME_DIP, DIP_OFF)
      -- The MVS needs a credit before Start. Inserting the coin makes the
      -- BIOS re-enter the cart at main_mvs_title (the post-coin title):
      -- .bss is reset, the demo restarts at epoch 1, and that title is
      -- where Start begins the game. Wait for that re-entry, then press
      -- Start (the MVS input helper's 5-frame holds).
      if game_stage == "coin" then
        if coin then
          coin:set_value((n >= coin_n and n < coin_n + 5) and 1 or 0)
        end
        if n >= coin_n + 10 then game_stage = "wait" end
      elseif game_stage == "wait" then
        if coin then coin:set_value(0) end
        if ep <= 1 then           -- the post-coin title's demo, epoch 1
          game_stage = "start"
          start_n = n
        end
      elseif game_stage == "start" then
        if start then
          start:set_value((n >= start_n and n < start_n + 5) and 1 or 0)
        end
        if n >= start_n + 5 then
          game_stage = "play"
          if start then start:set_value(0) end
        end
      end
      if um == 2 then
        if joy then joy.fields["P1 A"]:set_value(1) end
        game_frames = game_frames + 1
        if game_frames >= 90 then quit() return end
      end
    end
    if n >= run_len then quit() end
  end

  if emu.add_machine_frame_notifier then
    _G.__sound_demo = emu.add_machine_frame_notifier(tick)
  else
    emu.register_frame(tick)
  end
  return
else
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
      -- AND the first logged command is one of 4..9 (garbage can pass the
      -- two numeric gates at some addresses — the M7 Task 2 game log
      -- shifted the BSS layout — but no garbage byte is ever 4..9).
      -- tf must be a live title frame (1..1000), not the zero MAME writes
      -- before the cart's first title frame or the BIOS's 0x5555 garbage.
      if cnt <= 32 and tf >= 1 and tf <= 1000 then
        -- check the first record's command byte (log_addr + 2): a real
        -- title send, or the log is still empty (cnt == 0)
        local first_cmd = sp:read_u8(log_addr + 2)
        if cnt == 0 or (first_cmd >= 4 and first_cmd <= 9) then
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
end
