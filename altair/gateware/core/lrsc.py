from amaranth import Signal
from amaranth import Module
from amaranth import Elaboratable
from amaranth.build import Platform


class LRSC(Elaboratable):
    class SnoopPort:
        def __init__(self):
            self.address = Signal(30)
            self.we      = Signal()
            self.valid   = Signal()
            self.ack     = Signal()

    def __init__(self) -> None:
        self.snoop              = LRSC.SnoopPort()
        self.internal           = LRSC.SnoopPort()
        self.cancel_reservation = Signal()
        self.is_lr              = Signal()
        self.is_sc              = Signal()
        self.sc_ok              = Signal()
        self.sc_fail            = Signal()

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        reservation = Signal(30)
        valid_reservation = Signal()

        # Do the reservation (LR)
        with m.If(self.cancel_reservation):
            m.d.sync += valid_reservation.eq(0)
        with m.Elif(self.is_lr & self.internal.valid & ~self.internal.we & self.internal.ack):
            m.d.sync += [
                reservation.eq(self.internal.address),
                valid_reservation.eq(1)
            ]
        with m.Elif(self.snoop.valid & self.snoop.we & self.snoop.ack & (reservation == self.snoop.address)):
            m.d.sync += valid_reservation.eq(0)

        # Check reservaton (SC)
        with m.If(self.is_sc):
            with m.If((reservation == self.internal.address) & valid_reservation):
                m.d.comb += self.sc_ok.eq(1)
            with m.Else():
                m.d.comb += self.sc_fail.eq(1)

        return m
