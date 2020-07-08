from notion import __version__
from setuptools import setup, find_packages

with open("README.md") as file:
    long_description = file.read()

with open("requirements.txt") as file:
    r = file.read().split("\n")
    r = map(lambda l: l.strip(), filter(len, r))
    r = filter(lambda l: not l.startswith("-"), r)
    r = filter(lambda l: not l.startswith("#"), r)
    install_requires = list(r)

setup(
    name="notion-py",
    version=__version__,
    author="Artur Tamborski",
    author_email="tamborskiartur@gmail.com",
    description="(Fork of) Unofficial Python API client for Notion.so",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/arturtamborski/notion-py",
    install_requires=install_requires,
    include_package_data=True,
    packages=find_packages(),
    python_requires=">=3.6",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
