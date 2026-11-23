"""Shared constants for the MAME bridge protocol (must match mame/bridge.lua)."""

# Python -> Lua opcodes
OP_CONFIG = 1
OP_ACTION = 2
OP_PRESS = 3        # raw port press (boot/menu scripting): role-addressed
OP_LOAD_STATE = 4
OP_SAVE_STATE = 5
OP_SET = 6
OP_PING = 7
OP_QUIT = 8
OP_WRITE = 9        # poke a memory value (setup/scripting only)
OP_READF = 10       # read back ioport field values (mechanical input echo)
OP_READ = 11        # dynamic single-point memory read (uid-relative entity reads)

# Lua -> Python messages
MSG_HELLO = 100
MSG_STATE = 101
MSG_READY = 102
MSG_OK = 103
MSG_PONG = 104
MSG_ERR = 110

# memory read/write type codes
TYPE_U8, TYPE_S8, TYPE_U16, TYPE_S16, TYPE_U32 = 0, 1, 2, 3, 4
TYPE_CODES = {"u8": TYPE_U8, "s8": TYPE_S8, "u16": TYPE_U16,
              "s16": TYPE_S16, "u32": TYPE_U32}

# PRESS roles
ROLE_P1, ROLE_P2, ROLE_START, ROLE_COIN = 0, 1, 2, 3

# P1 joystick masks (neogeo ioport layout, confirmed by T1 probe)
MSK_UP, MSK_DOWN, MSK_LEFT, MSK_RIGHT = 0x01, 0x02, 0x04, 0x08
MSK_A, MSK_B, MSK_C, MSK_D = 0x10, 0x20, 0x40, 0x80

DIR_MASKS = {
    "N": 0, "U": MSK_UP, "D": MSK_DOWN, "L": MSK_LEFT, "R": MSK_RIGHT,
    "UL": MSK_UP | MSK_LEFT, "UR": MSK_UP | MSK_RIGHT,
    "DL": MSK_DOWN | MSK_LEFT, "DR": MSK_DOWN | MSK_RIGHT,
    "DF": MSK_DOWN | MSK_RIGHT,
}
