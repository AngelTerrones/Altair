import os
import yaml
from typing import Dict

logo = r'''--------------------------------------------------
    ALTAIR

    A 32-bit RISC-V CPU based on nMigen
--------------------------------------------------'''

header = '''\033[1;33m{logo}\033[0m

\033[0;32mConfiguration\033[0;0m
Variant name: {variant}
Config file: {configfile}

\033[0;32mBuild parameters\033[0;0m'''

current_path = os.path.dirname(os.path.abspath(__file__))
cpu_variants = ['minimal', 'lite', 'standard', 'custom']
config_files = {variant: f'{current_path}/{variant}.yml' for variant in cpu_variants}


def load_config(variant: str, configfile: str, verbose: bool) -> Dict:
    if variant == 'custom':
        if configfile is None:
            raise RuntimeError('A configuration file is needed for custom variant')
    else:
        configfile = config_files[variant]

    core_config = yaml.load(open(configfile).read(), Loader=yaml.Loader)
    config      = {}

    for key, item in core_config.items():
        if isinstance(item, dict):
            for k2, i2 in item.items():
                config['{}_{}'.format(key, k2)] = i2
        else:
            config[key] = item

    if verbose:
        print(header.format(logo=logo, variant=variant, configfile=configfile))
        for key, item in core_config.items():
            if isinstance(item, dict):
                print(f'{key}:')
                for k2, i2 in item.items():
                    if k2 in ('reset_address', 'start', 'end'):
                        print(f'- {k2}: {hex(i2)}')
                    else:
                        print(f'- {k2}: {i2}')
            else:
                print(f'{key}: {item}')
        print('--------------------------------------------------')

    return config
