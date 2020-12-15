/*
 * Copyright (C) 2018 Angel Terrones <angelterrones@gmail.com>
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 */

#include <chrono>
#include <atomic>
#include <signal.h>
#include "aelf.h"
#include "coretb.h"
#include "defines.h"

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
int CORETB::SimulateCore(const std::string &progfile, const unsigned long max_time, const std::string &s_signature) {
        bool ok        = false;
        bool notimeout = max_time == 0;

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
