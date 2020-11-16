#!/usr/bin/env python3

from nmigen import Signal
from nmigen import Module
from nmigen import Elaboratable
from nmigen.build import Platform
from nmigen_soc.memory import MemoryMap
from nmigen_soc.wishbone.bus import Arbiter
from nmigen_soc.wishbone.bus import Decoder
from nmigen_soc.wishbone.bus import Interface
from altair.gateware.core import Core


class CoreGenerator(Elaboratable):
    def __init__(self,
                 # Core
                 reset_address: int = 0x8000_0000,
                 enable_rv32m: bool = False,
                 enable_extra_csr: bool = False,
                 enable_user_mode: bool = False,
                 enable_triggers: bool = False,
                 ntriggers: int = 4,
                 debug_enable: bool = False,
                 # SoC
                 ncores: int = 1,
                 wbports: dict = {}
                 ) -> None:
        # ----------------------------------------------------------------------
        # config
        self.core_kw = dict(reset_address=reset_address,
                            enable_rv32m=enable_rv32m,
                            enable_extra_csr=enable_extra_csr,
                            enable_user_mode=enable_user_mode,
                            enable_triggers=enable_triggers,
                            ntriggers=ntriggers,
                            debug_enable=debug_enable)
        self.ncores  = ncores
        self.wbports = wbports
        # IO
        self.wbslaves = []
        for name, (start, size) in self.wbports.items():
            port = Interface(addr_width=size - 2, data_width=32, granularity=8, features=['err'], name=name)
            port.memory_map = MemoryMap(addr_width=size, data_width=8)
            self.wbslaves.append(port)

        self.external_interrupt = Signal()  # input
        self.timer_interrupt    = Signal()  # input
        self.software_interrupt = Signal()  # input

    def port_list(self) -> list:
        mport = [getattr(port, name) for port in self.wbslaves for name, _, _ in port.layout]

        return [
            *mport,
            self.external_interrupt,
            self.timer_interrupt,
            self.software_interrupt
        ]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # ------------------------------------------------------------
        # instantiate the cores
        cores = [Core(**self.core_kw) for _ in range(self.ncores)]
        for idx, core in enumerate(cores):
            setattr(m.submodules, f'core{idx}', core)  # get a proper name in the trace

        # ------------------------------------------------------------
        # build the interconnect
        nmasters = self.ncores
        nslaves  = len(self.wbports)
        masters  = [core.wbport for core in cores]
        slaves   = self.wbslaves

        if nmasters == 1 and nslaves == 1:
            # direct connection
            m.d.comb += masters[0].connect(slaves[0])
        elif nmasters == 1 and nslaves > 1:
            # decoder
            decoder = m.submodules.decoder = Decoder(addr_width=30, data_width=32, granularity=8, features=['err'])

            for (start, size), slave in zip(self.wbports.values(), slaves):
                decoder.add(slave, addr=start)

            m.d.comb += masters[0].connect(decoder.bus)
        elif nmasters > 1 and nslaves == 1:
            # arbiter
            arbiter = m.submodules.arbiter = Arbiter(addr_width=30, data_width=32, granularity=8, features=['err'])

            for master in masters:
                arbiter.add(master)

            m.d.comb += arbiter.bus.connect(slaves[0])
        else:
            # crossbar
            slave_start = [start for start, _ in self.wbports.values()]
            slave_size  = [size for _, size in self.wbports.values()]

            # create the matrix
            access      = [[Interface(addr_width=size - 2, data_width=32, granularity=8, features=['err']) for size in slave_size] for _ in enumerate(masters)]
            for row in access:
                for port, size in zip(row, slave_size):
                    port.memory_map = MemoryMap(addr_width=size, data_width=8)

            # decode each master to access row
            for row, master in zip(access, masters):
                decoder = Decoder(addr_width=30, data_width=32, granularity=8, features=['err'])
                m.submodules += decoder

                for bus, start in zip(row, slave_start):
                    decoder.add(bus, addr=start)

                m.d.comb += master.connect(decoder.bus)

            # arbitrate the column to slave
            for column, slave, size in zip(zip(*access), slaves, slave_size):
                arbiter = Arbiter(addr_width=size - 2, data_width=32, granularity=8, features=['err'])
                m.submodules += arbiter

                for bus in column:
                    arbiter.add(bus)

                m.d.comb += arbiter.bus.connect(slave)

        # ------------------------------------------------------------
        # connect the interrupt lines
        # TODO: connect to the PIC.
        for core in cores:
            m.d.comb += [
                core.external_interrupt.eq(self.external_interrupt),
                core.timer_interrupt.eq(self.timer_interrupt),
                core.software_interrupt.eq(self.software_interrupt)
            ]

        return m
