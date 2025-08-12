"""
Celestial Tracker - Autonomous Satellite Tracking for Celestron Origin
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="celestial-tracker",
    version="1.0.0",
    author="Celestial Tracker Contributors",
    description="Autonomous satellite tracking system for Celestron Origin telescope",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/celestial-tracker",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Astronomy",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "celestial-tracker=main_tracker:main",
            "celestial-dashboard=dashboard_server:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["templates/*.html", "static/*", "*.sample"],
    },
)
