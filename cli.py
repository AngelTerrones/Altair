#!/usr/bin/env python3

from systembuilder import SystemBuilder

name    = 'altair'
heading = 'ALTAIR: A 32-bit RISC-V CPU based on Amaranth'

if __name__ == '__main__':
    SystemBuilder(corename=name, heading=heading).run()
