import os
import subprocess
from subprocess import CalledProcessError
from string import Template
from elftools.elf.elffile import ELFFile

_boot_code = '''#define ram_start $RAM_START
    .global boot_start

boot_start:
    call ram_start
'''

_linker = '''OUTPUT_ARCH(riscv)
ENTRY(boot_start)

MEMORY {
       mem : ORIGIN = $ROM_START, LENGTH = 0x00000100
}

SECTIONS {
         .text : {
               *(.text)
               } > mem
}
'''

_makefile = '''RISCV_PREFIX  ?= riscv64-unknown-elf-
RISCV_GCC     := $(RVGCC_PATH)/$(RISCV_PREFIX)gcc
RISCV_OBJCOPY := $(RVGCC_PATH)/$(RISCV_PREFIX)objcopy
RISCV_OBJDUMP := $(RVGCC_PATH)/$(RISCV_PREFIX)objdump

CFLAGS = -march=rv32i -mabi=ilp32 -O3 -Wl,--no-relax
LFLAGS = -nostdlib -nostartfiles -mcmodel=medany -T linker.ld

all: boot.elf

%.elf: %.S
\t@$(RISCV_GCC) $(CFLAGS) $(LFLAGS) -o $@ $^
\t@$(RISCV_OBJDUMP) --disassemble-all --disassemble-zeroes $@ > $*.dump

.PRECIOUS: %.elf

'''

def generate_and_load(path: str, start: int, target: int, size: int):
    _generate_bootrom(path=path, start=start, target=target)
    return _load_elf(elffile=f'{path}/boot/boot.elf', start=start, size=size)


def _generate_bootrom(path: str, start: int, target: int):
        outfolder = f'{path}/boot'
        print(f'Create files for boot ROM')
        os.makedirs(outfolder, exist_ok=True)
        # create the files
        code_dict   = dict(RAM_START=f'{target:#010x}')
        linker_dict = dict(ROM_START=f'{start:#010x}')

        code   = Template(_boot_code).substitute(code_dict)
        linker = Template(_linker).substitute(linker_dict)

        with open(outfolder + '/boot.S', 'w') as f:
            f.write(code)
        with open(outfolder + '/linker.ld', 'w') as f:
            f.write(linker)
        with open(outfolder + '/makefile', 'w') as f:
            f.write(_makefile)

        # compile the elf file
        print('Compiling boot ROM')
        try:
            subprocess.check_output(f'make --no-print-directory -C {outfolder}', text=True, shell=True, stderr=subprocess.STDOUT)
        except CalledProcessError as error:
            print('Unable to build ROM:\n')
            print(error.stdout)
            raise error


def _load_elf(elffile: str, start: int, size: int):
    img = [0 for _ in range(size)]
    with open(elffile, 'rb') as f:
        e = ELFFile(f)
        # get the number of program headers
        phnum = e.header['e_phnum']
        # get the entries
        print(f'Loading boot ROM: {elffile}')
        for idx in range(phnum):
            segment = e.get_segment(idx)
            data    = segment.data()
            begin   = segment.header['p_paddr']
            end     = begin + segment.header['p_filesz']
            print(f'  - Segment {idx}: Begin = {hex(begin)}. End = {hex(end)}')
            # copy to array
            b = begin - start
            e = (end - start) >> 2
            img[b:e] = [int.from_bytes(data[i:i + 4], 'little') for i in range(0, len(data), 4)]

    return img
