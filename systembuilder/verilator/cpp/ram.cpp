#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "aelf.h"
#include "defines.h"
#include "Vtop__Dpi.h"

// -----------------------------------------------------------------------------
// DPI function
void ram_c_dpi_load(const svOpenArrayHandle mem_ptr, const char *filename) {
        ELFSECTION **section;
        uint8_t     *mem = static_cast<uint8_t *>(svGetArrayPtr(mem_ptr));
        if (not isELF(filename)) {
                fprintf(stderr, ANSI_COLOR_RED "[RAM] Invalid elf: %s\n" ANSI_COLOR_RESET, filename);
                exit(EXIT_FAILURE);
        }
        elfread(filename, section);
        for (int s = 0; section[s] != nullptr; s++){
                auto start = section[s]->m_start;
                auto end   = section[s]->m_start + section[s]->m_len;
                if (start >= MEMSTART && end < MEMSTART + MEMSZ) {
                        uint32_t offset = section[s]->m_start - MEMSTART;
                        std::memcpy(mem + offset, section[s]->m_data, section[s]->m_len);
                } else {
                        fprintf(stderr, ANSI_COLOR_YELLOW "[RAM] WARNING: unable to fit section %d. Start: 0x%08x, End: 0x%08x\n" ANSI_COLOR_RESET, s, start, end);
                }
        }
        delete [] section;
}
