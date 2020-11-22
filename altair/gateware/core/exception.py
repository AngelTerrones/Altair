from nmigen import Cat
from nmigen import Module
from nmigen import Signal
from nmigen import Elaboratable
from nmigen.lib.coding import PriorityEncoder
from nmigen.build import Platform
from altair.gateware.core.csr import AutoCSR
from altair.gateware.core.csr import CSRFile
from altair.gateware.core.isa import CSRIndex
from altair.gateware.core.isa import ExceptionCause
from altair.gateware.core.isa import PrivMode


class ExceptionUnit(Elaboratable, AutoCSR):
    def __init__(self,
                 csrf: CSRFile,
                 hartid: int = 0,
                 enable_user_mode: bool = False,
                 enable_extra_csr: bool = False,
                 enable_rv32m: bool = False,
                 reset_address: int = 0x8000_0000
                 ) -> None:
        # ----------------------------------------------------------------------
        self.hartid           = hartid
        self.enable_user_mode = enable_user_mode
        self.enable_extra_csr = enable_extra_csr
        self.enable_rv32m     = enable_rv32m
        self.reset_address    = reset_address
        # ----------------------------------------------------------------------
        if self.enable_extra_csr:
            self.misa      = csrf.add_register('misa', CSRIndex.MISA)
            self.mhartid   = csrf.add_register('mhartid', CSRIndex.MHARTID)
            self.mimpid    = csrf.add_register('mimpid', CSRIndex.MIMPID)
            self.marchid   = csrf.add_register('marchid', CSRIndex.MARCHID)
            self.mvendorid = csrf.add_register('mvendorid', CSRIndex.MVENDORID)
            self.minstret  = csrf.add_register('minstret', CSRIndex.MINSTRET)
            self.mcycle    = csrf.add_register('mcycle', CSRIndex.MCYCLE)
            self.minstreth = csrf.add_register('minstreth', CSRIndex.MINSTRETH)
            self.mcycleh   = csrf.add_register('mcycleh', CSRIndex.MCYCLEH)
            if self.enable_user_mode:
                self.instret  = csrf.add_register('instret', CSRIndex.INSTRET)
                self.cycle    = csrf.add_register('cycle', CSRIndex.CYCLE)
                self.instreth = csrf.add_register('instreth', CSRIndex.INSTRETH)
                self.cycleh   = csrf.add_register('cycleh', CSRIndex.CYCLEH)
        self.mstatus  = csrf.add_register('mstatus', CSRIndex.MSTATUS)
        self.mie      = csrf.add_register('mie', CSRIndex.MIE)
        self.mtvec    = csrf.add_register('mtvec', CSRIndex.MTVEC)
        self.mscratch = csrf.add_register('mscratch', CSRIndex.MSCRATCH)
        self.mepc     = csrf.add_register('mepc', CSRIndex.MEPC)
        self.mcause   = csrf.add_register('mcause', CSRIndex.MCAUSE)
        self.mtval    = csrf.add_register('mtval', CSRIndex.MTVAL)
        self.mip      = csrf.add_register('mip', CSRIndex.MIP)
        # ----------------------------------------------------------------------
        self.enable               = Signal()
        self.external_interrupt   = Signal()    # input
        self.software_interrupt   = Signal()    # input
        self.timer_interrupt      = Signal()    # input
        self.edata                = Signal(32)  # input
        self.ecode                = Signal(ExceptionCause)  # input
        self.m_mret               = Signal()    # input
        self.m_pc                 = Signal(32)  # input
        self.m_exception          = Signal()    # input
        self.m_interrupt          = Signal()    # output
        self.m_privmode           = Signal(PrivMode)   # output
        if self.enable_extra_csr:
            self.w_retire = Signal()

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # --------------------------------------------------------------------------------
        # Set MTVEC to the RESET address, to avoid getting lost in limbo if there's an exception
        # before the boot code sets this to a valid value
        self.mtvec.read.base.reset = self.reset_address >> 2

        # MISA reset value
        if self.enable_extra_csr:
            misa_ext = (1 << (ord('i') - ord('a')))  # 32-bits processor. RV32I
            if self.enable_rv32m:
                misa_ext |= 1 << (ord('m') - ord('a'))  # RV32M
            if self.enable_user_mode:
                misa_ext |= 1 << (ord('u') - ord('a'))  # User mode enabled

            self.misa.read.extensions.reset = misa_ext
            self.misa.read.mxl.reset        = 0x1
            self.mhartid.read.data.reset    = self.hartid

        if self.enable_user_mode:
            self.mstatus.read.mpp.reset = PrivMode.User
        else:
            self.mstatus.read.mpp.reset = PrivMode.Machine

        privmode = Signal(PrivMode, reset=PrivMode.Machine)
        m.d.comb += self.m_privmode.eq(privmode)

        # --------------------------------------------------------------------------------
        # Read/write behavior for all registers in this module
        for register in self.get_csrs():
            with m.If(register.update):
                m.d.sync += register.read.eq(register.write)

        # --------------------------------------------------------------------------------
        interrupts = m.submodules.interrupts = PriorityEncoder(ExceptionCause.MAX_NUM)
        m.d.comb += [
            interrupts.i[ExceptionCause.I_M_SOFTWARE].eq(self.mip.read.msip & self.mie.read.msie),
            interrupts.i[ExceptionCause.I_M_TIMER].eq(self.mip.read.mtip & self.mie.read.mtie),
            interrupts.i[ExceptionCause.I_M_EXTERNAL].eq(self.mip.read.meip & self.mie.read.meie),
        ]

        # interrupts are globally enable for less priviledge mode than Machine
        m.d.comb += self.m_interrupt.eq(~interrupts.n & (self.mstatus.read.mie | (privmode != PrivMode.Machine)))

        # --------------------------------------------------------------------------------
        m.d.sync += [
            self.mip.read.msip.eq(self.software_interrupt),
            self.mip.read.mtip.eq(self.timer_interrupt),
            self.mip.read.meip.eq(self.external_interrupt)
        ]

        if self.enable_user_mode:
            with m.If(self.mstatus.write.mpp != PrivMode.User):
                # In case of writting an invalid priviledge mode, force a valid one
                # For this case, anything different to the User mode is forced to Machine mode.
                m.d.sync += self.mstatus.read.mpp.eq(PrivMode.Machine)
        else:
            m.d.sync += self.mstatus.read.mpp.eq(PrivMode.Machine)  # Only machine mode

        # behavior for exception handling
        with m.If(self.enable):
            with m.If(self.m_exception | self.m_interrupt):
                # Register the exception and move one priviledge mode down.
                m.d.sync += [
                    self.mepc.read.base.eq(self.m_pc[2:]),
                    self.mstatus.read.mpie.eq(self.mstatus.read.mie),
                    self.mstatus.read.mie.eq(0),

                    # Change priviledge mode
                    privmode.eq(PrivMode.Machine),
                    self.mstatus.read.mpp.eq(privmode)
                ]
                # store cause/mtval
                with m.If(self.m_exception):  # mmmm
                    m.d.sync += [
                        self.mcause.read.ecode.eq(self.ecode),
                        self.mcause.read.interrupt.eq(0),
                        self.mtval.read.eq(self.edata)
                    ]
                with m.Else():
                    m.d.sync += [
                        self.mcause.read.ecode.eq(interrupts.o),
                        self.mcause.read.interrupt.eq(1)
                    ]
            with m.Elif(self.m_mret):
                # restore old mie
                # Restore priviledge mode
                m.d.sync += [
                    self.mstatus.read.mie.eq(self.mstatus.read.mpie),
                    privmode.eq(self.mstatus.read.mpp),
                ]
                if self.enable_user_mode:
                    m.d.sync += self.mstatus.read.mpp.eq(PrivMode.User)

        # counters
        if self.enable_extra_csr:
            mcycle   = Signal(64)
            minstret = Signal(64)

            with m.If(~self.mcycle.update):
                m.d.sync += [
                    self.mcycle.read.eq(mcycle[:32]),
                    self.mcycleh.read.eq(mcycle[32:64])
                ]
            with m.If(~self.minstret.update):
                m.d.sync += [
                    self.minstret.read.eq(minstret[:32]),
                    self.minstreth.read.eq(minstret[32:64])
                ]

            m.d.comb += mcycle.eq(Cat(self.mcycle.read, self.mcycleh.read) + 1)
            with m.If(self.w_retire):
                m.d.comb += minstret.eq(Cat(self.minstret.read, self.minstreth.read) + 1)
            with m.Else():
                m.d.comb += minstret.eq(Cat(self.minstret.read, self.minstreth.read))

            # shadow versions of MCYCLE and MINSTRET
            if self.enable_user_mode:
                m.d.sync += [
                    self.cycle.read.eq(mcycle[:32]),
                    self.cycleh.read.eq(mcycle[32:64]),
                    self.instret.read.eq(minstret[:32]),
                    self.instreth.read.eq(minstret[32:64])
                ]

        return m
