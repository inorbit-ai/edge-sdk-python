#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import find_packages, setup

with open("README.md") as readme_file:
    readme = readme_file.read()

setup_requirements = [
    "pytest-runner>=5.2",
]

test_requirements = [
    "black>=19.10b0",
    "codecov>=2.1.4",
    "flake8>=3.8.3",
    "flake8-debugger>=3.2.1",
    "pytest>=5.4.3",
    "pytest-cov>=2.9.0",
    "pytest-mock>=3.10.0",
    "pytest-raises>=0.11",
    "pyyaml>=6.0",
    "lark>=1.0.0",
    "requests_mock>=1.9.3",
]

dev_requirements = [
    *setup_requirements,
    *test_requirements,
    "bump2version>=1.0.1",
    "coverage>=5.1",
    "ipython>=7.15.0",
    "m2r2>=0.2.7",
    "pytest-runner>=5.2",
    "Sphinx>=3.4.3",
    "sphinx_rtd_theme>=0.5.1",
    "tox>=3.15.2",
    "twine>=3.1.1",
    "wheel>=0.34.2",
]

requirements = [
    "requests==2.26.0",
    "paho_mqtt==1.6.1",
    "PySocks==1.7.1",
    "protobuf==3.19.3",
    "certifi>=2021.10.8",
    "deprecated==1.2.13"
]

extra_requirements = {
    "setup": setup_requirements,
    "test": test_requirements,
    "dev": dev_requirements,
    "video": ["opencv-python==4.7.0.68"],
    "all": [
        *requirements,
        *dev_requirements,
    ]
}

setup(
    author="InOrbit",
    author_email="support@inorbit.ai",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    description="InOrbit Python Edge SDK",
    install_requires=requirements,
    long_description=readme,
    long_description_content_type="text/markdown",
    include_package_data=True,
    keywords="inorbit_edge",
    name="inorbit_edge",
    packages=find_packages(exclude=["tests", "*.tests", "*.tests.*"]),
    python_requires=">=3.7",
    setup_requires=setup_requirements,
    test_suite="inorbit_edge/tests",
    tests_require=test_requirements,
    extras_require=extra_requirements,
    url="https://github.com/inorbit-ai/edge-sdk-python",
    # Do not edit this string manually, always use bumpversion
    # Details in CONTRIBUTING.rst
    version="1.8.0",
    zip_safe=False,
)
