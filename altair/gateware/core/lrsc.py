from ast import LShift
from curses.ascii import SI
from amaranth import Signal
from amaranth import Module
from amaranth import Elaboratable
from amaranth.build import Platform


class LRSC(Elaboratable):
    def __init__(self, nmasters) -> None:
        self.idx     = Signal(range(nmasters))
        self.address = Signal(30)
        self.we      = Signal()
        self.lock    = Signal()
        self.valid   = Signal()
        self.ack     = Signal()
        self.sc_fail = Signal()

    def tap_bus(self, *, m, idx, master, slave):
        m.d.comb += [
            self.idx.eq(idx),
            self.address.eq(master.adr),
            self.we.eq(master.we),
            self.lock.eq(master.lock),
            self.valid.eq(master.cyc),
            self.ack.eq(master.ack),
        ]
        with m.If(master.lock):
            with m.If(master.we):
                # For writes, default to 0
                m.d.comb += master.dat_r.eq(0)
            with m.If(self.sc_fail):
                # negate the transaction.
                m.d.comb += [
                    slave.cyc.eq(0),
                    slave.stb.eq(0),
                    master.ack.eq(1),
                    master.dat_r.eq(1),
                ]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        idx_reservation   = Signal.like(self.idx)
        reservation       = Signal(30)
        valid_reservation = Signal()

        reservation_match = reservation == self.address
        idx_match         = idx_reservation == self.idx

        # Do the reservation (LR)
        with m.If(self.lock & self.valid & ~self.we & self.ack):
            m.d.sync += [
                idx_reservation.eq(self.idx),
                reservation.eq(self.address),
                valid_reservation.eq(1)
            ]
        with m.Elif(self.valid & self.we & self.ack):
            m.d.sync += valid_reservation.eq(0)

        # Check reservaton (SC)
        with m.If(self.lock & self.valid & self.we):
            m.d.comb += self.sc_fail.eq(~(idx_match & reservation_match & valid_reservation))

        return m
