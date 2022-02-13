#ifndef CORETB_H
#define CORETB_H

#include <vector>
#include "Vtop.h"
#include "Vtop__Dpi.h"
#include "testbench.h"

class CORETB: public Testbench<Vtop> {
public:
        CORETB();
        int SimulateCore(const std::string &progfile,
                         const unsigned long max_time,
                         const std::string &signature,
                         const unsigned long io_base_addr,
                         const unsigned long io_bit_size);
private:
        uint32_t PrintExitMessage (const bool ok, const unsigned long max_time);
        bool     CheckTOHOST      (bool &ok);
        void     LoadMemory       (const std::string &progfile);
        void     DumpSignature    (const std::string &signature);

        void     check_bus        ();
        void     _stdout           ();
        void     _interrupts      ();
        //
        uint32_t          m_exitCode;
        uint32_t          m_tohost;
        uint32_t          m_fromhost;
        uint32_t          m_begin_signature;
        uint32_t          m_end_signature;
        //
        uint32_t          m_stdout_addr;
        uint32_t          m_interrupt_addr;
        std::vector<char> m_buffer;
};

#endif
