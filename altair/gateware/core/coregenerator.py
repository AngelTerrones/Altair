#!/usr/bin/env python3

from amaranth import Signal
from amaranth import Module
from amaranth import Elaboratable
from amaranth.build import Platform
from amaranth_soc.memory import MemoryMap
from amaranth_soc.wishbone.bus import Arbiter
from amaranth_soc.wishbone.bus import Decoder
from amaranth_soc.wishbone.bus import Interface
from altair.gateware.core import Core
from altair.gateware.platform.coreint import CoreInterrupts
from altair.gateware.platform.plic import PLIC
from altair.gateware.platform.rom import ROM
from altair.boot.generate import generate_and_load
from typing import List


class CoreGenerator(Elaboratable):
    class SlavePort:
        def __init__(self, *, addr_start: int, addr_width: int, features: List[str], ifname: str) -> None:
            """Create the memory interface (bus): address width for words and a granularity of 8, enabling
            byte addressing.
            The memory map must be addr_width + 2 in this case (+2 due to data_width/granularity = 4 bytes per word)
            """
            iface = Interface(addr_width=addr_width, data_width=32, granularity=8, features=features, name=ifname)
            iface.memory_map = MemoryMap(addr_width=addr_width + 2, data_width=8)
            self.interface   = iface
            self.name        = ifname
            self.addr_start  = addr_start
            self.addr_width  = addr_width

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
                 rom: list = [],
                 mport: list = [],
                 io: list = [],
                 # build
                 build_path: str = 'build/'
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
        self._rom          = rom
        self._build_path   = build_path
        # IO
        self.mport      = CoreGenerator.SlavePort(addr_start=mport[0], addr_width=mport[1], features=['err'], ifname='mport')
        self.io         = CoreGenerator.SlavePort(addr_start=io[0], addr_width=io[1], features=['err'], ifname='io')
        self.interrupts = Signal(plic_nint)

    def port_list(self) -> list:
        mport = [getattr(self.mport.interface, name) for name, _, _ in self.mport.interface.layout]
        io    = [getattr(self.io.interface, name) for name, _, _ in self.io.interface.layout]

        return [
            *mport,
            *io,
            self.interrupts
        ]

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # ------------------------------------------------------------
        # instantiate the cores
        cores = [Core(**self.core_kw, hartid=idx) for idx in range(self._ncores)]
        for idx, core in enumerate(cores):
            setattr(m.submodules, f'core{idx}', core)  # get a proper name in the trace
            if self.core_kw['enable_rv32a']:
                m.d.comb += [
                    core.snoop.address.eq(self.mport.interface.adr),
                    core.snoop.we.eq(self.mport.interface.we),
                    core.snoop.valid.eq(self.mport.interface.cyc),
                    core.snoop.ack.eq(self.mport.interface.ack)
                ]

        # ------------------------------------------------------------
        # instantiate CoreInt
        coreint = m.submodules.coreint = CoreInterrupts(ncores=self._ncores)
        coreint_port = CoreGenerator.SlavePort(addr_start=self._coreint_addr, addr_width=CoreInterrupts.ADDR_WIDTH, features=[], ifname='coreint')

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
        plic_port = CoreGenerator.SlavePort(addr_start=self._plic_addr, addr_width=PLIC.ADDR_WIDTH, features=[], ifname='plic')

        m.d.comb += [
            plic_port.interface.connect(plic.wbport),
            plic.interrupts.eq(self.interrupts)
        ]
        for idx, core in enumerate(cores):
            m.d.comb += core.external_interrupt.eq(plic.core_interrupt[idx])
        # ------------------------------------------------------------
        # ROM
        rom_img = generate_and_load(path=self._build_path, start=self._rom[0], target=self.mport.addr_start, size=1 << self._rom[1])
        rom = m.submodules.rom = ROM(addr_width=self._rom[1], rom_img=rom_img)
        rom_port = CoreGenerator.SlavePort(addr_start=self._rom[0], addr_width=self._rom[1], features=[], ifname='rom')

        m.d.comb += rom_port.interface.connect(rom.wbport)
        # ------------------------------------------------------------
        # build the interconnect
        masters = [core.wbport for core in cores]
        slaves  = [self.mport, self.io, coreint_port, plic_port, rom_port]

        if self._ncores == 1:
            decoder = m.submodules.decoder = Decoder(addr_width=30, data_width=32, granularity=8, features=['err'])

            for slave in slaves:
                decoder.add(slave.interface, addr=slave.addr_start)

            m.d.comb += masters[0].connect(decoder.bus)
        else:
            # crossbar
            # create the matrix
            access = [[Interface(addr_width=slave.addr_width, data_width=32, granularity=8, features=['err'], name=f'xbar{idm}{ids}')for ids, slave in enumerate(slaves)]
                      for idm, _ in enumerate(masters)]
            for row in access:
                for port, slave in zip(row, slaves):
                    port.memory_map = slave.interface.memory_map

            # decode each master to access row
            for idx, (row, master) in enumerate(zip(access, masters)):
                decoder = Decoder(addr_width=30, data_width=32, granularity=8, features=['err'])
                setattr(m.submodules, f'xbar_decoder_{idx}', decoder)  # get a proper name in the trace

                for bus, slave in zip(row, slaves):
                    decoder.add(bus, addr=slave.addr_start)

                m.d.comb += master.connect(decoder.bus)

            # arbitrate the column to slave
            for column, slave in zip(zip(*access), slaves):
                features = []
                if hasattr(slave.interface, 'err'):
                    features = ['err']
                arbiter = Arbiter(addr_width=slave.addr_width, data_width=32, granularity=8, features=features)
                setattr(m.submodules, f'xbar_arbiter_{slave.name}', arbiter)  # get a proper name in the trace

                for bus in column:
                    arbiter.add(bus)

                m.d.comb += arbiter.bus.connect(slave.interface)

        return m
