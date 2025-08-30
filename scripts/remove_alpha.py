#!/usr/bin/env python3
"""
Remove alpha version marker for release preparation
"""

import fileinput
from os.path import join, dirname


def remove_alpha():
    """Remove alpha version marker from version.py"""
    version_file = join(dirname(dirname(__file__)), "version.py")
    alpha_var_name = "VERSION_ALPHA"

    print(f"Removing alpha version from {version_file}")
    
    for line in fileinput.input(version_file, inplace=True):
        if line.startswith(alpha_var_name):
            print(f"{alpha_var_name} = 0")
        else:
            print(line.rstrip("\n"))
    
    print("Alpha version removed successfully")


if __name__ == "__main__":
    remove_alpha()