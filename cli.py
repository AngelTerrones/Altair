#!/usr/bin/env python3

from sysgen.sysgen import Sysgen

name    = 'altair'
heading = 'ALTAIR: A 32-bit RISC-V CPU based on Amaranth'

if __name__ == '__main__':
    Sysgen(corename=name, heading=heading).run()
