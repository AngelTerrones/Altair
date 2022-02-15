from amaranth import Cat
from amaranth import Signal
from amaranth import Record
from amaranth import Module
from amaranth import Elaboratable
from amaranth.build import Platform
from amaranth.lib.cdc import FFSynchronizer
from altair.gateware.debug.layout import jtag_port_layout


class _JTAGRegister(Record):
    def __init__(self, layout: list, src_loc_at=0):
        temp = [
            ('read',   layout),
            ('write',  layout),
            ('update', 1),
            ('reset',  1),
        ]
        super().__init__(temp, src_loc_at=src_loc_at)


class JTAGTap(Elaboratable):
    def __init__(self, regmap, ir_width=5, ir_reset=0x01) -> None:
        self.port = Record(jtag_port_layout)
        self.regs = {addr: _JTAGRegister(layout) for addr, layout in regmap.items()}
        self.ir   = Signal(ir_width, reset=ir_reset)
        self.dr   = Signal(max(len(port.read) for port in self.regs.values()))

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # synchronize the inputs
        tck = Signal.like(self.port.tck)
        tdi = Signal.like(self.port.tdi)
        tms = Signal.like(self.port.tms)

        m.submodules += [
            FFSynchronizer(self.port.tck, tck),
            FFSynchronizer(self.port.tdi, tdi),
            FFSynchronizer(self.port.tms, tms)
        ]
        # generate the clock and neg-edge detection
        tck_rise = Signal()
        tck_fall = Signal()
        _tck     = Signal()

        m.d.sync += _tck.eq(tck)
        m.d.comb += [
            tck_rise.eq(~_tck & tck),
            tck_fall.eq(_tck  & ~tck)
        ]
        # Latch TDI and TMS at TCK falling edge
        _tdi = Signal()
        _tms = Signal()

        with m.If(tck_fall):
            m.d.sync += [
                _tdi.eq(tdi),
                _tms.eq(tms)
            ]

        # FSM
        with m.FSM(name='TAP_controller'):
            with m.State('TEST-LOGIC-RESET'):
                m.d.sync += self.ir.eq(self.ir.reset)
                with m.If(tck_rise):
                    with m.If(~_tms):
                        m.next = 'RUN-TEST-IDLE'
            with m.State('RUN-TEST-IDLE'):
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'SELECT-DR-SCAN'
            # DR path
            with m.State('SELECT-DR-SCAN'):
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'SELECT-IR-SCAN'
                    with m.Else():
                        m.next = 'CAPTURE-DR'
            with m.State('CAPTURE-DR'):
                with m.Switch(self.ir):
                    for addr, reg in self.regs.items():
                        with m.Case(addr):
                            with m.If(tck_rise):
                                m.d.sync += self.dr.eq(reg.read)
                # Move
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'EXIT1-DR'
                    with m.Else():
                        m.next = 'SHIFT-DR'
            with m.State('SHIFT-DR'):
                with m.If(tck_fall):
                    m.d.sync += self.port.tdo.eq(self.dr[0])
                with m.Switch(self.ir):
                    for addr, reg in self.regs.items():
                        with m.Case(addr):
                            with m.If(tck_rise):
                                m.d.sync += self.dr.eq(Cat(self.dr[1:len(reg.read)], _tdi))
                # Move
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'EXIT1-DR'
            with m.State('EXIT1-DR'):
                with m.If(tck_fall):
                    m.d.sync += self.port.tdo.eq(0)
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'UPDATE-DR'
                    with m.Else():
                        m.next = 'PAUSE-DR'
            with m.State('PAUSE-DR'):
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'EXIT2-DR'
            with m.State('EXIT2-DR'):
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'UPDATE-DR'
                    with m.Else():
                        m.next = 'SHIFT-DR'
            with m.State('UPDATE-DR'):
                with m.Switch(self.ir):
                    for addr, reg in self.regs.items():
                        with m.Case(addr):
                            m.d.sync += reg.write.eq(self.dr)
                            # handle the write in another module...
                            # If the register is RO: the update will be ignored
                            m.d.comb += reg.update.eq(tck_fall)
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'SELECT-DR-SCAN'
                    with m.Else():
                        m.next = 'RUN-TEST-IDLE'
            # IR path
            with m.State('SELECT-IR-SCAN'):
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'TEST-LOGIC-RESET'
                    with m.Else():
                        m.next = 'CAPTURE-IR'
            with m.State('CAPTURE-IR'):
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'EXIT1-IR'
                    with m.Else():
                        m.next = 'SHIFT-IR'
            with m.State('SHIFT-IR'):
                with m.If(tck_fall):
                    m.d.sync += self.port.tdo.eq(self.ir[0])
                with m.If(tck_rise):
                    m.d.sync += self.ir.eq(Cat(self.ir[1:], _tdi))
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'EXIT1-IR'
            with m.State('EXIT1-IR'):
                with m.If(tck_fall):
                    m.d.sync += self.port.tdo.eq(0)
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'UPDATE-IR'
                    with m.Else():
                        m.next = 'PAUSE-IR'
            with m.State('PAUSE-IR'):
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'EXIT2-IR'
            with m.State('EXIT2-IR'):
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'UPDATE-IR'
                    with m.Else():
                        m.next = 'SHIFT-IR'
            with m.State('UPDATE-IR'):
                with m.If(tck_rise):
                    with m.If(_tms):
                        m.next = 'SELECT-DR-SCAN'
                    with m.Else():
                        m.next = 'RUN-TEST-IDLE'

        return m
