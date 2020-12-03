#!/usr/bin/env python3

from nmigen import Cat
from nmigen import Signal
from nmigen import Module
from nmigen import Elaboratable
from nmigen.build import Platform
from nmigen_soc.csr.bus import Element
from nmigen_soc.csr.bus import Multiplexer
from nmigen_soc.csr.wishbone import WishboneCSRBridge


class CoreInterrupts(Elaboratable):
    # the addressing is done by words...
    # Max number of cores: 256
    SIZE_MTIMECMP = 1
    SIZE_XTIMER   = 2
    BASE_MSIP     = 0
    BASE_MTIMECMP = BASE_MSIP + (256 * SIZE_MTIMECMP)
    BASE_MTIME    = BASE_MTIMECMP + (256 * SIZE_XTIMER)

    def __init__(self, ncores: int = 1) -> None:
        # ----------------------------------------------------------------------
        # config
        self._ncores  = ncores
        self._clk_div = 10  # TODO make this a parameter.
        # ----------------------------------------------------------------------
        # control registers
        self._msip     = [Element(1, 'rw', name=f'msip{n}') for n in range(ncores)]
        self._mtimecmp = [Element(64, 'rw', name=f'mtimecmp{n}') for n in range(ncores)]
        self._mtime    = Element(64, 'rw', name='mtime')
        # ----------------------------------------------------------------------
        # Add the registers to the mux. Create the bridge
        self._mux = Multiplexer(addr_width=14, data_width=32)
        for idx, msip in enumerate(self._msip):
            self._mux.add(msip, addr=CoreInterrupts.BASE_MSIP + (CoreInterrupts.SIZE_MTIMECMP * idx))
        for idx, mtimecmp in enumerate(self._mtimecmp):
            self._mux.add(mtimecmp, addr=CoreInterrupts.BASE_MTIMECMP + (CoreInterrupts.SIZE_XTIMER * idx))
        self._mux.add(self._mtime, addr=CoreInterrupts.BASE_MTIME)

        self._bridge = WishboneCSRBridge(self._mux.bus, data_width=32)
        # ----------------------------------------------------------------------
        # IO
        self.wbport             = self._bridge.wb_bus
        self.timer_interrupt    = Signal(ncores)
        self.software_interrupt = Signal(ncores)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        m.submodules.mux    = self._mux
        m.submodules.bridge = self._bridge

        ti_matches = [Signal() for _ in range(self._ncores)]
        msip       = [register.r_data[0] for register in self._msip]

        # ------------------------------------------------------------
        # connect the SI/TI bits
        m.d.comb += [
            self.timer_interrupt.eq(Cat(ti_matches)),
            self.software_interrupt.eq(Cat(msip))
        ]

        # ------------------------------------------------------------
        # Software interrupts
        for register in self._msip:
            with m.If(register.w_stb):
                m.d.sync += register.r_data.eq(register.w_data)

        # ------------------------------------------------------------
        # Timer
        clk_div = Signal(range(self._clk_div), reset=self._clk_div - 1)
        time    = Signal(64)
        timecmp = [Signal(64, reset=-1) for _ in range(self._ncores)]

        # clk div + timer
        m.d.sync += clk_div.eq(clk_div - 1)
        with m.If(clk_div == 0):
            m.d.sync += [
                clk_div.eq(clk_div.reset),
                time.eq(time + 1)
            ]

        # compare
        for cmp, match in zip(timecmp, ti_matches):
            m.d.sync += match.eq(time >= cmp)

        # Bus handling: read
        m.d.comb += self._mtime.r_data.eq(time)
        for rcmp, cmp in zip(self._mtimecmp, timecmp):
            m.d.comb += rcmp.r_data.eq(cmp)

        # Bus handling: write
        with m.If(self._mtime.w_stb):
            m.d.sync += time.eq(self._mtime.w_data)
        for rcmp, cmp in zip(self._mtimecmp, timecmp):
            with m.If(rcmp.w_stb):
                m.d.sync += cmp.eq(rcmp.w_data)

        return m
