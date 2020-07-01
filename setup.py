import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()


def get_requirements(fname):
    "Takes requirements from requirements.txt and returns a list."
    with open(fname) as fp:
        reqs = list()
        for lib in fp.read().split("\n"):
            # Ignore pypi flags and comments
            if not lib.startswith("-") or lib.startswith("#"):
                reqs.append(lib.strip())
        return reqs


install_requires = get_requirements("requirements.txt")

setuptools.setup(
    name="notion-py",
    version="0.0.1",
    author="Artur Tamborski",
    author_email="tamborskiartur@gmail.com",
    description="(Fork of) Unofficial Python API client for Notion.so",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/arturtamborski/notion-py",
    install_requires=install_requires,
    include_package_data=True,
    packages=setuptools.find_packages(),
    python_requires=">=3.6",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
