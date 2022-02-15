from enum import Enum
from amaranth.hdl.rec import DIR_FANIN
from amaranth.hdl.rec import DIR_FANOUT

# DTM: Debug Transport Module
class JTAGReg:
    BYPASS = 0x00
    IDCODE = 0x01
    DTMCS  = 0x10
    DMI    = 0x11


jtag_port_layout = [
    ("tck",  1, DIR_FANIN),
    ("tms",  1, DIR_FANIN),
    ("tdi",  1, DIR_FANIN),
    ("tdo",  1, DIR_FANOUT)
]

dtmcs_layout = [
    ("version",       4),
    ("abits",         6),
    ("dmistat",       2),
    ("idle",          3),
    ("zero0",         1),
    ("dmireset",      1),
    ("dmihardreset",  1),
    ("zero1",        14)
]

dmi_layout = [
    ("op",    2),
    ("data", 32),
    ("addr",  7),
]

# DMI: Debug interface (bus)
dmi_bus_layout = [
    ('addr',   7),
    ('data_w', 32),
    ('wen',    1),
    ('valid',  1),
    ('data_r', 32),
    ('ack',    1),
    ('err',    1),
]

# DM: Debug Module
class Version:
    NONE  = 0
    V011  = 1
    V013  = 2
    OTHER = 15


class Command:
    ACCESS_REG   = 0
    QUICK_ACCESS = 1
    ACCESS_MEM   = 2


class Error:
    NONE        = 0
    BUSY        = 1
    UNSUPPORTED = 2
    EXCEPTION   = 3
    HALT_RESUME = 4


RegMode = Enum("RegMode", ("R", "W", "W1", "RW", "RW1C", "WARL"))


class DmiOp:
    OK   = NOP   = 0
    _0   = READ  = 1
    FAIL = WRITE = 2
    BUSY = _1    = 3


# Debug registers

class DebugReg:
    DATA0      = 0x04
    DMCONTROL  = 0x10
    DMSTATUS   = 0x11
    HARTINFO   = 0x12
    HALTSUM1   = 0x13
    ABSTRACTCS = 0x16
    COMMAND    = 0x17
    PROGBUF0   = 0x20
    HALTSUM2   = 0x34
    HALTSUM3   = 0x35
    SBCS       = 0x38
    SBADDRESS0 = 0x39
    SBDATA0    = 0x3c
    HALTSUM0   = 0x40


dmstatus_layout = [
    ("version",           4, RegMode.R,    Version.V013),
    ("confstrptrvalid",   1, RegMode.R,    0),
    ("hasresethaltreq",   1, RegMode.R,    0),
    ("authbusy",          1, RegMode.R,    0),
    ("authenticated",     1, RegMode.R,    1),
    ("anyhalted",         1, RegMode.R,    0),
    ("allhalted",         1, RegMode.R,    0),
    ("anyrunning",        1, RegMode.R,    0),
    ("allrunning",        1, RegMode.R,    0),
    ("anyunavail",        1, RegMode.R,    0),
    ("allunavail",        1, RegMode.R,    0),
    ("anynonexistent",    1, RegMode.R,    0),
    ("allnonexistent",    1, RegMode.R,    0),
    ("anyresumeack",      1, RegMode.R,    0),
    ("allresumeack",      1, RegMode.R,    0),
    ("anyhavereset",      1, RegMode.R,    0),
    ("allhavereset",      1, RegMode.R,    0),
    ("zero0",             2, RegMode.R,    0),
    ("impebreak",         1, RegMode.R,    0),
    ("zero1",             9, RegMode.R,    0)
]


dmcontrol_layout = [
    ("dmactive",          1, RegMode.RW,   0),
    ("ndmreset",          1, RegMode.RW,   0),
    ("clrresethaltreq",   1, RegMode.W1,   0),
    ("setresethaltreq",   1, RegMode.W1,   0),
    ("zero0",             2, RegMode.R,    0),
    ("hartselhi",        10, RegMode.R,    0),
    ("hartsello",        10, RegMode.R,    0),
    ("hasel",             1, RegMode.RW,   0),
    ("zero1",             1, RegMode.R,    0),
    ("ackhavereset",      1, RegMode.W1,   0),
    ("hartreset",         1, RegMode.RW,   0),
    ("resumereq",         1, RegMode.W1,   0),
    ("haltreq",           1, RegMode.W,    0)
]


abstractcs_layout = [
    ("datacount",         4, RegMode.R,    1),
    ("zero0",             4, RegMode.R,    0),
    ("cmderr",            3, RegMode.RW1C, 0),
    ("zero1",             1, RegMode.R,    0),
    ("busy",              1, RegMode.R,    0),
    ("zero2",            11, RegMode.R,    0),
    ("progbufsize",       5, RegMode.R,    0),
    ("zero3",             3, RegMode.R,    0)
]


cmd_access_reg_layout = [
    ("regno",            16),
    ("write",             1),
    ("transfer",          1),
    ("postexec",          1),
    ("aarpostincrement",  1),
    ("aarsize",           3),
    ("zero0",             1),
]


command_layout = [
    ("control",          24, RegMode.W,    0),
    ("cmdtype",           8, RegMode.W,    Command.ACCESS_REG)
]


sbcs_layout = [
    ("sbaccess8",         1, RegMode.R,    1),
    ("sbaccess16",        1, RegMode.R,    1),
    ("sbaccess32",        1, RegMode.R,    1),
    ("sbaccess64",        1, RegMode.R,    0),
    ("sbaccess128",       1, RegMode.R,    0),
    ("sbasize",           7, RegMode.R,    32),
    ("sberror",           3, RegMode.RW1C, 0),
    ("sbreadondata",      1, RegMode.RW,   0),
    ("sbautoincrement",   1, RegMode.RW,   0),
    ("sbaccess",          3, RegMode.RW,   2),
    ("sbreadonaddr",      1, RegMode.RW,   0),
    ("sbbusy",            1, RegMode.R,    0),
    ("sbbusyerror",       1, RegMode.RW1C, 0),
    ("zero0",             6, RegMode.R,    0),
    ("sbversion",         3, RegMode.R,    1)
]


flat_layout = [
    ("value",            32, RegMode.RW,   0)
]
