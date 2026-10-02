#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name="mv-query-optimization",
    version="0.1.0",
    packages=find_packages(where=".", include=["src*"]),
    python_requires=">=3.10",
)
