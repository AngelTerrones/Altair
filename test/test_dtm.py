#!/usr/bin/env python3

import os
import pytest
from amaranth import Cat
from amaranth import Signal
from amaranth import Module
from amaranth import ClockDomain
from amaranth.sim import Simulator
from amaranth.sim import Delay
import vcd
from altair.gateware.debug.dtm import DTM
from altair.gateware.debug.layout import DmiOp
from altair.gateware.debug.layout import JTAGReg


@pytest.fixture
def dtm():
    return DTM()

@pytest.fixture
def jtag_cd():
    return ClockDomain('jtag', clk_edge='neg')

@pytest.fixture
def module(dtm, jtag_cd):
    m    = Module()
    m.domain
    sync = ClockDomain('sync', clk_edge='pos')
    m.domains += [jtag_cd, sync]
    m.submodules.dtm = dtm
    # Loopback the DMI
    with m.If(dtm.dmi.valid):
        m.d.comb += dtm.dmi.data_r.eq(0x87654321)
        m.d.sync += dtm.dmi.ack.eq(~dtm.dmi.ack)

    return m

@pytest.fixture
def simulator(module):
    sim = Simulator(module)
    sim.add_clock(1 / 5000, domain='sync')
    sim.add_clock(1 / 200, domain='jtag')

    return sim

@pytest.fixture
def tck_proc(dtm, jtag_cd):
    def process():
        while (True):
            yield dtm.port.tck.eq(jtag_cd.clk)
            yield Delay(1 / 20000)

    return process

@pytest.fixture
def reset(dtm):
    def process():
        yield dtm.port.tms.eq(0)
        yield
        yield dtm.port.tms.eq(1)
        yield
        yield
        yield
        yield
        yield
    return process

@pytest.fixture
def access_ir(dtm):
    def process(addr, ir_size, rx=None):
        yield dtm.port.tms.eq(0)  # Rest -> Idle
        yield
        yield dtm.port.tms.eq(1)  # Idle -> Select DR
        yield
        yield dtm.port.tms.eq(1)  # Select DR -> Select IR
        yield
        yield dtm.port.tms.eq(0)  # Select IR -> Capture IR
        yield
        yield dtm.port.tms.eq(0)  # Capture IR -> Shift IR (0)
        yield
        for i in range(ir_size - 1):
            yield dtm.port.tms.eq(0)  # Shift IR (i)
            yield dtm.port.tdi.eq(addr >> i)  # Read DTMCS = IDCODE(i)
            yield
            if rx is not None: yield rx.eq(Cat(rx[1:], dtm.port.tdo))
        yield dtm.port.tms.eq(1)  # Shift IR -> Exit1
        yield dtm.port.tdi.eq(addr >> (ir_size - 1))  # Read DTMCS = IDCODE(i)
        yield
        if rx is not None: yield rx.eq(Cat(rx[1:], dtm.port.tdo))
        yield dtm.port.tms.eq(1)  # Exit1 -> UpdateIR
        yield
        yield dtm.port.tms.eq(0)  # Update IR -> Idle
        yield
        yield
        yield rx
    return process

@pytest.fixture
def access_dr(dtm):
    def process(dr_size, dr_new, rx=None):
        yield dtm.port.tms.eq(1)  # Idle -> Select DR
        yield
        yield dtm.port.tms.eq(0)  # Select DR -> Capture DR
        yield
        yield dtm.port.tms.eq(0)  # Capture DR -> Shift DR (0)
        yield
        for i in range(dr_size - 1):
            yield dtm.port.tms.eq(0)  # Shift IR (i)
            yield dtm.port.tdi.eq(dr_new >> i)  # Read DTMCS = IDCODE(0)
            yield
            if rx is not None: yield rx.eq(Cat(rx[1:], dtm.port.tdo))
        yield dtm.port.tms.eq(1)  # Shift DR -> Exit1
        yield dtm.port.tdi.eq(dr_new >> (dr_size - 1))  # Final bit
        yield
        if rx is not None: yield rx.eq(Cat(rx[1:], dtm.port.tdo))
        yield dtm.port.tms.eq(1)  # Exit1 -> Update DR
        yield
        yield dtm.port.tms.eq(0)  # Update DR -> Idle
        yield
        yield
        yield
    return process

@pytest.fixture
def simulate(simulator, tck_proc):
    def process(test_process, vcd_file, vcd=False, timeout=0.5):
        simulator.add_process(tck_proc)
        simulator.add_sync_process(test_process, domain='jtag')
        if vcd:
            os.makedirs('build/', exist_ok=True)
            with simulator.write_vcd(vcd_file):
                simulator.run_until(timeout)
        else:
            simulator.run_until(timeout)

    return process

