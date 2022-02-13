#include <thread>
#include <sys/stat.h>
#include "coretb.h"
#include "defines.h"
#include "inputparser.h"

void printHelp() {
        printf("RISC-V CPU Verilator model.\n");
        printf("Using configuration file: " BCONFIG"\n");
        printf("Usage:\n");
        printf("\t" EXE ".exe --file <ELF file> [--signature <signature file>] [--timeout <max time>] [--iobase <hex address>] [--iobits <addr size>] [--trace]\n");
        printf("\t" EXE ".exe --help\n");
}

void process_numeric(const std::string &arg, uint32_t &variable, int base, const char *msg) {
        if (!arg.empty()) {
                variable = std::stoul(arg, nullptr, base);
        }
        printf(msg, variable);
}

// -----------------------------------------------------------------------------
// Main
int main(int argc, char **argv) {
        INPUTPARSER input(argc, argv);
        const std::string &s_progfile  = input.GetCmdOption("--file");
        const std::string &s_signature = input.GetCmdOption("--signature");
        const std::string &s_timeout   = input.GetCmdOption("--timeout");
        const std::string &s_iobase    = input.GetCmdOption("--iobase");
        const std::string &s_iobitsize = input.GetCmdOption("--iobits");
        const bool         trace       = input.CmdOptionExist("--trace");
        // help
        const bool         help        = input.CmdOptionExist("--help");
        //
        bool     badParams    = false;
        uint32_t timeout      = 0;           // infinite
        uint32_t io_base_addr = 0x40000000;  // Default address
        uint32_t io_bit_size  = 28;          // Default bit size

        // ---------------------------------------------------------------------
        // process options
        if (s_progfile.empty())
                badParams = true;
        // check for help
        if (badParams || help) {
                printHelp();
                exit(EXIT_FAILURE);
        }
        printf("[MAIN] Using configuration file: " ANSI_COLOR_YELLOW BCONFIG "\n" ANSI_COLOR_RESET);
        process_numeric(s_timeout, timeout, 10, "[MAIN] Time limit: %d\n");
        process_numeric(s_iobase, io_base_addr, 16, "[MAIN] Base address for stdout: 0x%08X\n");
        process_numeric(s_iobitsize, io_bit_size, 10, "[MAIN] IO bit size: %d\n");
        // ---------------------------------------------------------------------
        CORETB *tb =new CORETB();
#ifdef DEBUG
        Verilated::scopesDump();
#endif
        const char* vcdFile = "build/trace_" EXE ".vcd";
        if (trace) {
                printf("[MAIN] Generate VCD file in build folder\n");
                tb->OpenTrace(vcdFile);
        }
        int exitCode = tb->SimulateCore(s_progfile, timeout, s_signature, io_base_addr, io_bit_size);
        tb->CloseTrace();
        delete tb;
        return exitCode;
}
// -----------------------------------------------------------------------------
