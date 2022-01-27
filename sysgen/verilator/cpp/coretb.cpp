#include <chrono>
#include <atomic>
#include <signal.h>
#include "aelf.h"
#include "coretb.h"
#include "defines.h"

#define ADDR   io___05Faddr
#define DAT_W  io___05Fdat_w
#define CYC    io___05Fcyc
#define ACK    io___05Fack

#define STDIO_OFFSET     0x1000
#define INTERRUPT_OFFSET 0x2000

static std::atomic_bool quit(false);

// -----------------------------------------------------------------------------
void intHandler(int signo){
        printf("\r[CORETB] Quit...\n");
        fflush(stdout);
        quit = true;
        signal(SIGINT, SIG_DFL); // restore default handler.
}
// -----------------------------------------------------------------------------
CORETB::CORETB() : Testbench(TBFREQ, TBTS), m_exitCode(-1) {
}
// -----------------------------------------------------------------------------
int CORETB::SimulateCore(const std::string &progfile,
                         const unsigned long max_time,
                         const std::string &s_signature,
                         const unsigned long io_base_addr,
                         const unsigned long io_bit_size) {
        bool ok        = false;
        bool notimeout = max_time == 0;
        // Init I/O "devices"
        uint32_t io_mask = ((1 << io_bit_size) - 1);
        m_stdout_addr    = ((io_base_addr + STDIO_OFFSET) >> 2) & io_mask;
        m_interrupt_addr = ((io_base_addr + INTERRUPT_OFFSET) >> 2) & io_mask;
        m_buffer.reserve(256);
        std::fill(m_buffer.begin(), m_buffer.end(), 0);  // fill with zeros first, then clear
        m_buffer.clear();

        // -------------------------------------------------------------
        // Add trap handler to catch [Ctrl + C]
        // Configure the signal to abort (blocking) system calls
        struct sigaction saStruct;
        saStruct.sa_flags   = 0;
        saStruct.sa_handler = intHandler;
        sigaction(SIGINT, &saStruct, NULL);
        // -------------------------------------------------------------
        LoadMemory(progfile);
        m_tohost   = getSymbol(progfile.data(), "tohost");
        m_fromhost = getSymbol(progfile.data(), "fromhost");
        if (!s_signature.empty()) {
                m_begin_signature = getSymbol(progfile.data(), "begin_signature");
                m_end_signature   = getSymbol(progfile.data(), "end_signature");
        }
        Reset();
        // Run for 7 cycles, reset
        for(auto i= 0; i < 7; i++)
                Tick();
        Reset();

        while ((getTime() <= max_time || notimeout) && !Verilated::gotFinish() && !quit) {
                Tick();
                check_bus();
                if (CheckTOHOST(ok))
                        break;
        }
        // -------------------------------------------------------------
        Tick();
        Tick();
        Tick();
        if (!s_signature.empty())
                DumpSignature(s_signature);
        return PrintExitMessage(ok, max_time);
}
// -----------------------------------------------------------------------------
uint32_t CORETB::PrintExitMessage(const bool ok, const unsigned long max_time) {
        if (ok)
                printf(ANSI_COLOR_GREEN "[CORETB] Simulation done. Time %u\n" ANSI_COLOR_RESET, getTime());
        else if (getTime() < max_time || max_time == 0)
                printf(ANSI_COLOR_RED "[CORETB] Simulation error. Exit code: %08X. Time: %u\n" ANSI_COLOR_RESET, m_exitCode, getTime());
        else
                printf(ANSI_COLOR_MAGENTA "[CORETB] Simulation error. Timeout. Time: %u\n" ANSI_COLOR_RESET, getTime());

        return 0;
}
// -----------------------------------------------------------------------------
bool CORETB::CheckTOHOST(bool &ok) {
        svSetScope(svGetScopeFromName("TOP.top.memory")); // Set the scope before using DPI functions
        uint32_t tohost = ram_v_dpi_read_word(m_tohost);
        if (tohost == 0)
                return false;
        ok         = tohost == 1;
        m_exitCode = tohost;
        return true;
}
// -----------------------------------------------------------------------------
void CORETB::LoadMemory(const std::string &progfile) {
        svSetScope(svGetScopeFromName("TOP.top.memory"));
        ram_v_dpi_load(progfile.data());
        printf("[CORETB] Executing file: " ANSI_COLOR_YELLOW "%s\n" ANSI_COLOR_RESET, progfile.c_str());
}
// -----------------------------------------------------------------------------
void CORETB::DumpSignature(const std::string &signature) {
        FILE *fp = fopen(signature.data(), "w");
        if (fp == NULL) {
                fprintf(stderr, ANSI_COLOR_RED "[CORETB] Unable to open the signature file. \n" ANSI_COLOR_RESET);
                return;
        }
        // Signature from riscv-compliance: 1 word per line
        for (uint32_t idx = m_begin_signature; idx < m_end_signature; idx = idx + 4) {
                fprintf(fp, "%08x\n", ram_v_dpi_read_word(idx));
        }
        fclose(fp);
}
// -----------------------------------------------------------------------------
void CORETB::check_bus() {
        if (!m_top->CYC) return;

        if (!m_top->ACK){
                if (m_top->ADDR == m_stdout_addr) {
                        _stdout();
                } else if (m_top->ADDR == m_interrupt_addr) {
                        _interrupts();
                }
        } else {
                m_top->ACK = 0;
        }
}
// -----------------------------------------------------------------------------
void CORETB::_stdout() {
        char dat = m_top->DAT_W & 0xff;
        m_top->ACK = 1;
        // flush buffer?
        if ((m_buffer.size() == m_buffer.capacity()) || dat == '\n') {
                printf("%s%c", m_buffer.data(), dat);
                std::fill(m_buffer.begin(), m_buffer.end(), 0);
                m_buffer.clear();
                fflush(stdout);
        } else {
                m_buffer.push_back(dat);
        }
}
// -----------------------------------------------------------------------------
void CORETB::_interrupts() {
        m_top->interrupts = m_top->DAT_W;
        m_top->ACK = 1;
}
