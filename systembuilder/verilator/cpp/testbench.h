#ifndef TESTBENCH_H
#define TESTBENCH_H

#include <memory>
#include <verilated.h>
#include <verilated_vcd_c.h>

template <class DUT> class Testbench {
public:
        Testbench(double frequency, double timescale=1e-9): m_top(new DUT), m_tick_count(0) {
                Verilated::traceEverOn(true);
                m_top->clk = 1;
                m_top->rst = 1;
                Evaluate();

                m_tickdiv = 1/(frequency * timescale);
                m_tickdivh = m_tickdiv/2;
        }

        uint32_t getTime() {
                return m_tick_count * m_tickdiv;
        }

        virtual ~Testbench() {
                if (m_trace)
                        m_trace->close();
                //m_top.reset(nullptr);
        }

        virtual void OpenTrace(const char *filename) {
                if (!m_trace) {
                        m_trace.reset(new VerilatedVcdC);
                        m_top->trace(m_trace.get(), 99);
                        m_trace->open(filename);
                }
        }

        virtual void CloseTrace() {
                if (m_trace)
                        m_trace->close();
        }

        virtual void Evaluate() {
                m_top->eval();
        }

        virtual void Tick() {
                m_tick_count++;
                m_top->clk = 1;
                Evaluate();
                if (m_trace)
                        m_trace->dump(m_tickdiv * m_tick_count - m_tickdivh);
                m_top->clk = 0;
                Evaluate();
                if (m_trace)
                        m_trace->dump(m_tickdiv * m_tick_count);
                /*
                Verilator 4.034 doesn't like using the sime timestamp multiple times...

                m_top->clk = 1;
                Evaluate();
                if (m_trace) {
                        m_trace->dump(m_tickdiv * m_tick_count + m_tickdivh);
                        m_trace->flush();
                }*/
        }

        virtual void Reset(unsigned int ticks=5) {
                m_top->rst = 1;
                for (unsigned int i = 0; i < ticks; i++)
                        Tick();
                m_top->rst = 0;
        }

protected:
        uint32_t                       m_tickdiv;
        uint32_t                       m_tickdivh;
        std::unique_ptr<DUT>           m_top;
        std::unique_ptr<VerilatedVcdC> m_trace;
        vluint64_t                     m_tick_count;
};

#endif
