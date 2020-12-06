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
from altair.gateware.platform.coreint import CoreInterrupts
from altair.gateware.platform.plic import PLIC
from typing import List


class CoreGenerator(Elaboratable):
    class SlavePort:
        def __init__(self, *, addr_start: int, addr_width: int, features: List[str], ifname: str) -> None:
            self.interface = Interface(addr_width=addr_width - 2, data_width=32, granularity=8,
                                       features=features, name=ifname)
            self.name                 = ifname
            self.interface.memory_map = MemoryMap(addr_width=addr_width, data_width=8)
            self.addr_start           = addr_start
            self.addr_width           = addr_width

    def __init__(self,
                 # Core
                 reset_address: int = 0x8000_0000,
                 enable_rv32m: bool = False,
                 enable_rv32a: bool = False,
                 enable_extra_csr: bool = False,
                 enable_user_mode: bool = False,
                 enable_triggers: bool = False,
                 ntriggers: int = 4,
                 debug_enable: bool = False,
                 # SoC
                 ncores: int = 1,
                 coreint_address: int = 0x2000_0000,
                 plic_address: int = 0x3000_0000,
                 plic_nint: int = 16,
                 external_ports: dict = {}
                 ) -> None:
        # ----------------------------------------------------------------------
        # config
        self.core_kw = dict(reset_address=reset_address,
                            enable_rv32m=enable_rv32m,
                            enable_rv32a=enable_rv32a,
                            enable_extra_csr=enable_extra_csr,
                            enable_user_mode=enable_user_mode,
                            enable_triggers=enable_triggers,
                            ntriggers=ntriggers,
                            debug_enable=debug_enable)
        self._ncores       = ncores
        self._coreint_addr = coreint_address
        self._plic_addr    = plic_address
        self._plic_nint    = plic_nint
        # IO
        self.extports = [CoreGenerator.SlavePort(addr_start=start, addr_width=size, features=['err'], ifname=ifname)
                         for ifname, (start, size) in external_ports.items()]
        self.interrupts = Signal(plic_nint)

    def port_list(self) -> list:
        mport = [getattr(port.interface, name) for port in self.extports for name, _, _ in port.interface.layout]

        return [
            *mport,
            self.interrupts
        ]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # search for 'mport'
        # TODO maybe make 'mport' and 'ioport' the default ports. O incluir múltiple 'snoop' ports
        # for now, the snoop ports listen the only memory port.
        mport = [port for port in self.extports if port.name == 'mport'][0]
        # ------------------------------------------------------------
        # instantiate the cores
        cores = [Core(**self.core_kw, hartid=idx) for idx in range(self._ncores)]
        for idx, core in enumerate(cores):
            setattr(m.submodules, f'core{idx}', core)  # get a proper name in the trace
            if self.core_kw['enable_rv32a']:
                m.d.comb += [
                    core.snoop.address.eq(mport.interface.adr),
                    core.snoop.we.eq(mport.interface.we),
                    core.snoop.valid.eq(mport.interface.cyc),
                    core.snoop.ack.eq(mport.interface.ack)
                ]

        # ------------------------------------------------------------
        # instantiate CoreInt
        coreint = m.submodules.coreint = CoreInterrupts(ncores=self._ncores)
        coreint_port = CoreGenerator.SlavePort(addr_start=self._coreint_addr, addr_width=16, features=[], ifname='coreint')

        m.d.comb += coreint_port.interface.connect(coreint.wbport)
        # connect TI and SI
        for idx, core in enumerate(cores):
            m.d.comb += [
                core.timer_interrupt.eq(coreint.timer_interrupt[idx]),
                core.software_interrupt.eq(coreint.software_interrupt[idx])
            ]
        # ------------------------------------------------------------
        # instantiate PLIC
        plic = m.submodules.plic = PLIC(ncores=self._ncores, ninterrupts=self._plic_nint)
        plic_port = CoreGenerator.SlavePort(addr_start=self._plic_addr, addr_width=16, features=[], ifname='plic')

        m.d.comb += [
            plic_port.interface.connect(plic.wbport),
            plic.interrupts.eq(self.interrupts)
        ]
        for idx, core in enumerate(cores):
            m.d.comb += core.external_interrupt.eq(plic.core_interrupt[idx])

        # ------------------------------------------------------------
        # build the interconnect
        masters = [core.wbport for core in cores]
        slaves  = [*self.extports, coreint_port, plic_port]

        if self._ncores == 1:
            decoder = m.submodules.decoder = Decoder(addr_width=30, data_width=32, granularity=8, features=['err'])

            for slave in slaves:
                decoder.add(slave.interface, addr=slave.addr_start)

            m.d.comb += masters[0].connect(decoder.bus)
        else:
            # crossbar
            # create the matrix
            access = [[Interface(addr_width=slave.addr_width - 2, data_width=32, granularity=8, features=['err']) for slave in slaves]
                      for _ in enumerate(masters)]
            for row in access:
                for port, slave in zip(row, slaves):
                    port.memory_map = slave.interface.memory_map

            # decode each master to access row
            for row, master in zip(access, masters):
                decoder = Decoder(addr_width=30, data_width=32, granularity=8, features=['err'])
                m.submodules += decoder

                for bus, slave in zip(row, slaves):
                    decoder.add(bus, addr=slave.addr_start)

                m.d.comb += master.connect(decoder.bus)

            # arbitrate the column to slave
            for column, slave in zip(zip(*access), slaves):
                arbiter = Arbiter(addr_width=slave.addr_width - 2, data_width=32, granularity=8)
                m.submodules += arbiter

                for bus in column:
                    arbiter.add(bus)

                m.d.comb += arbiter.bus.connect(slave.interface)

        return m
