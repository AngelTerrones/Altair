#ifndef CORETB_H
#define CORETB_H

#include <mutex>
#include "Vtop.h"
#include "Vtop__Dpi.h"
#include "testbench.h"

class CORETB: public Testbench<Vtop> {
public:
        CORETB();
        int SimulateCore(const std::string &progfile, const unsigned long max_time, const std::string &signature);
private:
        uint32_t PrintExitMessage (const bool ok, const unsigned long max_time);
        bool     CheckTOHOST      (bool &ok);
        void     LoadMemory       (const std::string &progfile);
        void     DumpSignature    (const std::string &signature);
        //
        uint32_t m_exitCode;
        uint32_t m_tohost;
        uint32_t m_fromhost;
        uint32_t m_begin_signature;
        uint32_t m_end_signature;
};

#endif
