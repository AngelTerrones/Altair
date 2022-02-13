from amaranth import Cat
from amaranth import Repl
from amaranth import Signal
from amaranth import Module
from amaranth import Elaboratable
from amaranth.build import Platform
from amaranth_soc.wishbone.bus import Arbiter
from amaranth_soc.wishbone.bus import Decoder
from amaranth_soc.wishbone.bus import Interface
from amaranth_soc.wishbone.bus import CycleType
from amaranth_soc.wishbone.bus import BurstTypeExt
from altair.gateware.core.lrsc import LRSC


class _Arbiter(Arbiter):
    """Clone the arbiter from Amaranth SoC, and add the grant as an output port
    Wishbone bus arbiter.

    A round-robin arbiter for initiators accessing a shared Wishbone bus.

    Parameters
    ----------
    addr_width : int
        Address width. See :class:`Interface`.
    data_width : int
        Data width. See :class:`Interface`.
    granularity : int
        Granularity. See :class:`Interface`
    features : iter(str)
        Optional signal set. See :class:`Interface`.

    Attributes
    ----------
    bus : :class:`Interface`
        Shared Wishbone bus.
    """
    def __init__(self, *,nmasters, addr_width, data_width, granularity=None, features=...):
        self.grant = Signal(range(nmasters))
        super().__init__(addr_width=addr_width, data_width=data_width,
                         granularity=granularity, features=features)

    def elaborate(self, platform):
        m = Module()

        requests = Signal(len(self._intrs))
        grant    = Signal(range(len(self._intrs)))
        m.d.comb += [
            self.grant.eq(grant),  # I need this...
            requests.eq(Cat(intr_bus.cyc for intr_bus in self._intrs))
        ]

        bus_busy = self.bus.cyc
        if hasattr(self.bus, "lock"):
            # If LOCK is not asserted, we also wait for STB to be deasserted before granting bus
            # ownership to the next initiator. If we didn't, the next bus owner could receive
            # an ACK (or ERR, RTY) from the previous transaction when targeting the same
            # peripheral.
            bus_busy &= self.bus.lock | self.bus.stb

        with m.If(~bus_busy):
            with m.Switch(grant):
                for i in range(len(requests)):
                    with m.Case(i):
                        for pred in reversed(range(i)):
                            with m.If(requests[pred]):
                                m.d.sync += grant.eq(pred)
                        for succ in reversed(range(i + 1, len(requests))):
                            with m.If(requests[succ]):
                                m.d.sync += grant.eq(succ)

        with m.Switch(grant):
            for i, intr_bus in enumerate(self._intrs):
                m.d.comb += intr_bus.dat_r.eq(self.bus.dat_r)
                if hasattr(intr_bus, "stall"):
                    intr_bus_stall = Signal(reset=1)
                    m.d.comb += intr_bus.stall.eq(intr_bus_stall)

                with m.Case(i):
                    ratio = intr_bus.granularity // self.bus.granularity
                    m.d.comb += [
                        self.bus.adr.eq(intr_bus.adr),
                        self.bus.dat_w.eq(intr_bus.dat_w),
                        self.bus.sel.eq(Cat(Repl(sel, ratio) for sel in intr_bus.sel)),
                        self.bus.we.eq(intr_bus.we),
                        self.bus.stb.eq(intr_bus.stb),
                    ]
                    m.d.comb += self.bus.cyc.eq(intr_bus.cyc)
                    if hasattr(self.bus, "lock"):
                        m.d.comb += self.bus.lock.eq(getattr(intr_bus, "lock", 0))
                    if hasattr(self.bus, "cti"):
                        m.d.comb += self.bus.cti.eq(getattr(intr_bus, "cti", CycleType.CLASSIC))
                    if hasattr(self.bus, "bte"):
                        m.d.comb += self.bus.bte.eq(getattr(intr_bus, "bte", BurstTypeExt.LINEAR))

                    m.d.comb += intr_bus.ack.eq(self.bus.ack)
                    if hasattr(intr_bus, "err"):
                        m.d.comb += intr_bus.err.eq(getattr(self.bus, "err", 0))
                    if hasattr(intr_bus, "rty"):
                        m.d.comb += intr_bus.rty.eq(getattr(self.bus, "rty", 0))
                    if hasattr(intr_bus, "stall"):
                        m.d.comb += intr_bus_stall.eq(getattr(self.bus, "stall", ~self.bus.ack))

        return m


class XBAR(Elaboratable):
    def __init__(self, *, masters, slaves, features) -> None:
        self.masters = masters
        self.slaves  = slaves

        # create the matrix
        access = [[Interface(addr_width=slave.addr_width,
                             data_width=32,
                             granularity=8,
                             features=features,
                             name=f'xifc_{idm}{ids}') for ids, slave in enumerate(slaves)]
                       for idm, _ in enumerate(masters)]
        for row in access:
            for port, slave in zip(row, slaves):
                port.memory_map = slave.interface.memory_map

        # Decoders for row access
        self.decoders = [Decoder(addr_width=30, data_width=32, granularity=8, features=features) for _ in masters]
        for row, decoder in zip(access, self.decoders):
            for bus, slave in zip(row, slaves):
                decoder.add(bus, addr=slave.addr_start)

        # Arbiters for each column/slave
        self.arbiters = [_Arbiter(nmasters=len(self.masters), addr_width=slave.addr_width, data_width=32, granularity=8, features=features) for slave in slaves]
        for column, arbiter in zip(zip(*access), self.arbiters):
            for bus in column:
                arbiter.add(bus)

        if 'lock' in features:
            nmasters     = len(masters)
            self.atomics = True
            self.lrsc    = [LRSC(nmasters=nmasters) for _ in slaves]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # connect masters <-> decoder
        for idx, (decoder, master) in enumerate(zip(self.decoders, self.masters)):
            setattr(m.submodules, f'decoder_{idx}', decoder)  # get a proper name in the trace
            m.d.comb += master.connect(decoder.bus)

        # connect arbiter <-> slave
        for idx, (arbiter, slave) in enumerate(zip(self.arbiters, self.slaves)):
            setattr(m.submodules, f'arbiter_{idx}_{slave.name}', arbiter)  # get a proper name in the trace
            m.d.comb += arbiter.bus.connect(slave.interface)

        if self.atomics:
            for lrsc, slave, arbiter in zip(self.lrsc, self.slaves, self.arbiters):
                setattr(m.submodules, f'lrsc_{slave.name}', lrsc)
                # do the connection
                lrsc.tap_bus(m=m, idx=arbiter.grant, master=arbiter.bus, slave=slave.interface)

        return m
