#!/usr/bin/env python3

import platform
import subprocess
from setuptools import setup  # type: ignore

arch = (platform.system(), platform.machine())

long_description=\
'''
 ============================================================
    UP-SIADEX
 ============================================================
    up-siadex is a small package that allows an exchange of
    equivalent data structures between unified_planning and SIADEX.
'''

EXECUTABLES = {
    ("Linux", "x86_64"): "bin/planner",
    # ("Windows", "x86_64"): "aries_windows_x86_64.exe",
    # ("Windows", "aarch64"): "aries_windows_aarch64.exe",
    # ("Windows", "x86"): "aries_windows_x86.exe",
    # ("Windows", "aarch32"): "aries_windows_aarch32.exe",
}

executable = EXECUTABLES[arch]

setup(
    name="up_siadex",
    version="0.0.1",
    description="up_siadex",
    long_description=long_description,
    author="UGR Intelligent Systems Group",
    author_email="jorgesoler@ugr.es,ignaciovellido@ugr.es",
    packages=["up_siadex"],
    package_data={"": [executable]},
    include_package_data=True,
    license="APACHE",
)
