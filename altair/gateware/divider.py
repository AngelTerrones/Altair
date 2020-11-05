from nmigen import Mux
from nmigen import Module
from nmigen import Signal
from nmigen import Elaboratable
from nmigen.build import Platform
from altair.gateware.isa import Funct3


class Divider(Elaboratable):
    def __init__(self) -> None:
        self.op     = Signal(Funct3)   # input
        self.dat1   = Signal(32)  # input
        self.dat2   = Signal(32)  # input
        self.valid  = Signal()
        self.result = Signal(32)  # output
        self.ready  = Signal()    # output

    def elaborate(self, platform: Platform) -> Module:
        m             = Module()

        is_div        = Signal()
        is_divu       = Signal()
        is_rem        = Signal()
        dividend      = Signal(32)
        divisor       = Signal(63)
        quotient      = Signal(32)
        quotient_mask = Signal(32)
        start         = Signal()
        start_q       = Signal()
        running       = Signal()
        outsign       = Signal()

        m.d.comb += [
            is_div.eq(self.op == Funct3.DIV),
            is_divu.eq(self.op == Funct3.DIVU),
            is_rem.eq(self.op == Funct3.REM)
        ]

        m.d.sync += [
            start.eq(self.valid & ~self.ready),
            start_q.eq(start),
            self.ready.eq(0)
        ]

        with m.If(start & ~start_q):
            m.d.sync += [
                dividend.eq(Mux((is_div | is_rem) & self.dat1[-1], -self.dat1, self.dat1)),
                divisor.eq(Mux((is_div | is_rem) & self.dat2[-1], -self.dat2, self.dat2) << 31),
                outsign.eq((is_div & (self.dat1[-1] ^ self.dat2[-1]) & (self.dat2 != 0)) | (is_rem & self.dat1[-1])),
                quotient.eq(0),
                quotient_mask.eq(1 << 31),
                running.eq(1)
            ]
        with m.Elif((quotient_mask == 0) & running):
            m.d.sync += [
                running.eq(0),
                self.ready.eq(1)
            ]

            with m.If(is_div | is_divu):
                m.d.sync += self.result.eq(Mux(outsign, -quotient, quotient))
            with m.Else():
                m.d.sync += self.result.eq(Mux(outsign, -dividend, dividend))
        with m.Else():
            with m.If(divisor <= dividend):
                m.d.sync += [
                    dividend.eq(dividend - divisor),
                    quotient.eq(quotient | quotient_mask)
                ]
            m.d.sync += [
                divisor.eq(divisor >> 1),
                quotient_mask.eq(quotient_mask >> 1)
            ]

        return m
