from amaranth import Module
from amaranth import Memory
from amaranth import Elaboratable
from amaranth.build import Platform
from amaranth_soc.wishbone import Interface


class ROM(Elaboratable):
    def __init__(self, addr_width: int, rom_img) -> None:
        # addr_width: size need to address words.
        self._rom = Memory(width=32, depth=1 << addr_width, init=rom_img, name='rom_mem')
        # ----------------------------------------------------------------------
        # IO
        self.wbport = Interface(addr_width=addr_width, data_width=32, name='rom')

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        rom_rp = m.submodules.rom_rp = self._rom.read_port(transparent=False)

        m.d.comb += [
            rom_rp.addr.eq(self.wbport.adr),
            rom_rp.en.eq(self.wbport.cyc & self.wbport.stb),
            self.wbport.dat_r.eq(rom_rp.data)
        ]
        m.d.sync += self.wbport.ack.eq(self.wbport.cyc & ~self.wbport.ack)

        return m
