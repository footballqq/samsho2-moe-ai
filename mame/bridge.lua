-- bridge.lua — MAME-side TCP bridge for the SS2 project (samsho2, MAME 0.281).
-- Ported from kof97_rl's proven bridge, minimal diff:
--   * env var MAME_SS2_SOCKET (was KOFRL_SOCKET)
--   * frame subscription held in _G (0.260+ GC safety)
--   * extra op READF: read back ioport field values (mechanical input echo)
--   * extra SET key "freeflow=<path>": append JSONL each frame without lockstep
-- Protocol constants must match src/mame_protocol.py.
--
-- Lock-step: blocking inside the frame callback pauses emulation, so each
-- ACTION advances exactly `step` frames — deterministic and frame-accurate.

-- NeoGeo BIOS watchdog soft-resets during boot re-run the autoboot script;
-- Lua state survives, so re-runs must be no-ops.
if _G.__ss2_bridge_active then
  return
end
_G.__ss2_bridge_active = true

local OP_CONFIG, OP_ACTION, OP_PRESS, OP_LOAD_STATE = 1, 2, 3, 4
local OP_SAVE_STATE, OP_SET, OP_PING, OP_QUIT, OP_WRITE = 5, 6, 7, 8, 9
local OP_READF = 10
local OP_READ = 11
local MSG_HELLO, MSG_STATE, MSG_READY, MSG_OK, MSG_PONG, MSG_ERR = 100, 101, 102, 103, 104, 110

local machine = manager.machine

-- ---------------------------------------------------------------- socket
local socket_spec = os.getenv("MAME_SS2_SOCKET") or "127.0.0.1:55555"
local sock = emu.file("rw")
local open_err = sock:open("socket." .. socket_spec)
if open_err then
  error("bridge.lua: cannot connect to " .. socket_spec .. ": " .. tostring(open_err))
end