# @pytest.mark.skip(reason='temporal')
@pytest.mark.parametrize("ir_addr", [JTAGReg.BYPASS, JTAGReg.IDCODE, JTAGReg.DMI, JTAGReg.DTMCS])
def test_ir(dtm, simulate, reset, access_ir, ir_addr):
    def process():
        # Values
        ir_size = len(dtm.tap.ir)
        rx     = Signal(ir_size)
        yield from reset()
        yield from access_ir(addr=ir_addr, ir_size=ir_size, rx=rx)

        assert (yield dtm.tap.ir) == ir_addr  # Internal IR register must be the same as the ADDR
        assert (yield rx) == JTAGReg.IDCODE  # Read the default value

    simulate(process, f"build/test_ir_{ir_addr}.vcd", timeout=0.2, vcd=False)

# @pytest.mark.skip(reason='temporal')
def test_write_IDCODE(dtm, simulate, reset, access_ir, access_dr):
    def process():
        # Values
        test_value  = 0x8badf00d
        ir_addr     = JTAGReg.IDCODE
        ir_size     = len(dtm.tap.ir)
        idcode_size = len(dtm.tap.regs[JTAGReg.IDCODE].read)
        rx          = Signal(idcode_size)
        yield from reset()
        yield from access_ir(addr=ir_addr, ir_size=ir_size)
        yield from access_dr(dr_size=idcode_size, dr_new=test_value, rx=rx)

        assert (yield dtm.tap.dr) == test_value  # Internal DR must have the test value
        assert (yield dtm.tap.regs[JTAGReg.IDCODE].read.value) == dtm.idcode  # IDCODE is inmutable
        assert (yield rx) == dtm.idcode  # we got IDCODE

    simulate(process, f"build/test_write_IDCODE.vcd", timeout=0.5, vcd=False)

# @pytest.mark.skip(reason='temporal')
def test_write_DTMCS(dtm, simulate, reset, access_ir, access_dr):
    def process():
        # Values
        test_value = 0x87654321
        ir_addr    = JTAGReg.DTMCS
        ir_size    = len(dtm.tap.ir)
        dtmcs_size = len(dtm.tap.regs[JTAGReg.DTMCS].read)
        rx         = Signal(dtmcs_size)
        yield from reset()
        yield from access_ir(addr=ir_addr, ir_size=ir_size)
        yield from access_dr(dr_size=dtmcs_size, dr_new=test_value, rx=rx)

        assert (yield dtm.tap.dr) == test_value  # Internal DR must have the test value
        assert (yield rx) == dtm.dtmcs  # we got DTMCS
        yield rx.eq(dtm.tap.regs[JTAGReg.DTMCS].read)
        yield
        assert (yield rx) == dtm.dtmcs  # DTMCS is inmutable

    simulate(process, f"build/test_write_DTMCS.vcd", timeout=0.5, vcd=False)

# @pytest.mark.skip(reason='temporal')
@pytest.mark.parametrize("addr, op, data", zip([0x1, 0x2, 0x3], [DmiOp.WRITE, DmiOp.NOP, DmiOp.READ], [0xdeadf00d, 0x0badc00de, 0x55aa55aa]))
def test_write_DMI(dtm, simulate, reset, access_ir, access_dr, addr, op, data):
    def process():
        # Values
        test_value = (addr << 34) | (data << 2) | (op)  # Nop
        ir_addr    = JTAGReg.DMI
        ir_size    = len(dtm.tap.ir)
        dmi_size   = len(dtm.tap.regs[JTAGReg.DMI].read)
        rx         = Signal(dmi_size)
        yield from reset()
        yield from access_ir(addr=ir_addr, ir_size=ir_size)
        yield from access_dr(dr_size=dmi_size, dr_new=test_value, rx=rx)

        assert (yield dtm.tap.dr) == test_value  # Internal DR must have the test value
        yield rx.eq(dtm.tap.regs[JTAGReg.DMI].write)
        yield
        assert (yield rx) == test_value                               # write register has the new value
        assert (yield dtm.tap.regs[JTAGReg.DMI].write.op) == op       # DMI data ok
        assert (yield dtm.tap.regs[JTAGReg.DMI].write.addr) == addr   #
        assert (yield dtm.tap.regs[JTAGReg.DMI].write.data) == data   #
        assert (yield dtm.tap.regs[JTAGReg.DMI].read.op) == DmiOp.OK  # DMI transaction is OK.
        if op != DmiOp.NOP:
            assert (yield dtm.tap.regs[JTAGReg.DMI].read.data) == 0x87654321  # DMI data is this value (TODO make variable).

    simulate(process, f"build/test_write_DMI.vcd", timeout=0.5, vcd=False)
