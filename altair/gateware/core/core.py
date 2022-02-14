from amaranth import Cat
from amaranth import Mux
from amaranth import Signal
from amaranth import Module
from amaranth import Memory
from amaranth import Elaboratable
from amaranth.build import Platform
from amaranth_soc.wishbone.bus import Interface
from typing import List
from altair.gateware.core.isa import Funct3
from altair.gateware.core.isa import ExceptionCause
from altair.gateware.core.csr import CSRFile
from altair.gateware.core.lsu import LoadStoreUnit
from altair.gateware.core.decoder import DecoderUnit
from altair.gateware.core.exception import ExceptionUnit
from altair.gateware.core.divider import Divider
from altair.gateware.core.multiplier import Multiplier
from altair.gateware.debug import TriggerModule


class Core(Elaboratable):
    def __init__(self,
                 # Reset
                 reset_address: int = 0x8000_0000,
                 # ISA
                 enable_rv32m: bool = False,
                 enable_rv32a: bool = False,
                 enable_extra_csr: bool = False,
                 enable_user_mode: bool = False,
                 # Trigger
                 enable_triggers: bool = False,
                 ntriggers: int = 4,
                 # Debug
                 debug_enable: bool = False,
                 # Identification
                 hartid: int = 0
                 ) -> None:
        # ----------------------------------------------------------------------
        # configuration
        self.reset_address     = reset_address
        self.enable_rv32m      = enable_rv32m
        self.enable_rv32a      = enable_rv32a
        self.enable_extra_csr  = enable_extra_csr
        self.enable_user_mode  = enable_user_mode
        self.enable_trigger    = enable_triggers
        self.trigger_ntriggers = ntriggers
        self.debug_enable      = debug_enable
        features = ['err', 'lock'] if enable_rv32a else ['err']
        # Instantiate units
        self._lsu        = LoadStoreUnit(features=features)
        self._decoder    = DecoderUnit(self.enable_rv32m, self.enable_rv32a)
        self._csr        = CSRFile()
        self._exceptunit = ExceptionUnit(csrf=self._csr,
                                         hartid=hartid,
                                         enable_rv32m=self.enable_rv32m,
                                         enable_extra_csr=self.enable_extra_csr,
                                         enable_user_mode=self.enable_user_mode,
                                         reset_address=self.reset_address)
        gprf           = Memory(width=32, depth=32)
        self._gprf_rp1 = gprf.read_port(transparent=False)
        self._gprf_rp2 = gprf.read_port(transparent=False)
        self._gprf_wp  = gprf.write_port()
        if self.enable_rv32m:
            self._multiplier = Multiplier()
            self._divider    = Divider()
        if self.enable_trigger:
            self._trigger = TriggerModule(privmode=self._exceptunit.m_privmode,
                                          ntriggers=self.trigger_ntriggers,
                                          csrf=self._csr,
                                          enable_user_mode=self.enable_user_mode)
        # IO
        self.wbport             = Interface(addr_width=30, data_width=32, granularity=8, features=features, name='wbport')
        self.external_interrupt = Signal()  # input
        self.timer_interrupt    = Signal()  # input
        self.software_interrupt = Signal()  # input

    def port_list(self) -> List:
        mport = [getattr(self.wbport, name) for name, _, _ in self.wbport.layout]

        return [
            *mport,
            self.external_interrupt,
            self.timer_interrupt,
            self.software_interrupt
        ]

    def str2value(self, string: str):
        val = 0
        for idx, x in enumerate(string[::-1]):
            val += ord(x) << (idx << 3)

        return val

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        # ----------------------------------------------------------------------
        # signals
        debug_state = Signal(8 * 10)
        pc          = Signal(32, reset=self.reset_address)
        pc4         = Signal(32)
        b_taken     = Signal()
        mult_result = Signal(32)
        mult_ack    = Signal()
        div_result  = Signal(32)
        div_ack     = Signal()
        instruction = Signal(32)
        alu_a       = Signal(32)
        alu_b       = Signal(32)
        cmp_b       = Signal(32)
        add_out     = Signal(32)
        logic_out   = Signal(32)
        shift_out   = Signal(32)
        csr_out     = Signal(32)
        ld_out      = Signal(32)
        is_eq       = Signal()
        is_lt       = Signal()
        is_ltu      = Signal()
        ltx_cmp_out = Signal()
        jb_error    = Signal()
        multdiv     = Signal()
        csr_src     = Signal(32)
        csr_wdata   = Signal(32)
        # ----------------------------------------------------------------------
        # Register units
        m.submodules.lsu       = self._lsu
        m.submodules.decoder   = self._decoder
        m.submodules.csr       = self._csr
        m.submodules.exception = self._exceptunit
        m.submodules += self._gprf_rp1, self._gprf_rp2, self._gprf_wp
        # optional units: register and connect
        if self.enable_rv32m:
            m.submodules.multiplier = self._multiplier
            m.submodules.divider    = self._divider
            m.d.comb += [
                self._multiplier.op.eq(self._decoder.funct3),
                self._multiplier.dat1.eq(self._gprf_rp1.data),
                self._multiplier.dat2.eq(self._gprf_rp2.data),
                self._multiplier.valid.eq(multdiv & self._decoder.is_mul),
                mult_result.eq(self._multiplier.result),
                mult_ack.eq(self._multiplier.ready),

                self._divider.op.eq(self._decoder.funct3),
                self._divider.dat1.eq(self._gprf_rp1.data),
                self._divider.dat2.eq(self._gprf_rp2.data),
                self._divider.valid.eq(multdiv & self._decoder.is_div),
                div_result.eq(self._divider.result),
                div_ack.eq(self._divider.ready)
            ]
        else:
            m.d.comb += [
                mult_result.eq(0xdead0000),
                div_result.eq(0x0000beef),
                mult_ack.eq(0),
                div_ack.eq(0)
            ]

        if self.enable_trigger:
            m.submodules.trigger = self._trigger
            m.d.comb += [
                self._trigger.x_pc.eq(pc),
                self._trigger.x_bus_addr.eq(add_out)
            ]

        # Memory port
        m.d.comb += self._lsu.mport.connect(self.wbport)

        # ALU A
        with m.If(self._decoder.inst_lui):
            m.d.comb += alu_a.eq(0)
        with m.Elif(self._decoder.inst_auipc | self._decoder.inst_jal | self._decoder.is_b):
            m.d.comb += alu_a.eq(pc)
        with m.Else():
            m.d.comb += alu_a.eq(self._gprf_rp1.data)

        # ALU B
        with m.If(self._decoder.inst_lui | self._decoder.inst_auipc | self._decoder.is_j | self._decoder.is_b | self._decoder.is_ld | self._decoder.is_st | self._decoder.is_imm):
            m.d.comb += alu_b.eq(self._decoder.immediate)
        with m.Elif(self._decoder.inst_sub):
            m.d.comb += alu_b.eq(~self._gprf_rp2.data)
        if self.enable_rv32a:
            with m.Elif(self._decoder.is_amo | self._decoder.is_lrsc):
                m.d.comb += alu_b.eq(0)
        with m.Else():
            m.d.comb += alu_b.eq(self._gprf_rp2.data)

        # CMP
        with m.If(self._decoder.inst_slti | self._decoder.inst_sltiu):
            m.d.comb += cmp_b.eq(self._decoder.immediate)
        with m.Else():
            m.d.comb += cmp_b.eq(self._gprf_rp2.data)

        # ALU
        m.d.sync += add_out.eq(alu_a + alu_b + self._decoder.inst_sub)

        # logic
        with m.If(self._decoder.inst_and | self._decoder.inst_andi):
            m.d.sync += logic_out.eq(alu_a & alu_b)
        with m.Elif(self._decoder.inst_or | self._decoder.inst_ori):
            m.d.sync += logic_out.eq(alu_a | alu_b)
        with m.Else():
            m.d.sync += logic_out.eq(alu_a ^ alu_b)

        # compare
        m.d.sync += [
            is_eq.eq(self._gprf_rp1.data == cmp_b),
            is_lt.eq(self._gprf_rp1.data.as_signed() < cmp_b.as_signed()),
            is_ltu.eq(self._gprf_rp1.data < cmp_b)
        ]
        m.d.comb += ltx_cmp_out.eq((is_lt & (self._decoder.inst_slt | self._decoder.inst_slti)) |
                                   (is_ltu & (self._decoder.inst_sltu | self._decoder.inst_sltiu)))

        # shift
        with m.If(self._decoder.inst_sll | self._decoder.inst_slli):
            m.d.sync += shift_out.eq(alu_a << alu_b[0:5])
        with m.Elif(self._decoder.inst_srl | self._decoder.inst_srli):
            m.d.sync += shift_out.eq(alu_a >> alu_b[0:5])
        with m.Else():
            m.d.sync += shift_out.eq(alu_a.as_signed() >> alu_b[0:5])

        # JMP/Branch
        beq  = is_eq & self._decoder.inst_beq
        bne  = ~is_eq & self._decoder.inst_bne
        blt  = is_lt & self._decoder.inst_blt
        bge  = ~is_lt & self._decoder.inst_bge
        bltu = is_ltu & self._decoder.inst_bltu
        bgeu = ~is_ltu & self._decoder.inst_bgeu
        m.d.comb += [
            b_taken.eq(beq | bne | blt | bge | bltu | bgeu),
            jb_error.eq((self._decoder.is_j | b_taken) & add_out[1])  # check for misalignment
        ]

        # CSR port
        m.d.comb += self._csr.privmode.eq(self._exceptunit.m_privmode)

        with m.If(self._decoder.funct3[2]):
            m.d.sync += csr_src.eq(self._decoder.gpr_rs1_q)
        with m.Else():
            m.d.sync += csr_src.eq(self._gprf_rp1.data)

        with m.If(self._decoder.funct3[:2] == 0b01):  # write
            m.d.comb += csr_wdata.eq(csr_src)
        with m.Elif(self._decoder.funct3[:2] == 0b10):  # set
            m.d.comb += csr_wdata.eq(self._csr.port.dat_r | csr_src)
        with m.Else():  # clear
            m.d.comb += csr_wdata.eq(self._csr.port.dat_r & ~csr_src)

        # Default: do not read the RF
        m.d.comb += [
            self._gprf_rp1.en.eq(0),
            self._gprf_rp2.en.eq(0)
        ]

        # Decoder
        m.d.comb += self._decoder.privmode.eq(self._exceptunit.m_privmode)

        # Interrupts
        m.d.comb += [
            self._exceptunit.external_interrupt.eq(self.external_interrupt),
            self._exceptunit.software_interrupt.eq(self.software_interrupt),
            self._exceptunit.timer_interrupt.eq(self.timer_interrupt)
        ]
        m.d.comb += self._exceptunit.m_pc.eq(pc)

        # Atomic Memory Operations
        if self.enable_rv32a:
            amo_rdata  = Signal(32)
            amo_wdata  = Signal(32)
            amo_strobe = Signal()
            amo_done   = Signal()
            amo_write  = Signal()

            with m.FSM(name='amo'):
                with m.State('load'):
                    m.d.comb += amo_strobe.eq(1)
                    with m.If(self._lsu.ready & self._decoder.is_amo):
                        m.d.sync += amo_rdata.eq(self._lsu.load_data)
                        m.next = 'modify'
                with m.State('modify'):
                    m.d.comb += amo_strobe.eq(0)

                    with m.If(self._decoder.inst_amoadd):
                        m.d.sync += amo_wdata.eq(amo_rdata + self._gprf_rp2.data)
                    with m.Elif(self._decoder.inst_amoand):
                        m.d.sync += amo_wdata.eq(amo_rdata & self._gprf_rp2.data)
                    with m.Elif(self._decoder.inst_amomax):
                        m.d.sync += amo_wdata.eq(Mux(amo_rdata.as_signed() > self._gprf_rp2.data.as_signed(), amo_rdata, self._gprf_rp2.data))
                    with m.Elif(self._decoder.inst_amomaxu):
                        m.d.sync += amo_wdata.eq(Mux(amo_rdata > self._gprf_rp2.data, amo_rdata, self._gprf_rp2.data))
                    with m.Elif(self._decoder.inst_amomin):
                        m.d.sync += amo_wdata.eq(Mux(amo_rdata.as_signed() > self._gprf_rp2.data.as_signed(), self._gprf_rp2.data, amo_rdata))
                    with m.Elif(self._decoder.inst_amominu):
                        m.d.sync += amo_wdata.eq(Mux(amo_rdata > self._gprf_rp2.data, self._gprf_rp2.data, amo_rdata))
                    with m.Elif(self._decoder.inst_amoswap):
                        m.d.sync += amo_wdata.eq(self._gprf_rp2.data)
                    with m.Elif(self._decoder.inst_amoxor):
                        m.d.sync += amo_wdata.eq(amo_rdata ^ self._gprf_rp2.data)
                    with m.Elif(self._decoder.inst_amoor):
                        m.d.sync += amo_wdata.eq(amo_rdata | self._gprf_rp2.data)

                    m.next = 'store'
                with m.State('store'):
                    m.d.comb += [
                        amo_strobe.eq(1),
                        amo_write.eq(1)
                    ]
                    with m.If(self._lsu.ready):
                        m.d.comb += amo_done.eq(1)
                        m.next = 'load'
                    with m.Elif(self._lsu.error):
                        m.next = 'load'
        # ----------------------------------------------------------------------
        # Main FSM
        with m.FSM(name='main'):
            with m.State('RESET'):
                m.d.comb += debug_state.eq(self.str2value('RESET'))

                m.next = 'FETCH'
            with m.State('FETCH'):
                m.d.comb += debug_state.eq(self.str2value('FETCH'))

                # connect LSU
                m.d.comb += [
                    self._lsu.address.eq(pc),
                    self._lsu.store_data.eq(0xdead_c0de),
                    self._lsu.write.eq(0),
                    self._lsu.cycle.eq(1),
                    self._lsu.strobe.eq(1),
                    self._lsu.op.eq(Funct3.W)
                ]
                # pre-decoding
                m.d.comb += [
                    self._decoder.instruction_f.eq(self._lsu.load_data),  # start decoding
                    self._decoder.enable.eq(self._lsu.ready),
                    self._gprf_rp1.addr.eq(self._decoder.gpr_rs1),
                    self._gprf_rp1.en.eq(1),
                    self._gprf_rp2.addr.eq(self._decoder.gpr_rs2),
                    self._gprf_rp2.en.eq(1)
                ]

                m.d.sync += instruction.eq(self._lsu.load_data)  # latch the instruction

                with m.If(self._lsu.ready):
                    m.next = 'EXECUTE'
                with m.Elif(self._lsu.error | self._lsu.misaligned):
                    m.d.sync += [
                        self._exceptunit.enable.eq(1),
                        self._exceptunit.edata.eq(pc),
                        self._exceptunit.ecode.eq(ExceptionCause.E_INST_ADDR_MISALIGNED),
                        self._exceptunit.m_exception.eq(1)
                    ]
                    with m.If(self._lsu.error):
                        m.d.sync += self._exceptunit.ecode.eq(ExceptionCause.E_INST_ACCESS_FAULT)

                    m.next = 'TRAP'
            with m.State('EXECUTE'):
                m.d.comb += debug_state.eq(self.str2value('EXECUTE'))
                if self.enable_trigger:
                    m.d.comb += self._trigger.x_valid.eq(1)

                with m.If(self._exceptunit.m_interrupt):
                    m.d.sync += [
                        self._exceptunit.enable.eq(1),
                        self._exceptunit.edata.eq(instruction)
                    ]
                    m.next = 'TRAP'
                if self.enable_trigger:
                    with m.Elif(self._trigger.trap):
                        m.d.sync += [
                            self._exceptunit.enable.eq(1),
                            self._exceptunit.edata.eq(pc),
                            self._exceptunit.ecode.eq(ExceptionCause.E_BREAKPOINT),
                            self._exceptunit.m_exception.eq(1)
                        ]
                        m.next = 'TRAP'
                with m.Else():
                    with m.If(self._decoder.is_shift | self._decoder.use_alu):
                        m.next = 'COMMIT'
                    with m.Elif(self._decoder.is_mul | self._decoder.is_div):
                        m.d.comb += multdiv.eq(1)
                        with m.If(mult_ack | div_ack):
                            m.next = 'COMMIT'
                    with m.Elif(self._decoder.inst_fence | self._decoder.inst_fencei | self._decoder.inst_wfi):
                        m.d.sync += pc.eq(pc4)
                        if self.enable_extra_csr:
                            m.d.comb += self._exceptunit.w_retire.eq(1)
                        m.next = 'FETCH'
                    with m.Elif(self._decoder.is_ld | self._decoder.is_st | self._decoder.is_lrsc):
                        m.next = 'MEMLS/LRSC'
                    if self.enable_rv32a:
                        with m.Elif(self._decoder.is_amo):
                            m.next = 'AMO'
                    with m.Elif(self._decoder.is_csr):
                        m.next = 'CSR'
                    with m.Else():
                        m.d.sync += [
                            self._exceptunit.enable.eq(1),
                            self._exceptunit.edata.eq(instruction),
                            self._exceptunit.ecode.eq(ExceptionCause.E_ILLEGAL_INST),
                            self._exceptunit.m_exception.eq(~self._decoder.inst_mret),
                            self._exceptunit.m_mret.eq(self._decoder.inst_mret)
                        ]
                        with m.If(self._decoder.inst_xcall):
                            m.d.sync += self._exceptunit.ecode.eq(ExceptionCause.E_ECALL_FROM_M)  # check priviledge mode...
                        with m.Elif(self._decoder.inst_xbreak):
                            m.d.sync += [
                                self._exceptunit.edata.eq(pc),
                                self._exceptunit.ecode.eq(ExceptionCause.E_BREAKPOINT)
                            ]

                        m.next = 'TRAP'
            with m.State('MEMLS/LRSC'):
                m.d.comb += debug_state.eq(self.str2value('MEMLS/LRSC'))
                is_ld = self._decoder.is_ld | self._decoder.inst_lr
                is_st = self._decoder.is_st | self._decoder.inst_sc

                valid = 1
                if self.enable_trigger:
                    valid = valid & ~self._trigger.trap
                    m.d.comb += [
                        self._trigger.x_valid.eq(1),
                        self._trigger.x_load.eq(is_ld),
                        self._trigger.x_store.eq(is_st),
                    ]

                # connect LSU
                m.d.comb += [
                    self._lsu.address.eq(add_out),
                    self._lsu.store_data.eq(self._gprf_rp2.data),
                    self._lsu.write.eq(is_st),
                    self._lsu.cycle.eq(valid),
                    self._lsu.strobe.eq(valid),
                    self._lsu.op.eq(self._decoder.funct3)
                ]
                if self.enable_rv32a:
                    m.d.comb += self._lsu.lrsc.eq(self._decoder.is_lrsc)
                # Next state and extra logic
                ready = self._lsu.ready
                with m.If(ready):
                    m.d.sync += ld_out.eq(self._lsu.load_data)
                    m.next = 'COMMIT'
                with m.Elif(self._lsu.error | self._lsu.misaligned):
                    m.d.sync += [
                        self._exceptunit.enable.eq(1),
                        self._exceptunit.edata.eq(add_out),
                        self._exceptunit.m_exception.eq(1)
                    ]
                    with m.If(is_ld & self._lsu.error):
                        m.d.sync += self._exceptunit.ecode.eq(ExceptionCause.E_LOAD_ACCESS_FAULT)
                    with m.If(is_ld & self._lsu.misaligned):
                        m.d.sync += self._exceptunit.ecode.eq(ExceptionCause.E_LOAD_ADDR_MISALIGNED)
                    with m.If(is_st & self._lsu.error):
                        m.d.sync += self._exceptunit.ecode.eq(ExceptionCause.E_STORE_AMO_ACCESS_FAULT)
                    with m.If(is_st & self._lsu.misaligned):
                        m.d.sync += self._exceptunit.ecode.eq(ExceptionCause.E_STORE_AMO_ADDR_MISALIGNED)

                    m.next = 'TRAP'
                if self.enable_trigger:
                    with m.If(self._trigger.trap):
                        m.d.sync += [
                            self._exceptunit.enable.eq(1),
                            self._exceptunit.edata.eq(pc),
                            self._exceptunit.ecode.eq(ExceptionCause.E_BREAKPOINT),
                            self._exceptunit.m_exception.eq(1)
                        ]
                        m.next = 'TRAP'
            if self.enable_rv32a:
                with m.State('AMO'):
                    m.d.comb += debug_state.eq(self.str2value('AMO'))

                    # connect LSU
                    m.d.comb += [
                        self._lsu.address.eq(add_out),
                        self._lsu.store_data.eq(amo_wdata),
                        self._lsu.write.eq(amo_write),
                        self._lsu.cycle.eq(1),
                        self._lsu.strobe.eq(amo_strobe),
                        self._lsu.op.eq(self._decoder.funct3)
                    ]
                    with m.If(amo_done):
                        m.d.sync += ld_out.eq(amo_rdata)

                        m.next = 'COMMIT'
                    with m.Elif(self._lsu.error | self._lsu.misaligned):
                        m.d.sync += [
                            self._exceptunit.enable.eq(1),
                            self._exceptunit.edata.eq(add_out),
                            self._exceptunit.m_exception.eq(1)
                        ]
                        with m.If(self._lsu.error):
                            m.d.sync += self._exceptunit.ecode.eq(ExceptionCause.E_STORE_AMO_ACCESS_FAULT)
                        with m.If(self._lsu.misaligned):
                            m.d.sync += self._exceptunit.ecode.eq(ExceptionCause.E_STORE_AMO_ADDR_MISALIGNED)

                        m.next = 'TRAP'
            with m.State('CSR'):
                m.d.comb += debug_state.eq(self.str2value('CSR'))
                # CSR
                m.d.comb += [
                    self._csr.port.addr.eq(self._decoder.csr_addr),
                    self._csr.port.dat_w.eq(csr_wdata),
                    self._csr.port.we.eq(self._decoder.csr_we),
                    self._csr.port.valid.eq(1)
                ]
                with m.If(self._csr.port.ready):
                    m.d.sync += csr_out.eq(self._csr.port.dat_r)

                    m.next = 'COMMIT'
                    with m.If(self._csr.invalid & self._decoder.is_csr):
                        m.d.sync += [
                            self._exceptunit.enable.eq(1),
                            self._exceptunit.edata.eq(instruction),
                            self._exceptunit.ecode.eq(ExceptionCause.E_ILLEGAL_INST),
                            self._exceptunit.m_exception.eq(1)
                        ]

                        m.next = 'TRAP'
            with m.State('COMMIT'):
                m.d.comb += debug_state.eq(self.str2value('COMMIT'))

                with m.If(self._decoder.is_j | b_taken):
                    with m.If(~jb_error):
                        m.d.sync += pc.eq(Cat(0, add_out[1:]))
                with m.Else():
                    m.d.sync += pc.eq(pc4)

                with m.If(self._decoder.gpr_rd.any()):
                    m.d.comb += [
                        self._gprf_wp.addr.eq(self._decoder.gpr_rd),
                        self._gprf_wp.en.eq(self._decoder.is_j | self._decoder.is_ld | self._decoder.is_csr | self._decoder.is_logic |
                                      self._decoder.is_cmp | self._decoder.is_shift | self._decoder.is_add | self._decoder.is_mul |
                                      self._decoder.is_div | self._decoder.is_amo | self._decoder.is_lrsc)
                    ]
                # BFMux
                with m.If(self._decoder.is_j):
                    m.d.comb += self._gprf_wp.data.eq(pc4)
                with m.Elif(self._decoder.is_ld):
                    m.d.comb += self._gprf_wp.data.eq(ld_out)
                with m.Elif(self._decoder.is_csr):
                    m.d.comb += self._gprf_wp.data.eq(csr_out)
                with m.Elif(self._decoder.is_logic):
                    m.d.comb += self._gprf_wp.data.eq(logic_out)
                with m.Elif(self._decoder.is_cmp):
                    m.d.comb += self._gprf_wp.data.eq(ltx_cmp_out)
                with m.Elif(self._decoder.is_shift):
                    m.d.comb += self._gprf_wp.data.eq(shift_out)
                with m.Elif(self._decoder.is_mul):
                    m.d.comb += self._gprf_wp.data.eq(mult_result)
                with m.Elif(self._decoder.is_div):
                    m.d.comb += self._gprf_wp.data.eq(div_result)
                if self.enable_rv32a:
                    with m.Elif(self._decoder.is_amo):
                        m.d.comb += self._gprf_wp.data.eq(amo_rdata)
                    with m.Elif(self._decoder.is_lrsc):
                        m.d.comb += self._gprf_wp.data.eq(ld_out)
                with m.Else():
                    m.d.comb += self._gprf_wp.data.eq(add_out)

                m.next = 'FETCH'
                with m.If(jb_error):
                    m.d.comb += self._gprf_wp.en.eq(0)
                    m.d.sync += [
                        self._exceptunit.enable.eq(1),
                        self._exceptunit.edata.eq(Cat(0, add_out[1:])),
                        self._exceptunit.ecode.eq(ExceptionCause.E_INST_ADDR_MISALIGNED),
                        self._exceptunit.m_exception.eq(1)
                    ]

                    m.next = 'TRAP'
                if self.enable_extra_csr:
                    with m.Else():
                        m.d.comb += self._exceptunit.w_retire.eq(1)
            with m.State('TRAP'):
                m.d.comb += debug_state.eq(self.str2value('TRAP'))

                with m.If(self._decoder.inst_mret):
                    m.d.sync += pc.eq(self._exceptunit.mepc)
                with m.Else():
                    m.d.sync += pc.eq(self._exceptunit.mtvec)

                m.d.sync += [
                    self._exceptunit.enable.eq(0),
                    self._exceptunit.m_mret.eq(0),
                    self._exceptunit.m_exception.eq(0)
                ]
                if self.enable_extra_csr:
                    m.d.comb += self._exceptunit.w_retire.eq(1)
                m.next = 'FETCH'
        # ----------------------------------------------------------------------
        # New PC
        m.d.comb += pc4.eq(pc + 4)

        return m
