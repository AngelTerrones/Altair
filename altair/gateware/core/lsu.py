from amaranth import Cat
from amaranth import Repl
from amaranth import Signal
from amaranth import Module
from amaranth import Elaboratable
from amaranth.build import Platform
from amaranth_soc.wishbone.bus import Interface
from altair.gateware.core.isa import Funct3


class _DataFormat(Elaboratable):
    def __init__(self) -> None:
        self.op         = Signal(Funct3)
        self.offset     = Signal(2)
        self.byte_sel   = Signal(4)
        self.store_data = Signal(32)
        self.data_write = Signal(32)
        self.data_read  = Signal(32)
        self.load_data  = Signal(32)
        self.misaligned = Signal()

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # create byte selector
        with m.Switch(self.op):
            with m.Case(Funct3.B):
                m.d.comb += self.byte_sel.eq(0b0001 << self.offset)
            with m.Case(Funct3.H):
                m.d.comb += self.byte_sel.eq(0b0011 << self.offset)
            with m.Case(Funct3.W):
                m.d.comb += self.byte_sel.eq(0b1111)

        # format write data
        with m.Switch(self.op):
            with m.Case(Funct3.B):
                m.d.comb += self.data_write.eq(Repl(self.store_data[:8], 4))
            with m.Case(Funct3.H):
                m.d.comb += self.data_write.eq(Repl(self.store_data[:16], 2))
            with m.Case(Funct3.W):
                m.d.comb += self.data_write.eq(self.store_data)

        # format input data
        _byte = Signal((8, True))
        _half = Signal((16, True))

        m.d.comb += [
            _byte.eq(self.data_read.word_select(self.offset, 8)),
            _half.eq(self.data_read.word_select(self.offset[1], 16)),
        ]

        with m.Switch(self.op):
            with m.Case(Funct3.B):
                m.d.comb += self.load_data.eq(_byte)
            with m.Case(Funct3.BU):
                m.d.comb += self.load_data.eq(Cat(_byte, 0))  # make sign bit = 0
            with m.Case(Funct3.H):
                m.d.comb += self.load_data.eq(_half)
            with m.Case(Funct3.HU):
                m.d.comb += self.load_data.eq(Cat(_half, 0))  # make sign bit = 0
            with m.Case(Funct3.W):
                m.d.comb += self.load_data.eq(self.data_read)

        # exception/misaligment
        with m.Switch(self.op):
            with m.Case(Funct3.H, Funct3.HU):
                m.d.comb += self.misaligned.eq(self.offset[0])
            with m.Case(Funct3.W):
                m.d.comb += self.misaligned.eq(self.offset != 0)

        return m


class LoadStoreUnit(Elaboratable):
    def __init__(self, features) -> None:
        # submodules
        self._dataformat = _DataFormat()
        # IO
        self.mport      = Interface(addr_width=30, data_width=32, granularity=8, features=features, name='mport')
        self.address    = Signal(32)
        self.store_data = Signal(32)
        self.load_data  = Signal(32)
        self.write      = Signal()
        self.cycle      = Signal()
        self.strobe     = Signal()
        self.op         = Signal(Funct3)
        self.ready      = Signal()
        self.error      = Signal()
        self.misaligned = Signal()
        self.lrsc       = Signal()

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        m.submodules.dataformat = self._dataformat

        m.d.comb += [
            self._dataformat.op.eq(self.op),
            self._dataformat.offset.eq(self.address[:2]),
            self._dataformat.store_data.eq(self.store_data),
            self.load_data.eq(self._dataformat.load_data),
            self.misaligned.eq(self._dataformat.misaligned),

            self.mport.adr.eq(self.address[2:]),
            self.mport.dat_w.eq(self._dataformat.data_write),
            self.mport.sel.eq(self._dataformat.byte_sel),
            self.mport.we.eq(self.write),
            self.mport.cyc.eq(~self.misaligned & self.cycle),
            self.mport.stb.eq(self.strobe),

            self.ready.eq(self.mport.ack),
            self.error.eq(self.mport.err),
            self._dataformat.data_read.eq(self.mport.dat_r)
        ]

        if hasattr(self.mport, 'lock'):
            m.d.comb += self.mport.lock.eq(self.lrsc)

        return m
