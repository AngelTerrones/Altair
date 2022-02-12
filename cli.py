#!/usr/bin/env python3

from sysgen import SystemGenerator

name    = 'altair'
heading = 'ALTAIR: A 32-bit RISC-V CPU based on Amaranth'

if __name__ == '__main__':
    SystemGenerator(corename=name, heading=heading).run()
