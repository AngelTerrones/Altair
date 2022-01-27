import os
from typing import Dict
from string import Template

current_path = os.path.dirname(os.path.realpath(__file__))
top_template = f'{current_path}/verilog/top.v'
makefile_template = f'{current_path}/makefile'


_define_h = '''#ifndef DEFINES_H
#define DEFINES_H

// -----------------------------------------------------------------------------
#if defined(__WIN32__) || defined(__MINGW32__)
#define mkdir(a, b) mkdir(a) /* mkdir command on Win32 does not support file permissions */
#endif
// -----------------------------------------------------------------------------
#define ANSI_COLOR_RED     "\x1b[31m"
#define ANSI_COLOR_GREEN   "\x1b[32m"
#define ANSI_COLOR_YELLOW  "\x1b[33m"
#define ANSI_COLOR_BLUE    "\x1b[34m"
#define ANSI_COLOR_MAGENTA "\x1b[35m"
#define ANSI_COLOR_CYAN    "\x1b[36m"
#define ANSI_COLOR_RESET   "\x1b[0m"
// -----------------------------------------------------------------------------
// Fixed parameters from TOP.v
#define TBFREQ   100e6
#define TBTS     1e-9
#define MEMSTART $RAM_ADDR    // Initial address
#define MEMSZ    $RAM_SIZE    // size: 16 MB
// -----------------------------------------------------------------------------

#endif
'''


def generate_testbench(corename, config: Dict, path: str) -> None:
    addr = config['platform']['mport'][0]
    size = config['platform']['mport'][1]
    data_v = dict(CORENAME=corename,
                  RAM_ADDR=f"32'h{addr:08x}",
                  RAM_ADDR_WIDTH=size - 2)  # byte to word
    data_h = dict(RAM_ADDR=f"{addr:#010x}",
                  RAM_SIZE=1 << size)  # bytes
    # top.v
    with open(top_template, 'r') as f:
        template = Template(f.read())
    top = template.substitute(data_v)
    with open(path + '/top.v', 'w') as f:
        f.write(top)
    # defines.h
    template = Template(_define_h)
    defines_h = template.substitute(data_h)
    with open(path + '/defines.h', 'w') as f:
        f.write(defines_h)


def generate_makefile(path: str):
    data = dict(TVERILATOR=current_path)
    # create the template
    with open(makefile_template, 'r') as f:
        template = Template(f.read())
    top = template.substitute(data)
    with open(path + '/makefile', 'w') as f:
        f.write(top)
