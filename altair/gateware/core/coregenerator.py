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
        rom_img = generate_and_load(path=build_path, start=rom[0], target=mport[0], size=1 << rom[1])
        # Instantiate
        self._cores = [Core(reset_address=reset_address,
                            enable_rv32m=enable_rv32m,
                            enable_rv32a=enable_rv32a,
                            enable_extra_csr=enable_extra_csr,
                            enable_user_mode=enable_user_mode,
                            enable_triggers=enable_triggers,
                            ntriggers=ntriggers,
                            debug_enable=debug_enable,
                            hartid=idx) for idx in range(ncores)]
        self._coreint = CoreInterrupts(ncores=ncores)
        self._plic    = PLIC(ncores=ncores, ninterrupts=plic_nint)
        self._rom     = ROM(addr_width=rom[1], rom_img=rom_img)
        # Internal Slave ports
        self._coreint_port = CoreGenerator.SlavePort(addr_start=coreint_address, addr_width=CoreInterrupts.ADDR_WIDTH, features=[], ifname='coreint')
        self._plic_port    = CoreGenerator.SlavePort(addr_start=plic_address, addr_width=PLIC.ADDR_WIDTH, features=[], ifname='plic')
        self._rom_port     = CoreGenerator.SlavePort(addr_start=rom[0], addr_width=rom[1], features=[], ifname='rom')
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
        # Register
        for idx, core in enumerate(self._cores):
            setattr(m.submodules, f'core{idx}', core)  # get a proper name in the trace
        m.submodules.coreint = self._coreint
        m.submodules.rom     = self._rom
        m.submodules.plic    = self._plic
        # ------------------------------------------------------------
        # Connections
        # CPU: connect TI, SI, EI, and snoop bus (TODO: rework the atomics...)
        for idx, core in enumerate(self._cores):
            m.d.comb += [
                core.timer_interrupt.eq(self._coreint.timer_interrupt[idx]),
                core.software_interrupt.eq(self._coreint.software_interrupt[idx]),
                core.external_interrupt.eq(self._plic.core_interrupt[idx])
            ]
            if hasattr(core, 'snoop'):
                m.d.comb += [
                    core.snoop.address.eq(self.mport.interface.adr),
                    core.snoop.we.eq(self.mport.interface.we),
                    core.snoop.valid.eq(self.mport.interface.cyc),
                    core.snoop.ack.eq(self.mport.interface.ack)
                ]
        # Connect slave ports
        m.d.comb += [
            self._coreint_port.interface.connect(self._coreint.wbport),
            self._plic_port.interface.connect(self._plic.wbport),
            self._rom_port.interface.connect(self._rom.wbport)
        ]
        # Connect IO for external interrupts to the PLIC
        m.d.comb += self._plic.interrupts.eq(self.interrupts)
        # ------------------------------------------------------------
        # build the interconnect
        masters = [core.wbport for core in self._cores]
        slaves  = [self.mport, self.io, self._coreint_port, self._plic_port, self._rom_port]

        if len(masters) == 1:
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
