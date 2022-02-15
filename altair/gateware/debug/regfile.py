from audioop import add
from signal import signal
from amaranth import Module, Signal
from amaranth import Record
from amaranth import Elaboratable
from amaranth.build import Platform
from altair.gateware.debug.layout import dmi_bus_layout
from altair.gateware.debug.layout import RegMode
from altair.gateware.debug.layout import DebugReg
from altair.gateware.debug.layout import flat_layout
from altair.gateware.debug.layout import sbcs_layout
from altair.gateware.debug.layout import command_layout
from altair.gateware.debug.layout import dmstatus_layout
from altair.gateware.debug.layout import dmcontrol_layout
from altair.gateware.debug.layout import abstractcs_layout

reg_map = {
    DebugReg.DMSTATUS:   dmstatus_layout,
    DebugReg.DMCONTROL:  dmcontrol_layout,
    DebugReg.HARTINFO:   flat_layout,
    DebugReg.ABSTRACTCS: abstractcs_layout,
    DebugReg.COMMAND:    command_layout,
    DebugReg.SBCS:       sbcs_layout,
    DebugReg.SBADDRESS0: flat_layout,
    DebugReg.SBDATA0:    flat_layout,
    DebugReg.DATA0:      flat_layout,
    DebugReg.HALTSUM0:   flat_layout,
    DebugReg.HALTSUM1:   flat_layout,
}


class _DebugRegister(Record):
    def __init__(self, name: str, layout: list) -> None:
        temp = [
            ('read',   layout),
            ('write',  layout),
            ('update', 1)
        ]
        super().__init__(temp, name=name)

class DebugRegisterFile(Elaboratable):
    def __init__(self) -> None:
        self._registers = {}
        self.dmi        = Record(dmi_bus_layout)

    def add_register(self, name: str, addr: int) -> _DebugRegister:
        if addr not in reg_map:
            raise ValueError(f'Unknown register at {addr:x}')
        if addr in self._registers:
            raise ValueError(f'Address {addr:x} already in the allocated list')

        layout = [f[:2] for f in reg_map[addr]]  # keep (name, size)
        self._registers[addr] = register = _DebugRegister(name, layout)
        # Set the reset value
        for name, _, _, reset in reg_map[addr]:
            getattr(register.read, name).reset  = reset
            getattr(register.write, name).reset = reset

        return register

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        # define read/write operations
        def read(addr, reg):
            tmp = Record(reg.read.layout)  # register -> temp -> dat_r
            m.d.sync += self.dmi.data_r.eq(tmp)
            # check fields register access
            for name, _, mode, _ in reg_map[addr]:
                src = getattr(reg.read, name)
                dst = getattr(tmp, name)
                if mode in {RegMode.R, RegMode.RW, RegMode.RW1C}:
                    m.d.comb += dst.eq(src)
                else:
                    m.d.comb += dst.eq(0)

        def write(addr, reg):
            tmp = Record(reg.write.layout)  # dat_w -> temp -> register
            m.d.comb += tmp.eq(self.dmi.data_w)
            # check fields register access
            for name, _, mode, _ in reg_map[addr]:
                src = getattr(tmp, name)
                dst = getattr(reg.write, name)
                if mode in {RegMode.W, RegMode.RW}:
                    m.d.sync += dst.eq(src)
                elif mode is RegMode.W1:
                    m.d.sync += dst.eq(getattr(reg.write, name) | src)
                elif mode is RegMode.RW1C:
                    m.d.sync += dst.eq(getattr(reg.write, name) & ~src)
            # the update is done in another module :D
            m.d.sync += reg.update.eq(1)

        with m.If(self.dmi.valid & ~self.dmi.ack):
            # ack the transaction
            m.d.sync += self.dmi.ack.eq(1)
            # bus transaction
            with m.Switch(self.dmi.addr):
                for addr, reg in self._registers.items():
                    with m.Case(addr):
                        # Check the operation
                        with m.If(self.dmi.wen):
                            write(addr, reg)
                        with m.Else():
                            read(addr, reg)
        with m.Else():
            m.d.sync += self.dmi.ack.eq(0)

        # reset the update flag
        for reg in self._registers.values():
            with m.If(reg.update):
                m.d.sync += reg.update.eq(0)

        return m
