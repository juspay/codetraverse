import os
from setuptools import setup, find_packages

# locate files relative to this setup.py
HERE = os.path.abspath(os.path.dirname(__file__))


def parse_requirements(rel_path):
    path = os.path.join(HERE, rel_path)
    with open(path, "r") as f:
        lines = f.read().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


setup(
    name="codetraverse",
    version="0.1.0",
    author="Juspay",
    author_email="opensource@juspay.in",
    description="Multi-language static code analyzer using Tree-sitter",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/juspay/codetraverse",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=parse_requirements("codetraverse/requirements.txt"),
    entry_points={
        "console_scripts": [
            "codetraverse=codetraverse.main:main",
        ],
    },
    include_package_data=True,
)
