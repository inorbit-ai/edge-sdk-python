#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

import os

from setuptools import find_packages, setup

# Do not edit manually, always use bumpversion (see CONTRIBUTING.rst)
VERSION = "1.19.0"

GITHUB_ORG = "https://github.com/inorbit-ai"
GITHUB_REPO = f"{GITHUB_ORG}/edge-sdk-python"
YOUTRACK_URL = "https://inorbit.youtrack.cloud"
YOUTRACK_KEY = "ESP"
YOUTRACK_OPEN = "State:%20-Resolved%20"

with open("README.md") as readme_file:
    long_description = readme_file.read()

# Load from the requirements-*.txt files where '*' is anything extra
requirements = {key: [] for key in ["install", "video"]}
base_path = os.path.dirname(os.path.abspath(__file__))
for key in requirements:
    fname = os.path.join(
        base_path, "requirements.txt" if key == "install" else f"requirements-{key}.txt"
    )
    with open(fname, "r") as file:
        requirements[key] = file.read().splitlines()

setup(
    author="InOrbit, Inc.",
    author_email="support@inorbit.ai",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    description="InOrbit Edge SDK for Python",
    # Do not edit manually, always use bumpversion (see CONTRIBUTING.rst)
    download_url=f"{GITHUB_REPO}/archive/refs/tags/v1.13.0.zip",
    extras_require={
        "video": requirements["video"],
    },
    install_requires=requirements["install"],
    keywords=["inorbit", "robops", "robotics"],
    license="MIT",
    license_files=["LICENSE"],
    long_description=long_description,
    long_description_content_type="text/markdown",
    maintainer="Leandro Pineda",
    maintainer_email="leandro@inorbit.ai",
    name="inorbit-edge",
    # TODO(russell): move to src/test directories
    #  packages=find_packages(where="src"),
    #  package_dir={"": "src"},
    packages=find_packages(exclude=["tests", "*.tests", "*.tests.*"]),
    platforms=["Linux", "Mac OS-X", "Windows"],
    python_requires=">=3.8, <3.13",
    url=GITHUB_REPO,
    # Do not edit manually, always use bumpversion (see CONTRIBUTING.rst)
    version=VERSION,
    project_urls={
        "CI/CD": "https://inorbit.teamcity.com/project/"
        "Engineering_Development_DeveloperPortal_EdgeSdkPython",
        "Tracker": f"{YOUTRACK_URL}/issues/{YOUTRACK_KEY}/?q={YOUTRACK_OPEN}",
        "Contributing": f"{GITHUB_REPO}/blob/v{VERSION}/CONTRIBUTING.md",
        "Code of Conduct": f"{GITHUB_REPO}/blob/v{VERSION}/CODE_OF_CONDUCT.md",
        "Changelog": f"{GITHUB_REPO}/blob/v{VERSION}/CHANGELOG.md",
        "Issue Tracker": f"{GITHUB_REPO}/issues",
        "License": f"{GITHUB_REPO}/blob/n{VERSION}/LICENSE",
        "About": "https://www.inorbit.ai/company",
        "Contact": "https://www.inorbit.ai/contact",
        "Blog": "https://www.inorbit.ai/blog",
        "Twitter": "https://twitter.com/InOrbitAI",
        "LinkedIn": "https://www.linkedin.com/company/inorbitai",
        "GitHub": GITHUB_ORG,
        "Website": "https://www.inorbit.ai/",
        "Source": GITHUB_REPO,
    },
)
