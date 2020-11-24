#!/usr/bin/env python3

from nmigen import Cat
from nmigen import Signal
from nmigen import Module
from nmigen import Elaboratable
from nmigen.lib.coding import PriorityEncoder
from nmigen.build import Platform
from nmigen_soc.csr.bus import Element
from nmigen_soc.csr.bus import Multiplexer
from nmigen_soc.csr.wishbone import WishboneCSRBridge
from nmigen_soc.event import Monitor
from nmigen_soc.event import Source
from nmigen_soc.event import EventMap


class PLIC(Elaboratable):
    # the addressing is done by words...
    SIZE         = 1
    BASE_PENDING = 0
    BASE_ENABLE  = BASE_PENDING + (256 * SIZE)
    BASE_SOURCE  = BASE_ENABLE + (256 * SIZE)
    BASE_CLEAR   = BASE_SOURCE + (256 * SIZE)

    def __init__(self, ncores: int = 1, ninterrupts: int = 2) -> None:
        if not isinstance(ninterrupts, int) or ninterrupts > 32:
            raise ValueError(f'ninterrupts must be an integer, not greater than 32: {ninterrupts}')
        # ----------------------------------------------------------------------
        # config
        self._ncores = ncores
        self._ninterrupts = ninterrupts
        # ----------------------------------------------------------------------
        # Control registers
        self._pending   = [Element(ninterrupts, 'r', name=f'pending{n}') for n in range(ncores)]
        self._enable    = [Element(ninterrupts, 'rw', name=f'enable{n}') for n in range(ncores)]
        self._source_id = [Element(32, 'r', name=f'source{n}') for n in range(ncores)]
        self._clear     = [Element(ninterrupts, 'rw', name=f'clear{n}') for n in range(ncores)]
        # ----------------------------------------------------------------------
        # Add the registers to the mux. Create the bridge
        self._mux    = Multiplexer(addr_width=14, data_width=32)
        for idx, reg in enumerate(self._pending):
            self._mux.add(reg, addr=PLIC.BASE_PENDING + (idx * PLIC.SIZE))
        for idx, reg in enumerate(self._enable):
            self._mux.add(reg, addr=PLIC.BASE_ENABLE + (idx * PLIC.SIZE))
        for idx, reg in enumerate(self._source_id):
            self._mux.add(reg, addr=PLIC.BASE_SOURCE + (idx * PLIC.SIZE))
        for idx, reg in enumerate(self._clear):
            self._mux.add(reg, addr=PLIC.BASE_CLEAR + (idx * PLIC.SIZE))
        self._bridge = WishboneCSRBridge(self._mux.bus, data_width=32)
        # ----------------------------------------------------------------------
        # IO
        self.wbport         = self._bridge.wb_bus
        self.interrupts     = Signal(ninterrupts)
        self.core_interrupt = Signal(ncores)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        m.submodules.mux    = self._mux
        m.submodules.bridge = self._bridge

        # ------------------------------------------------------------
        # create the sources, and create the maps
        interrurp_src = [[Source(trigger='level', name=f'intsrc{i}{j}') for j in range(self._ninterrupts)] for i in range(self._ncores)]
        event_maps    = [EventMap() for n in range(self._ncores)]

        for intsrc, eventmap in zip(interrurp_src, event_maps):
            for src in intsrc:
                eventmap.add(src)

        # ------------------------------------------------------------
        # create the monitors
        monitors = [Monitor(event_map=eventmap, trigger='level') for eventmap in event_maps]
        m.submodules += monitors

        # ------------------------------------------------------------
        # create the encoders
        prioenc = [PriorityEncoder(self._ninterrupts) for _ in range(self._ncores)]
        m.submodules += prioenc

        # ------------------------------------------------------------
        # connect the interrupts (IO)
        for intsrc in interrurp_src:
            for idx, src in enumerate(intsrc):
                m.d.comb += src.i.eq(self.interrupts[idx])

        m.d.comb += self.core_interrupt.eq(Cat([monitor.src.i for monitor in monitors]))

        # ------------------------------------------------------------
        # connect the monitor to encoder
        for encoder, monitor in zip(prioenc, monitors):
            m.d.sync += encoder.i.eq(monitor.pending & monitor.enable)

        # ------------------------------------------------------------
        # Bus: read
        for pending, enable, src_id, clear, monitor, encoder in zip(self._pending, self._enable, self._source_id, self._clear, monitors, prioenc):
            m.d.comb += [
                pending.r_data.eq(monitor.pending),
                enable.r_data.eq(monitor.enable),
                clear.r_data.eq(monitor.clear),
                src_id.r_data.eq(encoder.o)
            ]
        # ------------------------------------------------------------
        # Bus: write
        for enable, clear, monitor in zip(self._enable, self._clear, monitors):
            with m.If(enable.w_stb):
                m.d.sync += monitor.enable.eq(enable.w_data)
            with m.If(clear.w_stb):
                m.d.comb += monitor.clear.eq(clear.w_data)

        return m
