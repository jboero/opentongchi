#!/usr/bin/env python3
"""
Setup script for OpenTongchi
"""

from setuptools import setup, find_packages

setup(
    name="opentongchi",
    version="0.2.0",
    description="System Tray Manager for Open Source Infrastructure Tools",
    author="OpenTongchi Contributors",
    license="MPL-2.0",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[
        "PySide6>=6.5.0",
    ],
    entry_points={
        "console_scripts": [
            "opentongchi=main:main",
        ],
        "gui_scripts": [
            "opentongchi-gui=main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: X11 Applications :: Qt",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Systems Administration",
    ],
)
