from amaranth import Module
from amaranth import Record
from amaranth import Elaboratable
from amaranth.build import Platform
from altair.gateware.debug.layout import JTAGReg
from altair.gateware.debug.layout import dmi_layout
from altair.gateware.debug.layout import dtmcs_layout
from altair.gateware.debug.layout import DmiOp
from altair.gateware.debug.layout import dmi_bus_layout
from altair.gateware.debug.jtag import JTAGTap

jtag_regs = {
    JTAGReg.IDCODE: [('value', 32)],
    JTAGReg.DTMCS:  dtmcs_layout,
    JTAGReg.DMI:    dmi_layout
}


class DTM(Elaboratable):
    def __init__(self, idcode=0xDEADC0DE) -> None:
        self.idcode = idcode
        self.dtmcs  = 0x71  # abits = 7, version = 0.13
        # modules
        self.tap = JTAGTap(regmap=jtag_regs)
        # ports
        self.port = Record.like(self.tap.port)
        self.dmi  = Record(dmi_bus_layout)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        m.submodules.jtag = self.tap
        # Default values for JTAG registers
        m.d.comb += [
            self.tap.regs[JTAGReg.IDCODE].read.eq(self.idcode),
            self.tap.regs[JTAGReg.DTMCS].read.eq(self.dtmcs)
        ]
        # Connect the JTAG port
        m.d.comb += self.tap.port.connect(self.port)
        # DMI bus
        dmireg = self.tap.regs[JTAGReg.DMI]

        with m.FSM():
            with m.State('IDLE'):
                m.d.sync += [
                    self.dmi.addr.eq(dmireg.write.addr),
                    self.dmi.data_w.eq(dmireg.write.data),
                    self.dmi.wen.eq(dmireg.write.op == DmiOp.WRITE),
                ]
                with m.If(dmireg.update & (dmireg.write.op != DmiOp.NOP)):
                    # start transaction: read/write
                    m.d.sync += [
                        self.dmi.valid.eq(1),
                        dmireg.read.op.eq(DmiOp.BUSY)
                    ]
                    m.next = 'BUSY'
            with m.State('BUSY'):
                m.d.sync += [
                    dmireg.read.data.eq(self.dmi.data_r),
                    dmireg.read.op.eq(DmiOp.BUSY)
                ]
                with m.If(self.dmi.ack):
                    m.d.sync += dmireg.read.op.eq(DmiOp.OK)
                with m.If(self.dmi.err):
                    m.d.sync += dmireg.read.op.eq(DmiOp.FAIL)
                with m.If(self.dmi.ack | self.dmi.err):
                    m.d.sync += self.dmi.valid.eq(0)
                    m.next = 'IDLE'

        return m
