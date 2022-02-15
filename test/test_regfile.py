import os
import pytest
from amaranth import Cat
from amaranth import Signal
from amaranth import Module
from amaranth.sim import Simulator
from altair.gateware.debug.layout import DebugReg
from altair.gateware.debug.regfile import reg_map
from altair.gateware.debug.regfile import DebugRegisterFile


@pytest.fixture
def debugrf():
    dut = DebugRegisterFile()
    dut.add_register('dmstatus', DebugReg.DMSTATUS)
    dut.add_register('dmcontrol', DebugReg.DMCONTROL)
    dut.add_register('hartinfo', DebugReg.HARTINFO)
    dut.add_register('abstractcs', DebugReg.ABSTRACTCS)
    dut.add_register('command', DebugReg.COMMAND)
    dut.add_register('data0', DebugReg.DATA0)
    dut.add_register('haltsum0', DebugReg.HALTSUM0)
    dut.add_register('haltsum1', DebugReg.HALTSUM1)
    dut.add_register('sbcs', DebugReg.SBCS)
    dut.add_register('sbaddress0', DebugReg.SBADDRESS0)
    dut.add_register('sbdata0', DebugReg.SBDATA0)
    return dut

@pytest.fixture
def module(debugrf):
    m = Module()
    m.submodules.debugrf = debugrf

    # perform the update
    for reg in debugrf._registers.values():
        with m.If(reg.update):
            m.d.sync += reg.read.eq(reg.write)

    return m

@pytest.fixture
def simulator(module):
    sim = Simulator(module)
    sim.add_clock(1/1000, domain='sync')
    return sim

@pytest.fixture
def simulate(simulator):
    def process(test_process, vcd_file, vcd=False):
        simulator.add_sync_process(test_process, domain='sync')
        if vcd:
            os.makedirs('build/', exist_ok=True)
            with simulator.write_vcd(f'build/{vcd_file}'):
                simulator.run()
        else:
            simulator.run()

    return process

@pytest.fixture
def do_read(debugrf):
    def process(addr, rx):
        yield
        yield
        # configure DMI port
        yield debugrf.dmi.addr.eq(addr)
        yield debugrf.dmi.data_w.eq(0x8badf00d)
        yield debugrf.dmi.wen.eq(0)
        yield debugrf.dmi.valid.eq(1)
        while not (yield debugrf.dmi.ack):
            yield
        yield rx.eq(debugrf.dmi.data_r)
        yield debugrf.dmi.valid.eq(0)
        yield
        yield
    return process

@pytest.fixture
def do_write(debugrf):
    def process(addr, data, rx):
        yield
        yield
        # configure DMI port
        yield debugrf.dmi.addr.eq(addr)
        yield debugrf.dmi.data_w.eq(data)
        yield debugrf.dmi.wen.eq(1)
        yield debugrf.dmi.valid.eq(1)
        while not (yield debugrf.dmi.ack):
            yield
        yield rx.eq(debugrf.dmi.data_r)
        yield debugrf.dmi.valid.eq(0)
        yield
        yield
    return process

# @pytest.mark.skip(reason='temporal')
@pytest.mark.parametrize("addr", reg_map.keys())
def test_read_register(module, debugrf, simulate, do_read, addr):
    # perform the update
    for reg in debugrf._registers.values():
        with module.If(reg.update):
            module.d.sync += reg.read.eq(reg.write)

    def process():
        register = debugrf._registers[addr]  # reference
        rx       = Signal.like(register.read)  # tmp
        ref      = Signal.like(register.read)  # tmp
        yield from do_read(addr, rx)
        # get the reference value
        yield ref.eq(register.read)
        yield

        assert (yield rx) == (yield ref)
        assert (yield register.update) == 0

    simulate(process, f'test_read_register_{addr}.vcd', vcd=False)

# @pytest.mark.skip(reason='temporal')
@pytest.mark.parametrize("addr", reg_map.keys())
def test_write_register(debugrf, simulate, do_write, addr):
    def process():
        register = debugrf._registers[addr]  # reference
        rx       = Signal.like(register.read)  # tmp
        ref      = Signal.like(register.write)  # tmp
        data = 0xdeadc0de
        yield from do_write(addr, data, rx)

        assert (yield register.update) == 0  # To avoid multiple updates
        assert (yield rx) == 0               # No reads

    simulate(process, f'test_write_register_{addr}.vcd', vcd=True)
