from setuptools import setup, find_packages

setup(
    name="videolingo_tool",
    version="1.0.0",
    description="VideoLingo Architecture implementation for Video Processing",
    packages=find_packages(),
    install_requires=[], # Dependencies handled via install.py and requirements.txt
    python_requires=">=3.9",
)
