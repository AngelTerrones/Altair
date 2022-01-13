from amaranth import Module
from amaranth import Elaboratable
from amaranth.build import Platform
from amaranth_soc.wishbone.bus import Arbiter
from amaranth_soc.wishbone.bus import Decoder
from amaranth_soc.wishbone.bus import Interface


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
        self.arbiters = [Arbiter(addr_width=slave.addr_width, data_width=32, granularity=8, features=features) for slave in slaves]
        for column, arbiter in zip(zip(*access), self.arbiters):
            for bus in column:
                arbiter.add(bus)

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

        return m
