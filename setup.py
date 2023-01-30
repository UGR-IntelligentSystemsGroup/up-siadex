#!/usr/bin/env python3

import platform
import subprocess
from setuptools import setup  # type: ignore

arch = (platform.system(), platform.machine())

# Read long_description from repo README
with open("README.md", "r") as fh:
    long_description = fh.read()

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
    long_description_content_type="text/markdown",
    url='https://github.com/UGR-IntelligentSystemsGroup/up-siadex',
    author="UGR Intelligent Systems Group",
    author_email="jorgesoler@ugr.es,ignaciovellido@ugr.es",
    packages=["up_siadex"],
    package_data={"": [executable]},
    include_package_data=True,
    license="APACHE",
)
