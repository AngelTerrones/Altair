from nmigen import Cat
from nmigen import Signal
from nmigen import Module
from nmigen import Memory
from nmigen import Elaboratable
from nmigen.build import Platform
from nmigen_soc.wishbone.bus import Interface
from typing import List
from altair.gateware.isa import Funct3
from altair.gateware.isa import ExceptionCause
from altair.gateware.csr import CSRFile
from altair.gateware.lsu import LoadStoreUnit
from altair.gateware.decoder import DecoderUnit
from altair.gateware.exception import ExceptionUnit
from altair.gateware.divider import Divider
from altair.gateware.multiplier import Multiplier


class Altair(Elaboratable):
    def __init__(self,
                 # Core
                 core_reset_address: int = 0x8000_0000,
                 # ISA
                 isa_enable_rv32m: bool = False,
                 isa_enable_extra_csr: bool = False,
                 isa_enable_user_mode: bool = False
                 ) -> None:
        # ----------------------------------------------------------------------
        # configuration
        self.reset_address     = core_reset_address
        self.enable_rv32m      = isa_enable_rv32m
        self.enable_extra_csr  = isa_enable_extra_csr
        self.enable_user_mode  = isa_enable_user_mode
        # dicts
        self.exception_unit_kw = dict(enable_rv32m=self.enable_rv32m,
                                      enable_extra_csr=self.enable_extra_csr,
                                      enable_user_mode=self.enable_user_mode,
                                      core_reset_address=self.reset_address)
        # IO
        self.mport = Interface(addr_width=32, data_width=32, granularity=8, features=['err'], name='mport')
        self.external_interrupt = Signal()  # input
        self.timer_interrupt    = Signal()  # input
        self.software_interrupt = Signal()  # input

    def port_list(self) -> List:
        mport = [getattr(self.mport, name) for name, _, _ in self.mport.layout]

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
        # Units
        lsu        = m.submodules.lsu       = LoadStoreUnit()
        decoder    = m.submodules.decoder   = DecoderUnit(self.enable_rv32m)
        csr        = m.submodules.csr       = CSRFile()
        exceptunit = m.submodules.exception = ExceptionUnit(csr, **self.exception_unit_kw)
        # Register file
        gprf     = Memory(width=32, depth=32)
        gprf_rp1 = gprf.read_port(transparent=False)
        gprf_rp2 = gprf.read_port(transparent=False)
        gprf_wp  = gprf.write_port()
        m.submodules += gprf_rp1, gprf_rp2, gprf_wp

        if self.enable_rv32m:
            multiplier = m.submodules.multiplier = Multiplier()
            divider    = m.submodules.divider    = Divider()

            m.d.comb += [
                multiplier.op.eq(decoder.funct3),
                multiplier.dat1.eq(gprf_rp1.data),
                multiplier.dat2.eq(gprf_rp2.data),
                multiplier.valid.eq(multdiv & decoder.is_mul),
                mult_result.eq(multiplier.result),
                mult_ack.eq(multiplier.ready),

                divider.op.eq(decoder.funct3),
                divider.dat1.eq(gprf_rp1.data),
                divider.dat2.eq(gprf_rp2.data),
                divider.valid.eq(multdiv & decoder.is_div),
                div_result.eq(divider.result),
                div_ack.eq(divider.ready)
            ]
        else:
            m.d.comb += [
                mult_result.eq(0xdead0000),
                div_result.eq(0x0000beef),
                mult_ack.eq(0),
                div_ack.eq(0)
            ]

        # Port
        m.d.comb += lsu.mport.connect(self.mport)

        # ALU A
        with m.If(decoder.inst_lui):
            m.d.comb += alu_a.eq(0)
        with m.Elif(decoder.inst_auipc | decoder.inst_jal | decoder.is_b):
            m.d.comb += alu_a.eq(pc)
        with m.Else():
            m.d.comb += alu_a.eq(gprf_rp1.data)

        # ALU B
        with m.If(decoder.inst_lui | decoder.inst_auipc | decoder.is_j | decoder.is_b | decoder.is_ld | decoder.is_st | decoder.is_imm):
            m.d.comb += alu_b.eq(decoder.immediate)
        with m.Elif(decoder.inst_sub):
            m.d.comb += alu_b.eq(~gprf_rp2.data)
        with m.Else():
            m.d.comb += alu_b.eq(gprf_rp2.data)

        # CMP
        with m.If(decoder.inst_slti | decoder.inst_sltiu):
            m.d.comb += cmp_b.eq(decoder.immediate)
        with m.Else():
            m.d.comb += cmp_b.eq(gprf_rp2.data)

        # ALU
        m.d.sync += add_out.eq(alu_a + alu_b + decoder.inst_sub)

        # logic
        with m.If(decoder.inst_and | decoder.inst_andi):
            m.d.sync += logic_out.eq(alu_a & alu_b)
        with m.Elif(decoder.inst_or | decoder.inst_ori):
            m.d.sync += logic_out.eq(alu_a | alu_b)
        with m.Else():
            m.d.sync += logic_out.eq(alu_a ^ alu_b)

        # compare
        m.d.sync += [
            is_eq.eq(gprf_rp1.data == cmp_b),
            is_lt.eq(gprf_rp1.data.as_signed() < cmp_b.as_signed()),
            is_ltu.eq(gprf_rp1.data < cmp_b)
        ]
        m.d.comb += ltx_cmp_out.eq((is_lt & (decoder.inst_slt | decoder.inst_slti)) |
                                   (is_ltu & (decoder.inst_sltu | decoder.inst_sltiu)))

        # shift
        with m.If(decoder.inst_sll | decoder.inst_slli):
            m.d.sync += shift_out.eq(alu_a << alu_b[0:5])
        with m.Elif(decoder.inst_srl | decoder.inst_srli):
            m.d.sync += shift_out.eq(alu_a >> alu_b[0:5])
        with m.Else():
            m.d.sync += shift_out.eq(alu_a.as_signed() >> alu_b[0:5])

        # JMP/Branch
        beq  = is_eq & decoder.inst_beq
        bne  = ~is_eq & decoder.inst_bne
        blt  = is_lt & decoder.inst_blt
        bge  = ~is_lt & decoder.inst_bge
        bltu = is_ltu & decoder.inst_bltu
        bgeu = ~is_ltu & decoder.inst_bgeu
        m.d.comb += [
            b_taken.eq(beq | bne | blt | bge | bltu | bgeu),
            jb_error.eq((decoder.is_j | b_taken) & add_out[1])  # check for misalignment
        ]

        # CSR port
        m.d.comb += csr.privmode.eq(exceptunit.m_privmode)

        with m.If(decoder.funct3[2]):
            m.d.sync += csr_src.eq(decoder.gpr_rs1_q)
        with m.Else():
            m.d.sync += csr_src.eq(gprf_rp1.data)

        with m.If(decoder.funct3[:2] == 0b01):  # write
            m.d.comb += csr_wdata.eq(csr_src)
        with m.Elif(decoder.funct3[:2] == 0b10):  # set
            m.d.comb += csr_wdata.eq(csr.port.dat_r | csr_src)
        with m.Else():  # clear
            m.d.comb += csr_wdata.eq(csr.port.dat_r & ~csr_src)

        # Default: do not read the RF
        m.d.comb += [
            gprf_rp1.en.eq(0),
            gprf_rp2.en.eq(0)
        ]

        # Decoder
        m.d.comb += decoder.privmode.eq(exceptunit.m_privmode)

        # Interrupts
        m.d.comb += [
            exceptunit.external_interrupt.eq(self.external_interrupt),
            exceptunit.software_interrupt.eq(self.software_interrupt),
            exceptunit.timer_interrupt.eq(self.timer_interrupt)
        ]
        m.d.comb += exceptunit.m_pc.eq(pc)
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
                    lsu.address.eq(pc),
                    lsu.store_data.eq(0xdead_c0de),
                    lsu.load.eq(1),
                    lsu.store.eq(0),
                    lsu.op.eq(Funct3.W)
                ]
                # pre-decoding
                m.d.comb += [
                    decoder.instruction_f.eq(lsu.load_data),  # start decoding
                    decoder.enable.eq(lsu.ready),
                    gprf_rp1.addr.eq(decoder.gpr_rs1),
                    gprf_rp1.en.eq(1),
                    gprf_rp2.addr.eq(decoder.gpr_rs2),
                    gprf_rp2.en.eq(1)
                ]

                m.d.sync += instruction.eq(lsu.load_data)  # latch the instruction

                with m.If(lsu.ready):
                    m.next = 'EXECUTE'
                with m.Elif(lsu.error | lsu.misaligned):
                    m.d.sync += [
                        exceptunit.enable.eq(1),
                        exceptunit.edata.eq(pc),
                        exceptunit.ecode.eq(ExceptionCause.E_INST_ADDR_MISALIGNED),
                        exceptunit.m_exception.eq(1)
                    ]
                    with m.If(lsu.error):
                        m.d.sync += exceptunit.ecode.eq(ExceptionCause.E_INST_ACCESS_FAULT)

                    m.next = 'TRAP'
            with m.State('EXECUTE'):
                m.d.comb += debug_state.eq(self.str2value('EXECUTE'))

                with m.If(exceptunit.m_interrupt):
                    m.d.sync += [
                        exceptunit.enable.eq(1),
                        exceptunit.edata.eq(instruction)
                    ]
                    m.next = 'TRAP'
                with m.Else():
                    with m.If(decoder.is_shift | decoder.use_alu):
                        m.next = 'COMMIT'
                    with m.Elif(decoder.is_mul | decoder.is_div):
                        m.d.comb += multdiv.eq(1)
                        with m.If(mult_ack | div_ack):
                            m.next = 'COMMIT'
                    with m.Elif(decoder.inst_fence | decoder.inst_fencei):
                        m.d.sync += pc.eq(pc4)
                        m.next = 'FETCH'
                    with m.Elif(decoder.inst_wfi):
                        m.d.sync += pc.eq(pc4)
                        m.next = 'FETCH'
                    with m.Elif(decoder.is_ld | decoder.is_st):
                        m.next = 'MEMLS'
                    with m.Elif(decoder.is_csr):
                        m.next = 'CSR'
                    with m.Else():
                        m.d.sync += [
                            exceptunit.enable.eq(1),
                            exceptunit.edata.eq(instruction),
                            exceptunit.ecode.eq(ExceptionCause.E_ILLEGAL_INST),
                            exceptunit.m_exception.eq(1)
                        ]
                        with m.If(decoder.inst_xcall):
                            m.d.sync += exceptunit.ecode.eq(ExceptionCause.E_ECALL_FROM_M)  # check priviledge mode...
                        with m.Elif(decoder.inst_xbreak):
                            m.d.sync += [
                                exceptunit.edata.eq(pc),
                                exceptunit.ecode.eq(ExceptionCause.E_BREAKPOINT)
                            ]

                        m.next = 'TRAP'
            with m.State('MEMLS'):
                m.d.comb += debug_state.eq(self.str2value('MEMLS'))

                # connect LSU
                m.d.comb += [
                    lsu.address.eq(add_out),
                    lsu.store_data.eq(gprf_rp2.data),
                    lsu.load.eq(decoder.is_ld),
                    lsu.store.eq(decoder.is_st),
                    lsu.op.eq(decoder.funct3)
                ]

                with m.If(lsu.ready):
                    m.d.sync += ld_out.eq(lsu.load_data)

                    m.next = 'COMMIT'
                with m.Elif(lsu.error | lsu.misaligned):
                    m.d.sync += [
                        exceptunit.enable.eq(1),
                        exceptunit.edata.eq(add_out),
                        exceptunit.m_exception.eq(1)
                    ]
                    with m.If(decoder.is_ld & lsu.error):
                        m.d.sync += exceptunit.ecode.eq(ExceptionCause.E_LOAD_ACCESS_FAULT)
                    with m.If(decoder.is_ld & lsu.misaligned):
                        m.d.sync += exceptunit.ecode.eq(ExceptionCause.E_LOAD_ADDR_MISALIGNED)
                    with m.If(decoder.is_st & lsu.error):
                        m.d.sync += exceptunit.ecode.eq(ExceptionCause.E_STORE_AMO_ACCESS_FAULT)
                    with m.If(decoder.is_st & lsu.misaligned):
                        m.d.sync += exceptunit.ecode.eq(ExceptionCause.E_STORE_AMO_ADDR_MISALIGNED)

                    m.next = 'TRAP'
            with m.State('CSR'):
                m.d.comb += debug_state.eq(self.str2value('CSR'))
                # CSR

                m.d.comb += [
                    csr.port.addr.eq(decoder.csr_addr),
                    csr.port.dat_w.eq(csr_wdata),
                    csr.port.we.eq(decoder.csr_we),
                    csr.port.valid.eq(1)
                ]
                with m.If(csr.port.ready):
                    m.d.sync += csr_out.eq(csr.port.dat_r)

                    m.next = 'COMMIT'
                    with m.If(csr.invalid & decoder.is_csr):
                        m.d.sync += [
                            exceptunit.enable.eq(1),
                            exceptunit.edata.eq(instruction),
                            exceptunit.ecode.eq(ExceptionCause.E_ILLEGAL_INST),
                            exceptunit.m_exception.eq(1)
                        ]

                        m.next = 'TRAP'
            with m.State('COMMIT'):
                m.d.comb += debug_state.eq(self.str2value('COMMIT'))

                with m.If(decoder.is_j | b_taken):
                    with m.If(~jb_error):
                        m.d.sync += pc.eq(Cat(0, add_out[1:]))
                with m.Else():
                    m.d.sync += pc.eq(pc4)

                with m.If(decoder.gpr_rd.any()):
                    m.d.comb += [
                        gprf_wp.addr.eq(decoder.gpr_rd),
                        gprf_wp.en.eq(decoder.is_j | decoder.is_ld | decoder.is_csr | decoder.is_logic |
                                      decoder.is_cmp | decoder.is_shift | decoder.is_add | decoder.is_mul |
                                      decoder.is_div)
                    ]

                # BFMux
                with m.If(decoder.is_j):
                    m.d.comb += gprf_wp.data.eq(pc4)
                with m.Elif(decoder.is_ld):
                    m.d.comb += gprf_wp.data.eq(ld_out)
                with m.Elif(decoder.is_csr):
                    m.d.comb += gprf_wp.data.eq(csr_out)
                with m.Elif(decoder.is_logic):
                    m.d.comb += gprf_wp.data.eq(logic_out)
                with m.Elif(decoder.is_cmp):
                    m.d.comb += gprf_wp.data.eq(ltx_cmp_out)
                with m.Elif(decoder.is_shift):
                    m.d.comb += gprf_wp.data.eq(shift_out)
                with m.Elif(decoder.is_mul):
                    m.d.comb += gprf_wp.data.eq(mult_result)
                with m.Elif(decoder.is_div):
                    m.d.comb += gprf_wp.data.eq(div_result)
                with m.Else():
                    m.d.comb += gprf_wp.data.eq(add_out)

                m.next = 'FETCH'
                with m.If(jb_error):
                    m.d.comb += gprf_wp.en.eq(0)
                    m.d.sync += [
                        exceptunit.enable.eq(1),
                        exceptunit.edata.eq(Cat(0, add_out[1:])),
                        exceptunit.ecode.eq(ExceptionCause.E_INST_ADDR_MISALIGNED),
                        exceptunit.m_exception.eq(1)
                    ]

                    m.next = 'TRAP'
            with m.State('TRAP'):
                m.d.comb += debug_state.eq(self.str2value('TRAP'))

                with m.If(decoder.inst_mret):
                    m.d.sync += pc.eq(exceptunit.mepc)
                with m.Else():
                    m.d.sync += pc.eq(exceptunit.mtvec)

                m.d.sync += [
                    exceptunit.enable.eq(0),
                    exceptunit.m_mret.eq(0),
                    exceptunit.m_exception.eq(0)
                ]

                m.next = 'FETCH'
        # ----------------------------------------------------------------------
        # New PC
        m.d.comb += pc4.eq(pc + 4)

        return m
