-- flow_probe.lua: the M6 flow boot-test (AES Task 1 legs and the MVS Task 2
-- legs).
--
-- AES (modes flow / flow-restart): drives the NORMAL cart through the title
-- -> game -> GAME OVER -> title flow and proves the state machine and the
-- title's drawing. The probe overrides the Start window to MAME frames
-- 1200..1204 (SG_BEGIN), so the title runs for over a second before a game
-- begins — enough to sample the title (proof a), the Start (proof b), the
-- Up-held game to GAME OVER, and the return to the title (proof c). A second
-- run (FLOW_RESTART=1) presses A at GAME OVER + 60 and proves the A-restart
-- (proof d).
--
-- MVS (modes flow-mvs / flow-mvs-start / flow-mvs-norestart, M6 Tasks 2-4):
-- runs the same NORMAL cart under `neogeo -bios euro -cart1 esrg`.
-- mvs_input.lua holds "Coin 1" on MVS_COIN..+4 (1500, the confirmed default)
-- and "1 Player Start" on MVS_START..+4 (-100: never, or 1800 for the
-- -start leg). The probe writes, every frame, the MVS BIOS bytes
-- bios_mvs_flag (0x10FD82) and bios_compulsion_timer (0x10FDDA, BCD seconds)
-- plus hud_framecnt; nothing else. No AES joypad fields are touched: the
-- :ctrl1:joy:* ports do not exist on the MVS machine, and pressed "P1
-- A".."P1 D" from a shared probe would throw in the MVS legs. The
-- flow-mvs-norestart leg (M6 Task 4) plays the game on top: it holds P1 Up
-- from the first game frame through the :edge:joy:JOY1 port, taps P1 A at
-- GAME OVER + 60, reads the cart's rules.lives / rules.game_over bytes (and
-- bios_player_mod1) every game frame, and samples the title rows after the
-- return — proving that on MVS the A-restart never runs and the 295-frame
-- return still happens.
--
-- The MVS legs also sample the title's fix rows (M6 Task 3) every 6 frames
-- in two windows: 900..1499 (the plain main() title before a coin — row 9
-- must blink INSERT COIN, rows 4/6/8 stay blank) and 1530..3300 (the
-- post-coin main_mvs_title() title — row 9 blinks PRESS START, row 28 cols
-- 19..20 carry the BCD timer's digits, compared with the timer byte read
-- from RAM in the same frame).
--
-- Output:
--   I <n> <fc> <cur> <chg> <mod1>   every frame, AES (MAME n, cart
--                                   game-session fc = hud_framecnt, the
--                                   joypad, and the BIOS player_mod1 byte)
--   M <n> <fc> <flag> <timer>       every frame, MVS (bios_mvs_flag and the
--                                   compulsion timer, both hex)
--   R <n> <fc> <lives> <go> <mod1>  every game frame, the Task 4 leg: the
--                                   cart's rules.lives / rules.game_over
--                                   bytes and bios_player_mod1 (hex)
--   F <n> <fc>                      a fix-row read follows (all 10 rows)
--   W <r> <40 chars>                fix row r decoded (tile = ASCII)
--   Z <n> <fc> <nonzero>            the number of game sprite slots with
--                                   SCB3 height != 0 (must be 0 on the title)
--   V <n> <fc> <scb1tile>           the dome's SCB1 row-0 tile (the view; the
--                                   title must turn it at least 5 times)
--   T <n> <fc> <page> <t> <cred>    every frame, M6 Task 6: the cart's
--                                   title_page / title_t (RAM) and the
--                                   credits value (flow_entry, RAM)
--   L <n> <fc> <valid> <level>      every title frame, M6 Task 7: the
--                                   cart's flow_level_valid and flow_level
--                                   (the backup-RAM bytes, RAM)
--   G <n> <fc> <rules_level> <mis_level> every game frame, M6 Task 7: the
--                                   rules.level / mis.level bytes (RAM)
--   C <n> <fc>                      a title frame's dome SCB2/3/4 dump and
--                                   snapshot follow (M6 Task 6)
--   D <fc> <c> <scb2> <scb3> <scb4> one dome column (11 lines per C block)
--   GO <n> <fc>                     GAME OVER (row 7 text) first seen
--   SNAP <n> <fc>                   a snapshot was taken this frame
--   EXIT <n> <fc> <mod1>            the exit marker with the last mod1
-- Env: OUT, FRAMES (MAME frames to run), HUD_FRAMECNT_ADDR / FLOW_FRAMECNT_ADDR
-- (0 disables the exact fc), SG_BEGIN/SG_END (1200..1204), FLOW_RESTART (0:
-- proof c; 1: proof d, A at GAME OVER + 60); for the MVS legs: MVS_COIN
-- (1500) and MVS_START (-100 or 1800); for the M6 Task 4 leg: FLOW_NORESTART
-- (1: press A at GAME OVER and prove it does nothing on MVS) and
-- FLOW_RULES_ADDR (the static `rules`, for the lives/game_over reads).
-- M6 Task 6 env: FLOW_PAGES (1: the no-Start page-turn run, AES with the
-- title from ~frame 477 to the 8->0 wrap at ~3132: FRAMES must be >= 3200),
-- FLOW_PAGES_C (1: an MVS run that taps C at MVS_C_FRAMES (450) and
-- MVS_C_FRAMES+100 (550) to prove the manual page turn), MVS_C_FRAMES (the
-- first C tap), FLOW_PAGE_ADDR / FLOW_T_ADDR / FLOW_ENTRY_ADDR (the cart's
-- title_page / title_t / flow_entry BSS addresses, from nm; 0 disables the
-- exact page/t reads) and FLOW_DOME_SNAP (1: dump the dome's SCB words and
-- snapshot at the title-frame events the checker keys on).
-- M6 Task 7 env: FLOW_LEVEL (1: the level-select run, AES, no Start until
-- frame 1400; B tapped on 1000/1100/1200/1300, Start on 1400), FLOW_RETURN
-- (1: the no-B flow run that proves the GAME OVER return opens HIGH
-- SCORES), FLOW_LEVEL_ADDR (the cart's flow_level backup-RAM byte: the
-- probe reads the VALID marker at this address and the level at +1, from
-- nm; 0 disables the L records), FLOW_RULES_ADDR (the static `rules`, for
-- rules.level @ +0) and FLOW_MIS_ADDR (the static `mis`, for mis.level
-- @ +73).
-- M6 Task 9 env: FLOW_BEST (1: the best-mvs mode's game leg — the MVS run
-- that plays the centred game to GAME OVER and records mis.score10 / the
-- flow_best backups), FLOW_BEST_ADDR (the cart's flow_best backup-RAM
-- table, from nm; 0 disables the B records), FLOW_MIS_ADDR (also the
-- score10 read: mis + 76, the m68k layout checked against the ELF's
-- DWARF), FLOW_BEST_RETURN (1: the AES flow leg, in which the probe reads
-- and records the best table on the returned title so the checker can
-- prove the Up-held game's score landed in NORMAL).
-- M6 Task 10 env: FLOW_BEST_AES (1: the best-aes mode's game leg — the
-- AES run that plays the centred game to GAME OVER and records
-- mis.score10 and the card-log answers (the cart's card_save_best calls:
-- on a fresh card 0x81 then FORMAT 0 then SAVE 0), then the post-return
-- title rows), FLOW_CARDLOG_ADDR (the cart's card_log BSS words, from
-- nm; 0 disables the A records), and BEST_NOCARD (1: an AES run with no
-- -memcard — the load answers 0x80, the title's row 7 reads "0", and a
-- game to GAME OVER still keeps the score in backup RAM for that run).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "11000")
local framecnt_addr = tonumber(os.getenv("FLOW_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")
local restart = os.getenv("FLOW_RESTART") == "1"
local mvs_mode = os.getenv("FLOW_MVS") == "1"
-- the M6 Task 4 leg: press A at GAME OVER on MVS and prove it does not
-- restart (flow-mvs-norestart); boot_test.sh passes the static `rules`
-- address (found by nm) so the probe can read rules.lives @ +78 and
-- rules.game_over @ +82 (the m68k layout, checked against the ELF's DWARF).
local norestart = os.getenv("FLOW_NORESTART") == "1"
local rules_addr = tonumber(os.getenv("FLOW_RULES_ADDR") or "0")
-- M6 Task 6: the no-Start pages run, the C-tap run, and the title state's
-- RAM addresses (title_page / title_t / flow_entry, found by nm).
local pages_run = os.getenv("FLOW_PAGES") == "1"
local pages_c_run = os.getenv("FLOW_PAGES_C") == "1"
local mvs_c_frames = tonumber(os.getenv("MVS_C_FRAMES") or "450")
local page_addr = tonumber(os.getenv("FLOW_PAGE_ADDR") or "0")
local t_addr = tonumber(os.getenv("FLOW_T_ADDR") or "0")
local entry_addr = tonumber(os.getenv("FLOW_ENTRY_ADDR") or "0")
local dome_snap = os.getenv("FLOW_DOME_SNAP") == "1"
-- M6 Task 7: the level-select run (B taps + Start) and the no-B return
-- run; the RAM addresses of flow_level (the backup-RAM byte), rules.level
-- (rules + 0) and mis.level (mis + 73 — the m68k layout, checked against
-- the ELF's DWARF).
local level_run = os.getenv("FLOW_LEVEL") == "1"
local return_run = os.getenv("FLOW_RETURN") == "1"
local level_addr = tonumber(os.getenv("FLOW_LEVEL_ADDR") or "0")
local rules_addr2 = tonumber(os.getenv("FLOW_RULES_ADDR") or "0")
local mis_addr = tonumber(os.getenv("FLOW_MIS_ADDR") or "0")
-- M6 Task 9: the best-table records (B lines) and the MVS best-mode run
local best_run = os.getenv("FLOW_BEST") == "1"
local best_return = os.getenv("FLOW_BEST_RETURN") == "1"
local best_addr = tonumber(os.getenv("FLOW_BEST_ADDR") or "0")
-- M6 Task 10: the AES best-mode run (FLOW_BEST_AES) and the card-log
-- reads (A lines: the answers the cart's card calls left in card_log)
local best_aes_run = os.getenv("FLOW_BEST_AES") == "1"
local no_card = os.getenv("BEST_NOCARD") == "1"
local cardlog_addr = tonumber(os.getenv("FLOW_CARDLOG_ADDR") or "0")
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")
local MS = dofile((os.getenv("REPO") or ".") .. "/scripts/mis_seed.lua")
local MI = dofile((os.getenv("REPO") or ".") .. "/scripts/mvs_input.lua")

local BI, CHG = 0x10fd96, 0x10fd97
local MOD1 = 0x10fdb6
local MVS_FLAG, COMP_TIMER = 0x10fd82, 0x10fdda
local FR = 0x7000
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
local DOME0, DOME_COLS = S.DOME_SPRITE, S.DOME_COUNT

local f = assert(io.open(out, "w"))
local n, in_cart, rec = 0, 0, 0
local p1_go, mvs_go, mvs_go_n, snap_taken = nil, nil, nil, false
local a_pressed = false
-- M6 Task 10: the best-aes leg's card-log sampler (every frame during
-- the GAME OVER window — the BIOS card calls span several MAME frames —
-- and the post-return title sampling bookkeeping)
local card_ans_seen_n = nil
local next_aes_nrs = 0
-- M6 Task 7: the level-select run's B taps and the Start press. B is held
-- for one MAME frame on 1000/1100/1200/1300 (bios_p1change latches it),
-- then Start on 1400..1404 (the flow probe's SG override). The returned
-- title of the return run is page 1, so the Start press that follows only
-- happens in the level run.
local lvl_next_tap = 0
local lvl_taps = { [1000] = true, [1100] = true, [1200] = true, [1300] = true }
-- the M6 Task 4 leg's post-return title sampler (see the MVS branch)
local next_nrs = 0
-- the M6 Task 6 legs' per-page first-frame and next-turn bookkeeping: the
-- checker keys the page PINs and the C taps on these MAME frames
-- (pages_run: title_page's first 1 / first 2 / first 8 / first 0-after-8;
-- pages_c_run: each C tap's new-page title frame). dome_frame holds the
-- MAME frame the last C-block dome dump was taken at, so the checker can
-- compare two page-0 dump blocks by their event.
local page_pin, next_turn = {}, nil
local dome_wrapped
local dome_frame = 0
local dome_snap0, dome_snap1, dome_snap2
local next_dome_snap, c_tap_next = 0, 0
-- the MVS P1 joystick (the AES `joy` port below does not exist there); the
-- Task 4 leg drives "P1 Up" and "P1 A" through it (mvs_input.lua's holds
-- never touch the joystick fields).
local mvs_joy = machine.ioport.ports[":edge:joy:JOY1"]

-- VRAM is read (and, by the leftover probe, written) through MAME's own copy
-- of it, never through the LSPC registers at 0x3c0000/2: writing the address
-- register from a frame callback changes the cart's VRAM pointer under it, and
-- the cart's next writes land at the probe's address (it zeroed title rows).
local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(a)
    return vram:read(a)
end
local function vwrite(a, v)
    vram:write(a, v)
end

local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec
end

-- M6 Task 6: the cart's title state, read straight from its BSS (the
-- addresses come from nm, like hud_framecnt). title_page 0..8, title_t
-- the frames spent on this page, credits the value the cart draws row 9
-- with — the same derivation as src/flow.c's title_credits(): 0 on AES,
-- 1 on MVS before a coin (flow_entry 0), 2 after a coin (flow_entry 1),
-- so the checker's model call gets exactly the cart's credits byte. Any
-- address may be 0 (missing or irrelevant): the caller falls back.
local function title_state()
    local page, t, cred = nil, nil, nil
    if page_addr ~= 0 then page = sp:read_u8(page_addr) end
    if t_addr ~= 0 then t = sp:read_u16(t_addr) end
    if entry_addr ~= 0 then
        local mvs = sp:read_u8(MVS_FLAG) == 0x80
        cred = (not mvs) and 0 or (sp:read_u8(entry_addr) == 0 and 1 or 2)
    end
    return page, t, cred
end

-- M6 Task 9: the cart's backup-RAM best table (flow_best, 18 bytes from
-- nm: magic u32, score10 u32[3], sum u16, all big-endian), as the three
-- scores plus the raw bytes — the checker rebuilds and validates the
-- table (magic/sum) exactly as src/best.c does, and compares the scores
-- against the drawn rows' best values.
local function best_rec(n, fc)
    if best_addr == 0 then return end
    local b0 = sp:read_u32(best_addr + 4)
    local b1 = sp:read_u32(best_addr + 8)
    local b2 = sp:read_u32(best_addr + 12)
    local hex = {}
    local i
    for i = 0, 17 do
        hex[#hex + 1] = string.format("%02x", sp:read_u8(best_addr + i))
    end
    f:write(string.format("B %d %d %d %d %d %s\n", n, fc, b0, b1, b2,
                          table.concat(hex)))
end

-- M6 Task 10: the card-log pairs — the commands and answers the cart's
-- card calls left in card_log (u16s: command, answer, ... , 0
-- terminated), as <cmd>:<ans> pairs joined by commas. Read from RAM the
-- frame after a save (the cart's GAME OVER update + card calls ran in
-- the cart's frame; the probe reads at the START of the MAME frame, so
-- the answers appear one frame later). The checker keys run 1's fresh
-- card on "2:81" then "0:0" then "3:0" (LOAD 0x81, FORMAT 0, SAVE 0)
-- and run 3's no-card runs on "2:80" ("3:80" for the save).
local function cardlog_rec(n, fc)
    if cardlog_addr == 0 then return end
    local pairs = {}
    local i
    for i = 0, 6, 2 do
        local cmd = sp:read_u16(cardlog_addr + i * 2)
        local ans = sp:read_u16(cardlog_addr + (i + 1) * 2)
        if cmd == 0xffff then break end
        pairs[#pairs + 1] = string.format("%x:%x", cmd, ans)
    end
    f:write(string.format("A %d %d %s\n", n, fc, table.concat(pairs, ",")))
end

-- one dome column's SCB words (the checker's "chain rebuilt, not half a
-- dome" proof, M6 Task 6): <scb2> <scb3> <scb4>
local function dome_col(nn, c)
    f:write(string.format("D %d %d %04x %04x %04x\n", nn, c,
                          vread(SCB2 + DOME0 + c), vread(SCB3 + DOME0 + c),
                          vread(SCB4 + DOME0 + c)))
end

-- a title frame's full C block: the MAME frame, the page the dome dump
-- was taken on (read from the cart's title_page RAM right before), the 11
-- dome columns' SCB words, and a snapshot. The checker keys the page PINs
-- on the frame; the snapshot is the dome-pixels proof.
local function dome_dump(nn, fc)
    local c
    local page = page_addr ~= 0 and sp:read_u8(page_addr) or -1
    f:write(string.format("C %d %d %d\n", nn, fc, page))
    for c = 0, DOME_COLS - 1 do
        dome_col(nn, c)
    end
    machine.video:snapshot()
    f:write(string.format("SNAP %d %d\n", nn, fc))
end

-- count the game sprite slots (the ship, missiles and explosions, the
-- broken overlays, the radar) whose SCB3 height is non-zero.
local ranges = {
    { S.SHIP_SPRITE, S.SHIP_SPRITE + S.SHIP_COUNT - 1 },
    { S.MIS_BEHIND_SPRITE, S.MIS_BEHIND_SPRITE + S.MIS_BEHIND_COUNT - 1 },
    { S.MIS_FRONT_SPRITE, S.MIS_FRONT_SPRITE + S.MIS_FRONT_COUNT - 1 },
    { S.EXPL_SPRITE, S.EXPL_SPRITE + S.EXPL_COUNT - 1 },
    { S.BROKEN_SLOT_BASE, S.BROKEN_SLOT_AFTER - 1 },
    { S.RADAR_SPRITE, S.RADAR_SPRITE + S.RADAR_COUNT - 1 },
}
local function nonzero_slots()
    local count, i, s
    count = 0
    for i = 1, #ranges do
        local lo, hi = ranges[i][1], ranges[i][2]
        for s = lo, hi do
            if (vread(SCB3 + s) & 0x3f) ~= 0 then
                f:write(string.format("NZ %d %d %04x %04x\n", n, s,
                                      vread(SCB3 + s), vread(SCB4 + s)))
                count = count + 1
            end
        end
    end
    return count
end

local function read_row_text(row)
    local line = ""
    local c
    for c = 0, 39 do
        local tile = vread(FR + c * 32 + row) & 0x0fff
        -- the HUD icons are S ROM tiles 128/129 (colour index 1): write
        -- them as <NN> escapes so the row stream stays ASCII (a raw 0x80
        -- byte would not survive a UTF-8 text read); the checker decodes
        if tile >= 0x80 and tile <= 0xff then
            line = line .. string.format("<%d>", tile)
        elseif tile > 0xff then
            line = line .. "?"
        else
            line = line .. string.char(tile)
        end
    end
    return line
end

-- the title's row 3, as tests/check_flow.py builds it: since the M8 art
-- pass it is the logo's second tile row — src/title.h's LOGO_FIRST 130,
-- LOGO_COLS 16 from LOGO_COL 12 (rows from LOGO_ROW 2), so tiles 146..161
-- in read_row_text's <NN> escapes. The pages / pages-c legs' is_title
-- gate (reading this one row is safe: it is read alone, before any other
-- row).
local ROW3 = string.rep(" ", 12)
for c = 0, 15 do ROW3 = ROW3 .. string.format("<%d>", 130 + 16 + c) end
ROW3 = ROW3 .. string.rep(" ", 12)
-- the title gate: pages 1..8 are unambiguous (only the cart's title code
-- ever writes 1..8 to title_page RAM); page 0 is ambiguous pre-main (the
-- BIOS's RAM clear leaves 0 in the byte), so the drawn row 3 (the logo,
-- which only the title draws) must confirm it. Reading row 3 alone is
-- safe: it is read in isolation, before any other row of a sweep.
local function is_title()
    if page_addr ~= 0 then
        local p = sp:read_u8(page_addr)
        if p >= 1 and p <= 8 then return true end
        if p == 0 then return read_row_text(3) == ROW3 end
        return false
    end
    return read_row_text(3) == ROW3
end

local function dump_fix(nn, fc)
    local row, c
    f:write(string.format("F %d %d\n", nn, fc))
    -- reads go through MAME's own videoram item (84f2d6b), which touches
    -- no 68k-visible state and reads clean in every order — the row order
    -- below is defensive belt (the old LSPC-register reads corrupted the
    -- read-back of the same columns in later rows of a sweep; the stock
    -- probe has the ordering too, its checker just never read row 9). The
    -- checked rows are read first anyway: row 3 (the name row) is the
    -- FIRST row read, and row 9 (the prompt) before any later non-space
    -- row. The game frames' HUD rows (24, 26, 28) hold non-space tiles
    -- (the icons at cols 32..37, the score at 17..21), so they are read
    -- LAST, high row first (29, 28, 27, 26, 25, 24): a non-space row can
    -- only corrupt rows read AFTER it, and everything it could corrupt is
    -- already captured. Rows 28/29 on the title are the MVS countdown's
    -- own pair (blank on AES).
    for row = 0, 2 do
        f:write(string.format("W %d %s\n", row, read_row_text(row)))
    end
    line_3 = read_row_text(3)
    f:write(string.format("W 3 %s\n", line_3))
    for row = 4, 8 do
        f:write(string.format("W %d %s\n", row, read_row_text(row)))
    end
    line_9 = read_row_text(9)
    f:write(string.format("W 9 %s\n", line_9))
    for row = 10, 23 do
        f:write(string.format("W %d %s\n", row, read_row_text(row)))
    end
    for row = 29, 24, -1 do
        f:write(string.format("W %d %s\n", row, read_row_text(row)))
    end
end

local function is_go_text()
    local want = "GAME OVER"
    local c
    for c = 1, #want do
        local tile = vread(FR + (15 + c - 1) * 32 + 7) & 0x0fff
        if tile ~= string.byte(want, c, c) then
            return 0
        end
    end
    return 1
end

-- the title: sampled every 6 MAME frames while fc == 0, the cart's title is
-- drawn, and before Start. The dome's SCB1 first-column row-0/1 tiles are
-- the per-view signature (the title turns the dome); nonzero gives the game
-- slots' SCB3 heights (must all be 0). The samples are gated on row 3 ==
-- "E-SRG" by the CHECKER (tests/check_flow.py's title_samples), not by a
-- probe-side is_title pre-read: reading the row-3 cells first corrupts the
-- later rows' read-back in MAME (see title_sample).
local title_next = 0
-- the MVS title rows (M6 Task 3): sampled every 6 MAME frames in the two
-- windows the checker keys on, 300..590 (the plain main() title's page 0
-- before a coin: with no BIOS logo the title starts at MAME frame ~299) and 1530..3300 (the post-coin main_mvs_title() title, whose row 28
-- shows the compulsion timer's digits).
local title_mvs_next = 0
local MVS_PRE_LO, MVS_PRE_HI = 300, 590
local MVS_POST_LO, MVS_POST_HI = 1530, 3300
local function title_sample(nn, fc)
    -- the fix rows are read FIRST, before the Z/V slot reads below: in
    -- MAME, LSPC FIXMAP reads of one row with non-space tiles corrupt the
    -- read-back of the same columns in later rows of a sweep (row 3's
    -- "E-SRG" zeroes cols 17..21 of rows 4..9; the stock probe has this
    -- corruption too — its checker only read rows 3 and 9, which sit on
    -- different columns, so it never saw it). Reading the checked rows
    -- first keeps the checker on what the cart actually drew.
    dump_fix(nn, fc)
    local nonzero = nonzero_slots()
    local t0 = vread(SCB1 + DOME0 * 64)        -- row 0, column 0
    local t1 = vread(SCB1 + DOME0 * 64 + 2)    -- row 1, column 0
    local sig = (t0 << 16) | t1
    -- M6 Task 6: the title state, read from the cart's BSS in the same
    -- frame, so the checker can compare the drawn rows against
    -- tests/title_model.py's rows for exactly this (page, level, t,
    -- credits) — the whole proof 1 tens thousands of times over.
    local page, t, cred = title_state()
    f:write(string.format("T %d %d %d %d %d\n", nn, fc,
                          page or -1, t or -1, cred or -1))
    -- M6 Task 7: the title's level bytes (flow_level_valid @ +0, flow_level
    -- @ +1), read from RAM in the same frame — the checker applies the
    -- cart's own sanitize (a valid marker with an out-of-range level, or
    -- no marker at all, reads NORMAL) and gates the drawn row 6 on it.
    if level_addr ~= 0 then
        f:write(string.format("L %d %d %d %d\n", nn, fc,
                              sp:read_u8(level_addr),
                              sp:read_u8(level_addr + 1)))
    end
    -- M6 Task 9: the best table in the same frame, so the checker can
    -- compare the drawn rows' best values (page 0 row 7, page 1's rows)
    -- against exactly what the cart had.
    best_rec(nn, fc)
    -- M6 Task 10: the card-log answers in the same frame (the first-entry
    -- LOAD ran before the first title frame, so the answers are set) —
    -- the checker keys run 1's fresh-card "2:81", run 2's "2:0" and run
    -- 3's no-card "2:80" on the title frames.
    if best_aes_run then
        cardlog_rec(nn, fc)
    end
    f:write(string.format("Z %d %d %d\n", nn, fc, nonzero))
    f:write(string.format("V %d %d %08x\n", nn, fc, sig))
end
local function tick()
    n = n + 1
    if in_cart == 0 and cpu.state["PC"].value >= 0x100000 then
        in_cart = 1
    end
    if mvs_mode then
        -- the M6 Task 2 MVS legs: the coin and/or Start holds via the MVS
        -- ports, and every frame's M <n> <fc> <flag> <timer> record. The
        -- M records are written from frame 1 (not gated on in_cart): the
        -- BIOS work-RAM bytes are readable during the whole boot, and the
        -- pre-cart fc == 0 rows are part of the proof (the timer reads 0
        -- before the coin, 0x30 right after). The M6 Task 4 leg
        -- (flow-mvs-norestart) also plays the game: P1 Up held from the
        -- first game frame (the Up-held game: GAME OVER at fc 8188 under
        -- Task 1's seed at SG_BEGIN 1200; 6509 before it), A
        -- tapped at GAME OVER + 60, and the rules' lives/game_over bytes
        -- read every game frame so the checker can prove A did not
        -- restart. All the MVS driving goes through mvs_input.lua (the
        -- "P1 Up"/"P1 A" fields live in the :edge:joy:JOY1 port, which
        -- mi_apply also owns) — its hold logic never touches the joystick
        -- fields, so the probe drives them directly.
        MI.mi_apply(n)
        -- M6 Task 6, flow-pages-c (MVS): tap P1 C, through the same
        -- :edge:joy:JOY1 port the Task 4 leg drives (mvs_input.lua only
        -- owns Coin and Start). On MVS the cart's title starts at MAME
        -- frame ~299 (no BIOS logo), so page 0 spans ~299..592: a C tap at
        -- 450 turns 0 -> 1, at 550 turns 1 -> 2 — "the page goes 0 -> 1 -> 2 on
        -- those frames" exactly as the task says (on AES the title starts
        -- at ~477 and page 0 is already over at 900). The taps are applied
        -- and released on the next frame, and the checker gates its PIN
        -- frames on the T records' page changes.
        if pages_c_run and mvs_joy then
            if n >= c_tap_next then
                local tapping = (n == mvs_c_frames or n == mvs_c_frames + 100)
                mvs_joy.fields["P1 C"]:set_value(tapping and 1 or 0)
                if tapping then
                    c_tap_next = n + 1      -- release the tap next frame
                end
            end
        elseif not pages_c_run and mvs_joy and mvs_joy.fields["P1 C"] then
            mvs_joy.fields["P1 C"]:set_value(0)
        end
        if norestart and in_cart and framecnt() >= 1 then
            -- drive the joystick directly (the AES `joy` port below does
            -- not exist here): P1 Up from the first game frame, A tapped
            -- at GAME OVER + 60 .. +64 (as the FLOW_RESTART leg's tap).
            if mvs_joy then
                mvs_joy.fields["P1 Up"]:set_value(1)
                local fc = framecnt()
                if mvs_go ~= nil and not a_pressed and fc >= mvs_go + 60
                   and fc <= mvs_go + 64 then
                    mvs_joy.fields["P1 A"]:set_value(1)
                    if fc >= mvs_go + 63 then
                        a_pressed = true
                    end
                else
                    mvs_joy.fields["P1 A"]:set_value(0)
                end
            end
        end
        -- M6 Task 9, the best-mvs game leg: Task 1's seed makes the old
        -- centred game score 0 (no kill), which fails this leg's "a real
        -- score" proof; hold Right and tap A every 11 frames instead, a
        -- deterministic run that does score (the model gives fc 20240,
        -- score 987 at seed 0xadf9). The ship turns right, the fire taps
        -- line up with the missiles it meets. Nothing else is pressed,
        -- and the titles of the other best-mvs legs (runs 2 and 3) get
        -- no input at all.
        if best_run and in_cart and framecnt() >= 1 and mvs_joy then
            local fc = framecnt()
            mvs_joy.fields["P1 Left"]:set_value(0)
            mvs_joy.fields["P1 Up"]:set_value(0)
            mvs_joy.fields["P1 Right"]:set_value(1)
            mvs_joy.fields["P1 Down"]:set_value(0)
            mvs_joy.fields["P1 A"]:set_value(fc <= 20240 and (fc % 11) == 0
                                             and 1 or 0)
        end
        -- the best-mvs game leg's GAME OVER: its score (mis.score10 @
        -- mis+76) and the best table right after the cart's GAME OVER
        -- update, read from RAM in the same frame (the proof's "read
        -- mis.score10 at GAME OVER: it must be > 0"). Gated on mis_addr
        -- and best_addr (which boot_test.sh always sets for best-mvs); the
        -- title-only legs (runs 2 and 3) never reach fc >= 1, so the
        -- snapshot below covers them.
        if best_run and in_cart and n >= 280 and framecnt() >= 1
           and mis_addr ~= 0 and best_addr ~= 0 then
            local fc = framecnt()
            -- Task 1: the floor only has to predate the model's GAME OVER
            -- (fc 20240 under seed 0xadf9 for the scoring game; 24963 was
            -- the RNG_SEED game), so it is well below the first death.
            if mvs_go == nil and fc >= 6000 and is_go_text() == 1 then
                mvs_go = fc
                mvs_go_n = n
                f:write(string.format("GO %d %d\n", n, fc))
                f:write(string.format("SC %d %d %d\n", n, fc,
                                      sp:read_u32(mis_addr + 76)))
                best_rec(n, fc)
                machine.video:snapshot()
                f:write(string.format("SNAP %d %d\n", n, fc))
                snap_taken = true
            end
        end
        -- the best-mvs title-only legs (runs 2 and 3 never start a game):
        -- the first confirmed title frame still snapshots, so boot_test.sh
        -- has a file to copy. (Run 1's title snapshot is superseded by the
        -- GAME OVER one above.)
        if best_run and not snap_taken and n >= 900 and framecnt() == 0
           and is_title() then
            machine.video:snapshot()
            f:write(string.format("SNAP %d %d\n", n, framecnt()))
            snap_taken = true
        end
        -- the best-mvs game leg's post-return title rows: the proof "the
        -- return opens HIGH SCORES — page 1's NORMAL row reads score10 *
        -- 10, and flow_best in RAM is valid and holds it". Sampled every 6
        -- MAME frames from ~the window-expiry frame (GO + 290) while the
        -- game-session counter is 0 (the post-return title). The T record
        -- (page/t/credits, from the cart's BSS) and the L record (the
        -- level pair) let the checker gate the NORMAL-row proof and the
        -- model compare on page 1.
        if best_run and mvs_go ~= nil and framecnt() == 0
           and n >= mvs_go_n + 290 and n >= next_nrs then
            dump_fix(n, 0)
            best_rec(n, 0)
            local page, t, cred = title_state()
            f:write(string.format("T %d 0 %d %d %d\n", n,
                                  page or -1, t or -1, cred or -1))
            if level_addr ~= 0 then
                f:write(string.format("L %d 0 %d %d\n", n,
                                      sp:read_u8(level_addr),
                                      sp:read_u8(level_addr + 1)))
            end
            next_nrs = n + 6
        end
        rec = rec + 1
        f:write(string.format("M %d %d %02x %02x\n", n, framecnt(),
                              sp:read_u8(MVS_FLAG), sp:read_u8(COMP_TIMER)))
        MS.poll(f, n, framecnt())
        -- M6 Task 6: the pages-c run's per-frame title state (the C-turn
        -- proof needs frame resolution, not the 6-frame title_sample
        -- cadence: "the page goes 0 -> 1 -> 2 on those frames, within 2
        -- frames"). Every MAME frame while the cart's main is in and the
        -- session counter is still 0, the cart's page/t/credits are
        -- recorded (the F blocks are skipped — the C-turn proof keys on
        -- these T lines, and the model-row proof belongs to the flow and
        -- flow-pages legs).
        if pages_c_run and in_cart and framecnt() == 0 then
            local page, t, cred = title_state()
            f:write(string.format("T %d 0 %d %d %d\n", n,
                                  page or -1, t or -1, cred or -1))
        end
        -- the M6 Task 4 leg's game-state records: every game frame, the
        -- rules' lives (@ +78), game_over (@ +82) and bios_player_mod1
        -- (the m68k layout of rules_t; boot_test.sh passes
        -- FLOW_RULES_ADDR = nm `rules`), plus the GAME OVER marker when
        -- row 7 first reads it. Gated on n >= 280 like the MVS checker's
        -- mvs_first_game_frame: before the BIOS's RAM clear (and the cart
        -- main's .bss zeroing at ~frame 749) the cart RAM holds the BIOS's
        -- 0x55555555 test fill, which would masquerade as fc >= 1.
        if norestart and in_cart and n >= 280 and framecnt() >= 1
           and rules_addr ~= 0 then
            f:write(string.format("R %d %d %02x %02x %02x\n", n, framecnt(),
                                  sp:read_u8(rules_addr + 78),
                                  sp:read_u8(rules_addr + 82),
                                  sp:read_u8(MOD1)))
            -- Task 1: the MVS game's GAME OVER is at fc 16551 (Start
            -- 1800, seed 0xadf9); this bound only has to predate it,
            -- so keep a safe floor below the 0xACE1 game's 6509
            if mvs_go == nil and framecnt() >= 6480 and is_go_text() == 1 then
                mvs_go = framecnt()
                mvs_go_n = n
                f:write(string.format("GO %d %d\n", n, framecnt()))
                if not snap_taken then
                    machine.video:snapshot()
                    f:write(string.format("SNAP %d %d\n", n, framecnt()))
                    snap_taken = true
                end
            end
        end
        -- the M6 Task 4 leg's post-return title rows: the proof "the title
        -- rows are back by GAME OVER + 600". Sampled every 6 MAME frames
        -- from ~the window-expiry frame (GO + 290) while the game-session
        -- counter is 0 (the post-return title; the checker gates on row 3
        -- == "E-SRG" to skip the BIOS preamble's dirty fix layer).
        if norestart and mvs_go ~= nil and framecnt() == 0
           and n >= mvs_go_n + 290 and n >= next_nrs then
            dump_fix(n, 0)
            next_nrs = n + 6
        end
        -- the M6 Task 3 title rows: sample the rows 9 and 28 every 6 frames
        -- in the two windows the checker keys on (before the coin 900..1499,
        -- after it 1530..3300). Row 9 must alternate INSERT COIN / blank
        -- before the coin and PRESS START / blank after it; row 28 must be
        -- blank before the coin and carry the BCD timer's digits after.
        -- (The Task 4 leg skips these: it plays a game through those
        -- windows and its checker keys on the post-return samples instead.)
        -- The samples carry the T record too (M6 Task 6): the checker
        -- gates page 0's row-9 prompt on the page read in the same frame.
        if not norestart and not pages_c_run and n >= title_mvs_next then
            local in_pre = (n >= MVS_PRE_LO and n <= MVS_PRE_HI)
            local in_post = (n >= MVS_POST_LO and n <= MVS_POST_HI)
            if in_pre or in_post then
                title_sample(n, framecnt())
                title_mvs_next = n + 6
            end
        end
        -- M6 Task 6: the pages-c run's dome dumps at the title-frame page
        -- PINs, gated on fc == 0 and row 3 (is_title) like the pages run.
        -- One dump per page (0, 1, 2), at the first frame of each that the
        -- sampling cursor hits; the checker compares page 2's "all hidden"
        -- columns against page 1's and pages 0/a0's against each other.
        if pages_c_run and dome_snap and dome_snap2 == nil and n >= next_dome_snap
           and n >= 280 and in_cart and framecnt() == 0 then
            if is_title() then
                local page = page_addr ~= 0 and sp:read_u8(page_addr) or -1
                local want_page = dome_snap0 == nil and 0
                    or (dome_snap0 ~= nil and dome_snap1 == nil and 1)
                    or (dome_snap1 ~= nil and 2)
                if page == want_page then
                    dome_dump(n, 0)
                    if dome_snap0 == nil then dome_snap0 = n
                    elseif dome_snap1 == nil then dome_snap1 = n
                    else dome_snap2 = n end
                end
                -- whatever the cart reports (page_addr may be 0 before the
                -- M6 Task 6 build), the first confirmed title frame still
                -- snapshots/dumps, so boot_test.sh always has a file. The
                -- pages-c run gates on `in_cart` (line 442) so this cannot
                -- fire during the BIOS preamble.
                if page_addr == 0 and dome_snap0 == nil and not snap_taken then
                    dome_snap0 = n
                    dome_dump(n, 0)
                end
            end
            next_dome_snap = n + 6
        end
        -- one snapshot at the moment the game begins (boot_test.sh wants a
        -- snapshot file; the Task 4 leg's real GAME OVER snapshot replaces
        -- this one when it fires). Gated on n >= 280 like the R records:
        -- before the BIOS's RAM clear the fc word reads the 0x55555555
        -- test fill (>= 1), and the plain MVS legs' game never starts
        -- before frame 1802 anyway.
        if not snap_taken and n >= 280 and framecnt() >= 1 then
            machine.video:snapshot()
            f:write(string.format("SNAP %d %d\n", n, framecnt()))
            snap_taken = true
        end
        if n >= run_len then
            f:write(string.format("EXIT %d %d %d\n", n, framecnt(),
                                  sp:read_u8(0x10fdb6)))
            f:write(string.format("pc_in_cart=%d frames=%d rec=%d\n",
                                  in_cart, n, rec))
            f:close()
            machine:exit()
            return
        end
        return
    end
    SG.sg_apply(n)
    -- M6 Task 7, the level-select run (AES): B tapped (one frame) on
    -- 1000/1100/1200/1300, always released otherwise — nothing of the
    -- probe's reaches the title except the taps (the task's proof 1).
    -- The Start press at 1400 is SG's own override (SG_BEGIN=1400).
    if level_run and joy then
        if n >= lvl_next_tap then
            local tapping = lvl_taps[n] or false
            joy.fields["P1 B"]:set_value(tapping and 1 or 0)
            if tapping then
                lvl_next_tap = n + 1      -- release the tap next frame
            end
        else
            joy.fields["P1 B"]:set_value(0)
        end
    end
    if in_cart then
        rec = rec + 1
        local fc = framecnt()
        f:write(string.format("I %d %d %d %d %d\n", n, fc, sp:read_u8(BI),
                              sp:read_u8(CHG), sp:read_u8(MOD1)))
        MS.poll(f, n, fc)
        -- M6 Task 10 (the best-aes leg): the card-log read during the
        -- GAME OVER window. The cart's save runs in ITS GAME OVER frame,
        -- but the BIOS card calls take several MAME frames to complete,
        -- so the log is sampled EVERY frame from GO + 2 while the game
        -- session is still running (the 295-frame window) — the LAST
        -- record before the return (fc drops to 0 and the entry's .bss
        -- zeroing wipes card_log) carries the complete save sequence.
        if best_aes_run and card_ans_seen_n ~= nil and n >= card_ans_seen_n
           and n <= card_ans_seen_n + 300 then
            if fc >= 1 then
                cardlog_rec(n, fc)
            end
        end
        -- M6 Task 7: the game's level bytes (the first G at fc 1 is the
        -- proof's "on the first game frame"; the rules' level @ +0 and the
        -- missiles' @ +73, both read from RAM).
        if (level_run or return_run) and fc >= 1 and rules_addr2 ~= 0
           and mis_addr ~= 0 then
            f:write(string.format("G %d %d %d %d\n", n, fc,
                                  sp:read_u8(rules_addr2),
                                  sp:read_u8(mis_addr + 73)))
        end
        -- M6 Task 7, the level-select run: while fc == 0 (the title), the
        -- title's state is recorded EVERY frame — the task's "B on frame
        -- 1000 -> row 6 reads 'HARD' from frame 1002 on (within 2 frames)"
        -- needs frame resolution around the taps. The fix rows are read
        -- every 6 frames as usual (the checker's drawn gates key on the T
        -- records' page-0/t-0 frames), so the L/T lines carry the state
        -- the drawn rows were sampled with — the 6-frame cadence is inside
        -- the checker's "within 8 of the level change" window.
        if level_run and fc == 0 then
            local page, t, cred = title_state()
            f:write(string.format("T %d %d %d %d %d\n", n, fc,
                                  page or -1, t or -1, cred or -1))
            if level_addr ~= 0 then
                f:write(string.format("L %d %d %d %d\n", n, fc,
                                      sp:read_u8(level_addr),
                                      sp:read_u8(level_addr + 1)))
            end
        end
        if fc == 0 then
            -- the title: hold nothing of our own (the probe's game input
            -- never touches the title), sample the title every 6 frames.
            -- The fix rows are read FIRST (no is_title pre-read: that
            -- corrupts later rows' read-back); the checker gates the
            -- samples on row 3 == "E-SRG" to skip the BIOS preamble's
            -- dirty fix layer (is_title's old job, done safely on the
            -- already-dumped rows).
            if n >= title_next then
                title_sample(n, fc)
                title_next = n + 6
            end
            -- M6 Task 10, the best-aes title-only legs (runs 2 and 3 with
            -- no Start pressed): the first confirmed title frame still
            -- snapshots, so boot_test.sh always has a file to copy. (Run
            -- 1's title snapshot is superseded by the GAME OVER one.)
            if best_aes_run and not snap_taken and n >= 900 and fc == 0
               and is_title() then
                machine.video:snapshot()
                f:write(string.format("SNAP %d %d\n", n, framecnt()))
                snap_taken = true
            end
            -- M6 Task 6, flow-pages (AES, no Start): the page-turn
            -- bookkeeping and the dome dumps at the page PINs. The PINs are
            -- the first title frame of page 1 / 2 / 8 / 0-after-8, read
            -- from the cart's title_page RAM; the checker proves the page
            -- advanced every 295 frames by the T records alone, and uses
            -- these PINs for the event-keyed dome proofs (page 0's first
            -- frame -> hidden pages 1..8 -> the rebuilt page 0 after the
            -- wrap). Each PIN dumps the dome's SCB words and snapshots.
            if pages_run and fc == 0 and is_title() and in_cart then
                if page_addr ~= 0 then
                    local page = sp:read_u8(page_addr)
                    -- one dump at the first title frame of EVERY page
                    -- 0..8 (the "first page-0 frame" the checker compares
                    -- the wrap's rebuilt page 0 against, and each hidden
                    -- page's all-zero columns), plus the first page-0
                    -- frame after the wrap.
                    if page_pin[page] == nil then
                        page_pin[page] = n
                        if dome_snap and page ~= 0 then
                            dome_dump(n, 0)
                        elseif dome_snap and page == 0 and dome_snap0 == nil then
                            dome_snap0 = n
                            dome_dump(n, 0)
                        end
                    end
                    -- the first page-0 title frame AFTER the wrap (page 8
                    -- was seen): dump it ONCE (a bout of re-dumps would
                    -- give the checker several "second page 0" blocks).
                    if dome_snap and dome_wrapped == nil and page == 8 then
                        dome_wrapped = n
                        next_turn = math.max(next_turn or 0, n + 1)
                    end
                    if dome_snap and next_turn ~= nil and page == 0
                       and n >= next_turn then
                        dome_dump(n, 0)
                        next_turn = nil        -- only the first wrapped frame
                    end
                end
                -- whatever the cart reports (page_addr may be 0 before the
                -- M6 Task 6 build), the first confirmed title frame still
                -- snapshots, so boot_test.sh always has a file to check.
                if page_addr == 0 and dome_snap0 == nil and not snap_taken then
                    dome_snap0 = n
                    if dome_snap then
                        dome_dump(n, 0)
                    end
                end
            end
        else
            -- the game: hold Up from the first game frame (proof a's "the
            -- Up-held game"), nothing else; A only for the FLOW_RESTART leg.
            -- (The flow-pages-c run is MVS: it never reaches this branch —
            -- no Start is pressed, fc stays 0 for the whole run.)
            -- M6 Task 10, the best-aes game leg: Task 1's seed makes the
            -- old centred game score 0 (no kill), which fails this leg's
            -- "a real score" proof; hold Right and tap A every 11 frames
            -- instead, the same deterministic policy as best-mvs (the
            -- model gives fc 17818, score 699 at seed 0xaede).
            if best_aes_run and joy then
                joy.fields["P1 Left"]:set_value(0)
                joy.fields["P1 Up"]:set_value(0)
                joy.fields["P1 Right"]:set_value(1)
                joy.fields["P1 Down"]:set_value(0)
                joy.fields["P1 A"]:set_value(fc <= 17818 and (fc % 11) == 0
                                             and 1 or 0)
            elseif joy then
                joy.fields["P1 Up"]:set_value(1)
            end
            if restart and p1_go ~= nil and not a_pressed
               and fc >= p1_go + 60 and fc <= p1_go + 64 and joy then
                joy.fields["P1 A"]:set_value(1)
                if fc >= p1_go + 63 then
                    a_pressed = true
                end
            elseif not best_aes_run then
                if joy then joy.fields["P1 A"]:set_value(0) end
            end
            -- the HUD's first game frames (proof b): rows must match the
            -- model's first frame within a few frames of fc 1.
            if fc <= 12 then
                dump_fix(n, fc)
            end
            -- proof d: right after the A-restart, the HUD rows must show a
            -- new game (lives 3) and the title must not return.
            if restart and a_pressed and fc >= p1_go + 60
               and fc <= p1_go + 96 then
                dump_fix(n, fc)
            end
            -- Task 1: the AES Up-held game's GAME OVER at SG_BEGIN
            -- 1200 is fc 8188 (6509 before); the 6480 floor still
            -- only has to predate it
            if p1_go == nil and fc >= 6480 and is_go_text() == 1 then
                p1_go = fc
                f:write(string.format("GO %d %d\n", n, fc))
                -- M6 Task 9 (the flow-return leg): the game's score at
                -- GAME OVER (mis.score10 @ mis+76) and the best table as
                -- the cart's GAME OVER update left it in backup RAM — the
                -- checker proves the returned title's page 1 shows
                -- score10 * 10 for NORMAL (proof 3).
                if best_return and mis_addr ~= 0 and best_addr ~= 0 then
                    f:write(string.format("SC %d %d %d\n", n, fc,
                                          sp:read_u32(mis_addr + 76)))
                    best_rec(n, fc)
                end
                -- M6 Task 10 (the best-aes leg): the score at GAME OVER
                -- and the card-log sampling window (the save's answers —
                -- see the per-frame read above; the sampler runs from GO
                -- + 2 through the return).
                if best_aes_run and mis_addr ~= 0 and best_addr ~= 0
                   and (no_card or cardlog_addr ~= 0) then
                    f:write(string.format("SC %d %d %d\n", n, fc,
                                          sp:read_u32(mis_addr + 76)))
                    best_rec(n, fc)
                    card_ans_seen_n = n + 2
                end
                if not snap_taken then
                    machine.video:snapshot()
                    f:write(string.format("SNAP %d %d\n", n, fc))
                    snap_taken = true
                end
            end
            -- M6 Task 7, the level-select run: boot_test.sh needs a
            -- snapshot, and this run never reaches GAME OVER (it covers
            -- only the game's opening frames). Snapshot at the moment the
            -- game begins instead.
            if level_run and not snap_taken and fc >= 1 then
                machine.video:snapshot()
                f:write(string.format("SNAP %d %d\n", n, fc))
                snap_taken = true
            end
            -- M6 Task 10, the best-aes leg's post-return title: the proof
            -- "the return opens HIGH SCORES — page 1's NORMAL row reads the
            -- score". Sampled every 6 MAME frames from ~the window-expiry
            -- frame (p1_go + 290) while the game-session counter is 0
            -- (the post-return title; the checker gates on the drawn rows
            -- and T records as the MVS best leg does). The T/L/B records
            -- let the checker run the model on page 1.
            if best_aes_run and p1_go ~= nil and fc == 0
               and n >= p1_go + 290 and n >= next_aes_nrs then
                dump_fix(n, 0)
                best_rec(n, 0)
                cardlog_rec(n, 0)
                local page, t, cred = title_state()
                f:write(string.format("T %d 0 %d %d %d\n", n,
                                      page or -1, t or -1, cred or -1))
                if level_addr ~= 0 then
                    f:write(string.format("L %d 0 %d %d\n", n,
                                          sp:read_u8(level_addr),
                                          sp:read_u8(level_addr + 1)))
                end
                next_aes_nrs = n + 6
            end
        end
    end
    if n >= run_len then
        f:write(string.format("EXIT %d %d %d\n", n, framecnt(),
                              sp:read_u8(0x10fdb6)))
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d go=%s restart=%d\n",
                              in_cart, n, rec, tostring(p1_go or 0),
                              restart and 1 or 0))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__flow = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