local function send(op, payload)
  payload = payload or ""
  sock:write(string.pack("<BI4", op, #payload) .. payload)
end

local function read_exact(n, timeout_s)
  local buf = ""
  local deadline = os.time() + (timeout_s or 60)
  while #buf < n do
    local chunk = sock:read(n - #buf)
    if chunk and #chunk > 0 then
      buf = buf .. chunk
    elseif os.time() > deadline then
      return nil
    end
  end
  return buf
end

-- ---------------------------------------------------------------- devices
local space = machine.devices[":maincpu"].spaces["program"]

local screen = nil
for _, scr in pairs(machine.screens) do
  screen = scr
  break
end

local readers = {
  [0] = function(a) return space:read_u8(a) end,
  [1] = function(a) return space:read_i8(a) end,
  [2] = function(a) return space:read_u16(a) end,
  [3] = function(a) return space:read_i16(a) end,
  [4] = function(a) return space:read_u32(a) end,
}

local writers = {
  [0] = function(a, v) space:write_u8(a, v) end,
  [1] = function(a, v) space:write_u8(a, v & 0xFF) end,
  [2] = function(a, v) space:write_u16(a, v) end,
  [3] = function(a, v) space:write_u16(a, v & 0xFFFF) end,
  [4] = function(a, v) space:write_u32(a, v) end,
}

-- ---------------------------------------------------------------- ioports
-- Suffix-match port tags (0.281 uses ":edge:joy:JOY1" style tags).
local function find_port(suffixes)
  local ports = machine.ioport.ports
  for tag, port in pairs(ports) do
    for _, want in ipairs(suffixes) do
      if tag == want or tag:sub(-#want) == want then
        return port, tag
      end
    end
  end
  return nil, "?"
end

local function fields_by_mask(port)
  local map = {}
  if port == nil then return map end
  for _, field in pairs(port.fields) do
    map[field.mask] = field
  end
  return map
end

local joy1_port, joy1_tag = find_port({"JOY1", ":IN0"})
local joy2_port, joy2_tag = find_port({"JOY2", ":IN1"})
local start_port, start_tag = find_port({"START", ":IN2"})
local coin_port, coin_tag = find_port({"AUDIO/COIN", "AUDIO_COIN", ":IN3"})

local role_fields = {
  [0] = fields_by_mask(joy1_port),
  [1] = fields_by_mask(joy2_port),
  [2] = fields_by_mask(start_port),
  [3] = fields_by_mask(coin_port),
}
local role_ports = { [0] = joy1_port, [1] = joy2_port, [2] = start_port, [3] = coin_port }

local held = {}          -- list of {field=f}; everything currently set_value(1)
local held_buttons = {}  -- subset released when press counter expires

local function set_bits(fields, mask, into)
  local bit = 1
  while bit <= 0x80 do
    if mask & bit ~= 0 then
      local field = fields[bit]
      if field then
        field:set_value(1)
        table.insert(held, { field = field })
        if into then table.insert(into, { field = field }) end
      end
    end
    bit = bit << 1
  end
end

local function release_all()
  for _, entry in ipairs(held) do
    entry.field:clear_value()
  end
  held = {}
  held_buttons = {}
end

local function release_buttons()
  for _, entry in ipairs(held_buttons) do
    entry.field:clear_value()
  end
  held_buttons = {}
end

-- ---------------------------------------------------------------- state
local configured = false
local playing_addr, playing_value = 0, 0
local ready_delay, ready_timeout = 30, 600
local mem_entries = {}  -- {addr=..., type=...}
local ai_role = 0       -- 0: AI controls P1 (default), 1: AI controls P2

-- frame-loop state machine (explicit flags, no sentinel arithmetic)
local state_lockstep = 0      -- frames remaining in current ACTION/PRESS
local state_loading = false
local load_frames = 0
local save_ack_frames = 0     -- >0: count down, ack save when it hits 0
local press_left = 0
local want_pixels = false

-- freeflow mode: append JSONL each frame, never block the frame callback
local freeflow_path = nil
local freeflow_file = nil
local freeflow_frame = 0
-- port trace (debug): P1 port raw byte per frame
local trace_file = nil
local trace_n = 0

local function read_values()
  local parts = {}
  for _, entry in ipairs(mem_entries) do
    local value = 0
    if entry.addr ~= 0 then
      local ok, v = pcall(readers[entry.type], entry.addr)
      value = ok and (v or 0) or 0
    end
    parts[#parts + 1] = string.pack("<I4", value & 0xFFFFFFFF)
  end
  return table.concat(parts)
end

local function send_state(msg_type)
  local payload = read_values()
  if want_pixels and screen then
    local ok, data, w, h = pcall(function()
      local d, ww, hh = screen:pixels()
      return d, ww, hh
    end)
    if ok and data then
      payload = payload .. string.pack("<B", 1) .. string.pack("<I2I2", w, h) .. data
    else
      payload = payload .. string.pack("<B", 0)
    end
  else
    payload = payload .. string.pack("<B", 0)
  end
  send(msg_type, payload)
end

local function freeflow_close()
  if freeflow_file then freeflow_file:close(); freeflow_file = nil end
  freeflow_path = nil
end

local function freeflow_open(value)
  freeflow_close()
  freeflow_path = value
  freeflow_file = io.open(freeflow_path, "w")
  freeflow_frame = 0
end

-- ---------------------------------------------------------------- commands
-- returns true when the frame loop must unblock (frames are about to run)
local function handle_set(payload)
  local key, value = payload:match("^([^=]+)=(.*)$")
  local unblock = false
  if key == "throttle" then
    machine.video.throttled = (value == "1" or value == "true")
  elseif key == "throttle_rate" then
    machine.video.throttle_rate = tonumber(value) or 1.0
  elseif key == "ai_role" then
    ai_role = tonumber(value) or 0
  elseif key == "field" then
    -- generic ioport field set: "PORTSUFFIX:MASK:VALUE" (e.g. DSW:64:1)
    local suffix, mask_s, val_s = value:match("^([^:]+):(%d+):(%d+)$")
    local ok, err = pcall(function()
      local port = find_port({ suffix })
      if not port then error("port not found: " .. tostring(suffix)) end
      local field = fields_by_mask(port)[tonumber(mask_s)]
      if not field then error("field not found: " .. tostring(mask_s)) end
      field:set_value(tonumber(val_s))
    end)
    if not ok then
      send(MSG_ERR, "field set failed: " .. tostring(err))
      return unblock
    end
  elseif key == "trace_ports" then
    -- record P1 port raw byte per frame to file (debug input path)
    if value == "" then
      if trace_file then trace_file:close(); trace_file = nil end
    else
      if trace_file then trace_file:close() end
      trace_file = io.open(value, "w")
      trace_n = 0
    end
    -- single OK from the shared tail send below (double-OK desynced the next
    -- command's expected STATE reply)
  elseif key == "freeflow" then
    if value == "" then
      freeflow_close()
    else
      freeflow_open(value)
      unblock = true  -- frame loop resumes in freeflow mode
    end
  end
  send(MSG_OK)
  return unblock
end

local function handle_readf(payload)
  local role = string.unpack("<B", payload)
  local mask = nil
  if #payload >= 2 then mask = string.unpack("<B", payload, 2) end
  local fields = role_fields[role] or {}
  local port = role_ports[role]
  if mask then
    -- single-field diagnostic: field:value() readback
    local f = fields[mask]
    local ok, v = pcall(function() return f and f:value() or nil end)
    local n = tonumber(v)
    local byte = (n == 1) and 1 or ((n == 0) and 0 or 255)  -- 255 = unknown
    send(MSG_STATE, string.pack("<BBB", 1, mask, byte))
    return
  end
  -- live aggregate from the ioport system (reflects set_value overrides)
  local ok, live = pcall(function() return port:read() end)
  live = (ok and live) or 0
  local masks = {}
  local bit = 1
  while bit <= 0x80 do
    if fields[bit] then masks[#masks + 1] = bit end
    bit = bit << 1
  end
  local parts = { string.pack("<B", #masks) }
  for _, m in ipairs(masks) do
    parts[#parts + 1] = string.pack("<BB", m, (live & m ~= 0) and 1 or 0)
  end
  send(MSG_STATE, table.concat(parts))
end

-- Blocks until a command arrives that requires frames to advance.
-- Returns control to the frame loop only for ACTION/PRESS/loading/freeflow-on.
local function await_command()
  while true do
    -- 120s: long enough for any legitimate pause, short enough that an
    -- orphaned MAME (Python died without QUIT) exits instead of spinning
    local header = read_exact(5, 120)
    if header == nil then
      send(MSG_ERR, "command timeout")
      machine:exit()
      return
    end
    local op, length = string.unpack("<BI4", header)
    local payload = ""
    if length > 0 then
      payload = read_exact(length, 60) or ""
    end

    if op == OP_ACTION then
      local dir, buttons, press, step, pix = string.unpack("<BBBBB", payload)
      release_all()
      set_bits(role_fields[ai_role], dir, nil)
      set_bits(role_fields[ai_role], buttons, held_buttons)
      press_left = press
      state_lockstep = math.max(step, 1)
      want_pixels = (pix == 1)
      return
    elseif op == OP_PRESS then
      local role, mask, press, wait, pix = string.unpack("<BBI2I2B", payload)
      release_all()
      set_bits(role_fields[role], mask, held_buttons)
      press_left = press
      state_lockstep = math.max(wait, 1)
      want_pixels = (pix == 1)
      return
    elseif op == OP_LOAD_STATE then
      local pix = string.unpack("<B", payload)
      local name = payload:sub(2)
      want_pixels = (pix == 1)
      release_all()
      local ok, err = pcall(function() machine:load(name) end)
      if not ok then
        send(MSG_ERR, "load failed: " .. tostring(err))
      else
        state_loading = true
        load_frames = 0
        return
      end
    elseif op == OP_SAVE_STATE then
      local ok, err = pcall(function() machine:save(payload) end)
      if not ok then
        send(MSG_ERR, "save failed: " .. tostring(err))
      else
        save_ack_frames = 15  -- save is scheduled; ack from the frame loop
        return
      end
    elseif op == OP_SET then
      if handle_set(payload) then return end
    elseif op == OP_WRITE then
      local addr, type_code, value = string.unpack("<IBi4", payload)
      writers[type_code](addr, value)
      send(MSG_OK)
    elseif op == OP_READ then
      -- dynamic single-point read (uid-relative entity reads reply as a
      -- 1-value STATE frame: <I4 value><B pixels-flag=0>)
      local addr, type_code = string.unpack("<IB", payload)
      local ok_r, v = pcall(readers[type_code], addr)
      send(MSG_STATE, string.pack("<I4B", ok_r and (v or 0) or 0, 0))
    elseif op == OP_READF then
      handle_readf(payload)
    elseif op == OP_PING then
      send(MSG_PONG)
    elseif op == OP_QUIT then
      freeflow_close()
      machine:exit()
      return
    else
      send(MSG_ERR, "unknown opcode " .. tostring(op))
    end
  end
end

-- drain any bytes already available on the socket (freeflow poll); never blocks
local rx_buf = ""
local function try_process_commands()
  while true do
    local ok, chunk = pcall(function() return sock:read(4096) end)
    if ok and chunk and #chunk > 0 then
      rx_buf = rx_buf .. chunk
    else
      break
    end
  end
  while #rx_buf >= 5 do
    local op, length = string.unpack("<BI4", rx_buf)
    if #rx_buf < 5 + length then break end
    local payload = rx_buf:sub(6, 5 + length)
    rx_buf = rx_buf:sub(6 + length)
    if op == OP_SET then
      local key, value = payload:match("^([^=]+)=(.*)$")
      if key == "freeflow" then
        if value == "" then
          freeflow_close()
          send(MSG_OK)
        else
          freeflow_open(value)
          send(MSG_OK)
        end
      elseif key == "throttle" then
        machine.video.throttled = (value == "1" or value == "true")
        send(MSG_OK)
      elseif key == "throttle_rate" then
        machine.video.throttle_rate = tonumber(value) or 1.0
        send(MSG_OK)
      elseif key == "wp" then
        -- T5 master hunt: run a debugger command (watchpoint/breakpoint).
        -- Requires -debug; survives state loads when armed after load.
        if machine.debugger ~= nil and machine.debugger.command ~= nil then
          local ok, res = pcall(machine.debugger.command, machine.debugger, value)
          print("T5WP-CMD: " .. tostring(ok) .. "|" .. tostring(res))
          send(MSG_OK, tostring(ok) .. "|" .. tostring(res))
        else
          send(MSG_ERR, "wp: debugger unavailable (launch with -debug)")
        end
      else
        send(MSG_ERR, "freeflow: unsupported SET key " .. tostring(key))
      end
    elseif op == OP_PING then
      send(MSG_PONG)
    elseif op == OP_QUIT then
      freeflow_close()
      machine:exit()
      return
    else
      send(MSG_ERR, "freeflow: unsupported opcode " .. tostring(op))
    end
  end
end

-- ---------------------------------------------------------------- frame loop
local function on_frame()
  if freeflow_path then
    if freeflow_file then
      freeflow_frame = freeflow_frame + 1
      local parts = { "{\"f\":", tostring(freeflow_frame) }
      for _, entry in ipairs(mem_entries) do
        local ok, v = pcall(readers[entry.type], entry.addr)
        parts[#parts + 1] = string.format(",\"a%x\":%d", entry.addr, ok and (v or 0) or 0)
      end
      parts[#parts + 1] = "}"
      freeflow_file:write(table.concat(parts) .. "\n")
      if freeflow_frame % 60 == 0 then freeflow_file:flush() end
    end
    try_process_commands()
    return
  end

  if not configured then
    return
  end

  if state_loading then
    load_frames = load_frames + 1
    if load_frames >= ready_delay then
      local ok, phase = pcall(readers[0], playing_addr)
      if (ok and phase == playing_value) or load_frames >= ready_timeout then
        state_loading = false
        send_state(MSG_READY)
        await_command()
      end
    end
    return
  end

  if save_ack_frames > 0 then
    save_ack_frames = save_ack_frames - 1
    if save_ack_frames == 0 then
      send(MSG_OK)
      await_command()
    end
    return
  end

  if state_lockstep > 0 then
    -- 0.281: the input system may clear field overrides each frame —
    -- re-assert every held field so holds/presses span frames reliably
    for _, entry in ipairs(held) do
      entry.field:set_value(1)
    end
    if trace_file then
      trace_n = trace_n + 1
      local ok_t, raw16 = pcall(function() return space:read_u16(0x300000) end)
      local joyb = ok_t and ((raw16 >> 8) & 0xFF) or 0xFF
      local dswb = ok_t and (raw16 & 0xFF) or 0xFF
      trace_file:write(string.format("%d joy=%02X dsw=%02X\n", trace_n, joyb, dswb))
      if trace_n % 30 == 0 then trace_file:flush() end
    end
    state_lockstep = state_lockstep - 1
    if press_left > 0 then
      press_left = press_left - 1
      if press_left == 0 then
        release_buttons()
      end
    end
    if state_lockstep == 0 then
      send_state(MSG_STATE)
      await_command()
    end
    return
  end

  -- idle (first frame after handshake)
  await_command()
end

-- hold the subscription in _G so the GC can never collect it (0.260+ behavior)
if emu.add_machine_frame_notifier ~= nil then
  _G.__ss2_bridge_sub = emu.add_machine_frame_notifier(on_frame)
else
  emu.register_frame_done(on_frame)
end

-- ---------------------------------------------------------------- handshake
local hello = string.format(
  "game=%s;mame=%s;joy1=%s;joy2=%s;start=%s;coin=%s",
  emu.romname(), emu.app_version(), joy1_tag, joy2_tag, start_tag, coin_tag)
send(MSG_HELLO, hello)

local header = read_exact(5, 120)
if header == nil then
  error("bridge.lua: no CONFIG received")
end
local op, length = string.unpack("<BI4", header)
local payload = read_exact(length, 60)
if op ~= OP_CONFIG then
  error("bridge.lua: expected CONFIG, got opcode " .. tostring(op))
end

local n, offset
playing_addr, playing_value, ready_delay, ready_timeout, n, offset = string.unpack("<I4BI2I2I4", payload)
for _ = 1, n do
  local addr, type_code
  addr, type_code, offset = string.unpack("<IB", payload, offset)
  mem_entries[#mem_entries + 1] = { addr = addr, type = type_code }
end
configured = true
send(MSG_OK)
