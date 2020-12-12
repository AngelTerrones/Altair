#!/usr/bin/env python3

import re
import os
import glob
import sys
import argparse
import subprocess
from subprocess import CalledProcessError
from nmigen.back import verilog
from nmigen.hdl.ir import Fragment
from altair.gateware.core import CoreGenerator
from altair.config.config import logo
from altair.config.config import load_config
from altair.config.config import cpu_variants
from altair.config.config import config_files
from altair.verilator.generate import generate_makefile
from altair.verilator.generate import generate_testbench


def need_rebuild(bfolder: str):
    root  = os.path.dirname(os.path.abspath(__file__))
    files = glob.glob(f'{root}/altair/gateware/**/*.py', recursive=True)
    if not os.path.exists(f'{bfolder}/altair_core.v'):
        return True
    ref   = os.stat(f'{bfolder}/altair_core.v').st_mtime_ns

    for file in files:
        tmp = os.stat(file).st_mtime_ns
        if tmp > ref:
            return True

    return False


def CPU_to_verilog(core_config: dict, path: str, vfile: str):
    core_args     = core_config['core']
    platform_args = core_config['platform']
    cpu           = CoreGenerator(**core_args, **platform_args, build_path=path)
    ports         = cpu.port_list()

    # generate the verilog file
    fragment = Fragment.get(cpu, None)
    output   = verilog.convert(fragment, name='altair_core', ports=ports)
    try:
        with open(f'{path}/{vfile}', 'w') as f:
            f.write(output)
    except EnvironmentError as error:
        print(f"Error: {error}. Check if the output path exists.", file=sys.stderr)


def generate_cpu_verilog(args):
    # load configuration
    core_config = load_config(args.variant, args.config)
    CPU_to_verilog(core_config, args.filename)


def build_testbench(args):
    for variant in args.variant:
        path = f'build/{variant}'

        # check if the testbench has been built
        rebuild = need_rebuild(path)
        if (os.path.exists(f'{path}/core.exe') and not rebuild):
            print('Testbench up-to-date. Skipping.')
        else:
            # generate verilog
            os.makedirs(path, exist_ok=True)
            core_config = load_config(variant, args.config)
            CPU_to_verilog(core_config, path, 'altair_core.v')

            # generate testbench and makefile
            generate_testbench(core_config, path)
            generate_makefile(path)
        # get the config file
        if variant == 'custom':
            configfile = args.config
        else:
            configfile = config_files[variant]

        # run make
        os.environ['BCONFIG'] = configfile
        try:
            subprocess.check_call(f'make --no-print-directory -C {path} -j$(nproc)', shell=True, stderr=subprocess.STDOUT)
            print('--------------------------------------------------')
            print('Build: DONE')
            print('--------------------------------------------------')
        except CalledProcessError as error:
            print('--------------------------------------------------')
            print('Build with errors:\n')
            print(error)
            print('--------------------------------------------------')


def run_compliance(args):
    # build the testbench
    build_testbench(args)

    riscv_path = os.environ.get('RVGCC_PATH')
    if riscv_path is None:
        raise EnvironmentError('Environment variable "RVGCC_PATH" is undefined.')

    os.environ['RISCV_PREFIX'] = f'{riscv_path}/riscv64-unknown-elf-'

    variant_msg = []
    for variant in args.variant:
        print('------------------------------------------------------------')
        print(f'Running tests for {variant} configuration:\n')

        os.environ['TARGET_FOLDER'] = os.path.abspath(f'build/{variant}')
        isa_msg = []
        for isa in args.isa:
            try:
                cmd = f'make --no-print-directory -C {args.rvc} variant RISCV_TARGET=nht RISCV_DEVICE=rv32i RISCV_ISA={isa}'
                output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
                isa_msg.append(f'{isa} test ended sucessfully.')
            except CalledProcessError as error:
                output = error.stdout
                isa_msg.append(f'{isa} test ended with errors.')

            result = re.search(f'files \.\.\. \n(.*)\nmake: Leaving', output, re.DOTALL)  # noqa
            if result:
                print(f'* {isa}:\n\n{result.group(1)}\n')

            # write log file
            logfile = os.path.abspath(f'build/{variant}') + f'/{isa}.log'
            with open(logfile, 'w') as f:
                f.write(output)

        variant_msg.append(isa_msg)

    print('============================================================')
    print('Result:\n')
    for variant, msg in zip(args.variant, variant_msg):
        print(f'{variant} configuration:')
        for tmp in msg:
            print(f'\t{tmp}')
    print('============================================================')


def main() -> None:
    parser = argparse.ArgumentParser(description='''\033[1;33m{}\033[0m'''.format(logo))

    # Actions
    p_action = parser.add_subparsers(dest='action', help='Available commands')
    # --------------------------------------------------------------------------
    # Generate core verilog
    p_generate_cpu = p_action.add_parser('generate_cpu', help='Generate CPU Verilog from the design')
    p_generate_cpu.add_argument('filename', metavar="FILE", help="Write generated verilog to FILE")
    p_generate_cpu.add_argument('--variant', choices=cpu_variants, required=True, help='CPU type')
    p_generate_cpu.add_argument('--config', help='Configuration file for custom variants')
    # --------------------------------------------------------------------------
    # build verilator testbench
    p_buildtb = p_action.add_parser('buildtb', help='Build the Verilator simulator')
    p_buildtb.add_argument('--variant', choices=cpu_variants, nargs='+', required=True, help='CPU type')
    p_buildtb.add_argument('--config', help='Configuration file for custom variants')
    # --------------------------------------------------------------------------
    # run compliance test
    p_compliance = p_action.add_parser('compliance', help='Run the RISC-V compliance test')
    p_compliance.add_argument('--rvc', required=True, help='Path to riscv-compliance')
    p_compliance.add_argument('--variant', choices=cpu_variants, nargs='+', required=True, help='CPU type')
    p_compliance.add_argument('--config', help='Configuration file for custom variants')
    p_compliance.add_argument('--isa', choices=['rv32i', 'rv32im', 'rv32mi', 'rv32ui', 'rv32ua', 'rv32Zicsr', 'rv32Zifencei'],
                              nargs='+', required=True, help='Available compliance tests',)
    # --------------------------------------------------------------------------
    args = parser.parse_args()
    # --------------------------------------------------------------------------
    # execute
    if args.action == 'generate_cpu':
        generate_cpu_verilog(args)
    elif args.action == 'buildtb':
        build_testbench(args)
    elif args.action == 'compliance':
        run_compliance(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
