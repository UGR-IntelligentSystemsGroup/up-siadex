#!/usr/bin/env python3

import platform

from setuptools import setup  # type: ignore

import up_siadex

arch = (platform.system(), platform.machine())

EXECUTABLES = {
    ("Linux", "x86_64"): "planner",
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
    author="UGR",
    author_email="jorgesoler@ugr.es,ignaciove@ugr.es",
    packages=["up_lpg"],
    package_data={"": [executable]},
    include_package_data=True,
    license="APACHE",
)
