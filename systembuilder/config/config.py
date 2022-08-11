import os
import yaml
from typing import Dict

header = '''\033[0;32mConfiguration\033[0;0m
Variant name: {variant}
Config file: {configfile}
\033[0;32mBuild parameters\033[0;0m'''

current_path = os.path.dirname(os.path.abspath(__file__))
cpu_variants = [os.path.splitext(f)[0] for f in os.listdir(current_path) if f.endswith('.yml')]
cpu_variants.append('custom')
config_files = {variant: f'{current_path}/{variant}.yml' for variant in cpu_variants}


def print_dict(dict_: dict, level: int = 0):
    indent = ''
    if level != 0:
        indent = '{:>{}}'.format('- ', 4 * level)

    for key, item in dict_.items():
        if isinstance(item, dict):
            print(f'{indent}{key}:')
            print_dict(item, level + 1)
        else:
            if isinstance(item, list):
                print(f'{indent}{key}: [start_addr: {item[0]:#010x}, addr_width: {item[1]}]')
            else:
                if 'address' in key:
                    print(f'{indent}{key}: {item:#010x}')
                else:
                    print(f'{indent}{key}: {item}')


def load_config(variant: str, configfile: str, verbose: bool = True) -> Dict:
    if variant == 'custom':
        if configfile is None:
            raise RuntimeError('A configuration file is needed for custom variant')
    else:
        configfile = config_files[variant]

    core_config = yaml.load(open(configfile).read(), Loader=yaml.Loader)

    if verbose:
        print(header.format(variant=variant, configfile=configfile))
        print_dict(core_config)

    return core_config
