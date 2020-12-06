from enum import IntEnum
from nmigen import Cat
from nmigen import Signal
from nmigen import Module
from nmigen import Elaboratable
from nmigen.build import Platform
from altair.gateware.core.isa import PrivMode
from altair.gateware.core.isa import Opcode
from altair.gateware.core.isa import Funct3
from altair.gateware.core.isa import Funct5
from altair.gateware.core.isa import Funct7
from altair.gateware.core.isa import Funct12


class Type(IntEnum):
    R = 0
    I = 1  # noqa
    S = 2
    B = 3
    U = 4
    J = 5


class DecoderUnit(Elaboratable):
    def __init__(self, enable_rv32m: bool, enable_rv32a: bool) -> None:
        self.enable_rv32m = enable_rv32m
        self.enable_rv32a = enable_rv32a

        self.enable        = Signal()
        self.privmode      = Signal(PrivMode)
        self.instruction_f = Signal(32)
        self.immediate     = Signal(32)
        self.gpr_rs1       = Signal(5)
        self.gpr_rs2       = Signal(5)
        self.gpr_rs1_q     = Signal(5)
        self.gpr_rd        = Signal(5)
        self.inst_lui      = Signal()
        self.inst_auipc    = Signal()
        self.inst_jal      = Signal()
        self.inst_jalr     = Signal()
        self.inst_beq      = Signal()
        self.inst_bne      = Signal()
        self.inst_blt      = Signal()
        self.inst_bge      = Signal()
        self.inst_bltu     = Signal()
        self.inst_bgeu     = Signal()
        self.inst_lb       = Signal()
        self.inst_lh       = Signal()
        self.inst_lw       = Signal()
        self.inst_lbu      = Signal()
        self.inst_lhu      = Signal()
        self.inst_sb       = Signal()
        self.inst_sh       = Signal()
        self.inst_sw       = Signal()
        self.inst_addi     = Signal()
        self.inst_slti     = Signal()
        self.inst_sltiu    = Signal()
        self.inst_xori     = Signal()
        self.inst_ori      = Signal()
        self.inst_andi     = Signal()
        self.inst_slli     = Signal()
        self.inst_srli     = Signal()
        self.inst_srai     = Signal()
        self.inst_add      = Signal()
        self.inst_sub      = Signal()
        self.inst_sll      = Signal()
        self.inst_slt      = Signal()
        self.inst_sltu     = Signal()
        self.inst_xor      = Signal()
        self.inst_srl      = Signal()
        self.inst_sra      = Signal()
        self.inst_or       = Signal()
        self.inst_and      = Signal()
        self.inst_fence    = Signal()
        self.inst_fencei   = Signal()
        self.inst_csrrw    = Signal()
        self.inst_csrrs    = Signal()
        self.inst_csrrc    = Signal()
        self.inst_csrrwi   = Signal()
        self.inst_csrrsi   = Signal()
        self.inst_csrrci   = Signal()
        self.inst_xcall    = Signal()
        self.inst_xbreak   = Signal()
        self.inst_mret     = Signal()
        self.inst_wfi      = Signal()
        self.inst_mul      = Signal()
        self.inst_mulh     = Signal()
        self.inst_mulhsu   = Signal()
        self.inst_mulhu    = Signal()
        self.inst_div      = Signal()
        self.inst_divu     = Signal()
        self.inst_rem      = Signal()
        self.inst_remu     = Signal()
        self.inst_lr       = Signal()
        self.inst_sc       = Signal()
        self.inst_amoswap  = Signal()
        self.inst_amoadd   = Signal()
        self.inst_amoor    = Signal()
        self.inst_amoxor   = Signal()
        self.inst_amoand   = Signal()
        self.inst_amomin   = Signal()
        self.inst_amomax   = Signal()
        self.inst_amominu  = Signal()
        self.inst_amomaxu  = Signal()
        self.is_imm        = Signal()
        self.is_j          = Signal()
        self.is_b          = Signal()
        self.is_ld         = Signal()
        self.is_st         = Signal()
        self.is_csr        = Signal()
        self.is_add        = Signal()
        self.is_logic      = Signal()
        self.is_cmp        = Signal()
        self.is_shift      = Signal()
        self.is_mul        = Signal()
        self.is_div        = Signal()
        self.is_lrsc       = Signal()
        self.is_amo        = Signal()
        self.use_alu       = Signal()
        self.csr_addr      = Signal(12)
        self.csr_we        = Signal()
        self.funct3        = Signal(3)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        opcode      = Signal(Opcode)
        funct3      = Signal(Funct3)
        funct5      = Signal(Funct5)
        funct7      = Signal(Funct7)
        funct12     = Signal(Funct12)
        iimm12      = Signal((12, True))
        simm12      = Signal((12, True))
        bimm12      = Signal((13, True))
        uimm20      = Signal(20)
        jimm20      = Signal((21, True))
        itype       = Signal(Type)
        instruction = self.instruction_f

        # Fields = list of (Opcode, F3, F7, F12)
        def match(op, f3=None, f5=None, f7=None, f12=None):
            op_match  = opcode == op
            f3_match  = funct3 == f3 if f3 is not None else 1
            f5_match  = funct5 == f5 if f5 is not None else 1
            f7_match  = funct7 == f7 if f7 is not None else 1
            f12_match = funct12 == f12 if f12 is not None else 1

            return op_match & f3_match & f5_match & f7_match & f12_match

        with m.Switch(opcode):
            with m.Case(Opcode.LUI):
                m.d.comb += itype.eq(Type.U)
            with m.Case(Opcode.AUIPC):
                m.d.comb += itype.eq(Type.U)
            with m.Case(Opcode.JAL):
                m.d.comb += itype.eq(Type.J)
            with m.Case(Opcode.JALR):
                m.d.comb += itype.eq(Type.I)
            with m.Case(Opcode.BRANCH):
                m.d.comb += itype.eq(Type.B)
            with m.Case(Opcode.LOAD):
                m.d.comb += itype.eq(Type.I)
            with m.Case(Opcode.STORE):
                m.d.comb += itype.eq(Type.S)
            with m.Case(Opcode.OP_IMM):
                m.d.comb += itype.eq(Type.I)
            with m.Case(Opcode.OP):
                m.d.comb += itype.eq(Type.R)
            with m.Case(Opcode.FENCE):
                m.d.comb += itype.eq(Type.I)
            with m.Case(Opcode.SYSTEM):
                m.d.comb += itype.eq(Type.I)

        m.d.comb += [
            opcode.eq(instruction[:7]),
            funct3.eq(instruction[12:15]),
            funct5.eq(instruction[27:32]),
            funct7.eq(instruction[25:32]),
            funct12.eq(instruction[20:32]),
            iimm12.eq(instruction[20:32]),
            simm12.eq(Cat(instruction[7:12], instruction[25:32])),
            bimm12.eq(Cat(0, instruction[8:12], instruction[25:31], instruction[7], instruction[31])),
            uimm20.eq(instruction[12:32]),
            jimm20.eq(Cat(0, instruction[21:31], instruction[20], instruction[12:20], instruction[31]))
        ]

        m.d.comb += [
            self.gpr_rs1.eq(instruction[15:20]),
            self.gpr_rs2.eq(instruction[20:25]),
        ]

        with m.If(self.enable):
            with m.Switch(itype):
                with m.Case(Type.I):
                    m.d.sync += self.immediate.eq(iimm12)
                with m.Case(Type.S):
                    m.d.sync += self.immediate.eq(simm12)
                with m.Case(Type.B):
                    m.d.sync += self.immediate.eq(bimm12)
                with m.Case(Type.U):
                    m.d.sync += self.immediate.eq(uimm20 << 12)
                with m.Case(Type.J):
                    m.d.sync += self.immediate.eq(jimm20)

            m.d.sync += [
                self.funct3.eq(funct3),
                self.gpr_rs1_q.eq(self.gpr_rs1),
                self.gpr_rd.eq(instruction[7:12]),
                self.csr_addr.eq(instruction[20:32]),
                self.csr_we.eq(~funct3[1] | self.gpr_rs1.any()),

                self.is_imm.eq(match(op=Opcode.OP_IMM)),
            ]

            m.d.sync += [
                self.inst_lui.eq(match(Opcode.LUI)),
                self.inst_auipc.eq(match(Opcode.AUIPC)),
                self.inst_jal.eq(match(Opcode.JAL)),
                self.inst_jalr.eq(match(Opcode.JALR)),
                self.inst_beq.eq(match(Opcode.BRANCH, f3=Funct3.BEQ)),
                self.inst_bne.eq(match(Opcode.BRANCH, f3=Funct3.BNE)),
                self.inst_blt.eq(match(Opcode.BRANCH, f3=Funct3.BLT)),
                self.inst_bge.eq(match(Opcode.BRANCH, f3=Funct3.BGE)),
                self.inst_bltu.eq(match(Opcode.BRANCH, f3=Funct3.BLTU)),
                self.inst_bgeu.eq(match(Opcode.BRANCH, f3=Funct3.BGEU)),
                self.inst_lb.eq(match(Opcode.LOAD, f3=Funct3.B)),
                self.inst_lh.eq(match(Opcode.LOAD, f3=Funct3.H)),
                self.inst_lw.eq(match(Opcode.LOAD, f3=Funct3.W)),
                self.inst_lbu.eq(match(Opcode.LOAD, f3=Funct3.BU)),
                self.inst_lhu.eq(match(Opcode.LOAD, f3=Funct3.HU)),
                self.inst_sb.eq(match(Opcode.STORE, f3=Funct3.B)),
                self.inst_sh.eq(match(Opcode.STORE, f3=Funct3.H)),
                self.inst_sw.eq(match(Opcode.STORE, f3=Funct3.W)),
                self.inst_addi.eq(match(Opcode.OP_IMM, f3=Funct3.ADD)),
                self.inst_slti.eq(match(Opcode.OP_IMM, f3=Funct3.SLT)),
                self.inst_sltiu.eq(match(Opcode.OP_IMM, f3=Funct3.SLTU)),
                self.inst_xori.eq(match(Opcode.OP_IMM, f3=Funct3.XOR)),
                self.inst_ori.eq(match(Opcode.OP_IMM, f3=Funct3.OR)),
                self.inst_andi.eq(match(Opcode.OP_IMM, f3=Funct3.AND)),
                self.inst_slli.eq(match(Opcode.OP_IMM, f3=Funct3.SLL, f7=0)),
                self.inst_srli.eq(match(Opcode.OP_IMM, f3=Funct3.SR, f7=Funct7.SRL)),
                self.inst_srai.eq(match(Opcode.OP_IMM, f3=Funct3.SR, f7=Funct7.SRA)),
                self.inst_add.eq(match(Opcode.OP, f3=Funct3.ADD, f7=Funct7.ADD)),
                self.inst_sub.eq(match(Opcode.OP, f3=Funct3.ADD, f7=Funct7.SUB)),
                self.inst_sll.eq(match(Opcode.OP, f3=Funct3.SLL, f7=0)),
                self.inst_slt.eq(match(Opcode.OP, f3=Funct3.SLT, f7=0)),
                self.inst_sltu.eq(match(Opcode.OP, f3=Funct3.SLTU, f7=0)),
                self.inst_xor.eq(match(Opcode.OP, f3=Funct3.XOR, f7=0)),
                self.inst_srl.eq(match(Opcode.OP, f3=Funct3.SR, f7=Funct7.SRL)),
                self.inst_sra.eq(match(Opcode.OP, f3=Funct3.SR, f7=Funct7.SRA)),
                self.inst_or.eq(match(Opcode.OP, f3=Funct3.OR, f7=0)),
                self.inst_and.eq(match(Opcode.OP, f3=Funct3.AND, f7=0)),
                self.inst_fence.eq(match(Opcode.FENCE, f3=Funct3.FENCE)),
                self.inst_fencei.eq(match(Opcode.FENCE, f3=Funct3.FENCEI)),
                self.inst_csrrw.eq(match(Opcode.SYSTEM, f3=Funct3.CSRRW)),
                self.inst_csrrs.eq(match(Opcode.SYSTEM, f3=Funct3.CSRRS)),
                self.inst_csrrc.eq(match(Opcode.SYSTEM, f3=Funct3.CSRRC)),
                self.inst_csrrwi.eq(match(Opcode.SYSTEM, f3=Funct3.CSRRWI)),
                self.inst_csrrsi.eq(match(Opcode.SYSTEM, f3=Funct3.CSRRSI)),
                self.inst_csrrci.eq(match(Opcode.SYSTEM, f3=Funct3.CSRRCI)),
                self.inst_xcall.eq(match(Opcode.SYSTEM, f3=Funct3.PRIV, f7=None, f12=Funct12.ECALL)),
                self.inst_xbreak.eq(match(Opcode.SYSTEM, f3=Funct3.PRIV, f7=None, f12=Funct12.EBREAK)),
                self.inst_mret.eq((self.privmode == PrivMode.Machine) & match(Opcode.SYSTEM, f3=Funct3.PRIV, f7=None, f12=Funct12.MRET)),
                self.inst_wfi.eq(match(Opcode.SYSTEM, f3=Funct3.PRIV, f7=None, f12=Funct12.WFI))
            ]
            if self.enable_rv32m:
                m.d.sync += [
                    self.inst_mul.eq(match(Opcode.OP, f3=Funct3.MUL, f7=Funct7.MULDIV)),
                    self.inst_mulh.eq(match(Opcode.OP, f3=Funct3.MULH, f7=Funct7.MULDIV)),
                    self.inst_mulhsu.eq(match(Opcode.OP, f3=Funct3.MULHSU, f7=Funct7.MULDIV)),
                    self.inst_mulhu.eq(match(Opcode.OP, f3=Funct3.MULHU, f7=Funct7.MULDIV)),
                    self.inst_div.eq(match(Opcode.OP, f3=Funct3.DIV, f7=Funct7.MULDIV)),
                    self.inst_divu.eq(match(Opcode.OP, f3=Funct3.DIVU, f7=Funct7.MULDIV)),
                    self.inst_rem.eq(match(Opcode.OP, f3=Funct3.REM, f7=Funct7.MULDIV)),
                    self.inst_remu.eq(match(Opcode.OP, f3=Funct3.REMU, f7=Funct7.MULDIV))
                ]
            if self.enable_rv32a:
                m.d.sync += [
                    self.inst_lr.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.LR)),
                    self.inst_sc.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.SC)),
                    self.inst_amoswap.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.AMOSWAP)),
                    self.inst_amoadd.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.AMOADD)),
                    self.inst_amoxor.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.AMOXOR)),
                    self.inst_amoor.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.AMOOR)),
                    self.inst_amoand.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.AMOAND)),
                    self.inst_amoand.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.AMOAND)),
                    self.inst_amomin.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.AMOMIN)),
                    self.inst_amomax.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.AMOMAX)),
                    self.inst_amominu.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.AMOMINU)),
                    self.inst_amomaxu.eq(match(Opcode.AMO, f3=Funct3.AMO, f5=Funct5.AMOMAXU)),
                ]

        m.d.comb += [
            self.is_j.eq(self.inst_jal | self.inst_jalr),
            self.is_b.eq(self.inst_beq | self.inst_bne | self.inst_blt | self.inst_bltu | self.inst_bge | self.inst_bgeu),
            self.is_ld.eq(self.inst_lb | self.inst_lbu | self.inst_lh | self.inst_lhu | self.inst_lw),
            self.is_st.eq(self.inst_sb | self.inst_sh | self.inst_sw),
            self.is_csr.eq(self.inst_csrrw | self.inst_csrrs | self.inst_csrrc | self.inst_csrrwi | self.inst_csrrsi | self.inst_csrrci),
            self.is_add.eq(self.inst_auipc | self.inst_lui | self.inst_add | self.inst_addi | self.inst_sub),
            self.is_logic.eq(self.inst_and | self.inst_andi | self.inst_or | self.inst_ori | self.inst_xor | self.inst_xori),
            self.is_cmp.eq(self.inst_slt | self.inst_slti | self.inst_sltu | self.inst_sltiu),
            self.is_shift.eq(self.inst_slli | self.inst_sll | self.inst_srli | self.inst_srl | self.inst_srai | self.inst_sra),
            self.use_alu.eq(self.is_add | self.is_j | self.is_b | self.is_cmp | self.is_logic),
        ]
        if self.enable_rv32m:
            m.d.comb += [
                self.is_mul.eq(self.inst_mul | self.inst_mulh | self.inst_mulhsu | self.inst_mulhu),
                self.is_div.eq(self.inst_div | self.inst_divu | self.inst_rem | self.inst_remu),
            ]
        if self.enable_rv32a:
            m.d.comb += [
                self.is_lrsc.eq(self.inst_lr | self.inst_sc),
                self.is_amo.eq(self.inst_amoadd | self.inst_amoand | self.inst_amomax | self.inst_amomaxu |
                               self.inst_amomin | self.inst_amominu | self.inst_amoswap | self.inst_amoxor | self.inst_amoor)
            ]

        return m
