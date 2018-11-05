""" Setup script for MQ Mid-IR Photonics Group lab control software.

Usage:
    'cd' into this directory and execute:
        "python setup.py install" [for a simple install to python site-packages folder]
        "python setup.py develop" [for an active development environment]
"""

from setuptools import setup


def readme():
    with open('README.md') as f:
        return f.read()


setup(
    name='mqlab',
    version='0.2',
    description='Instrument control code for MQ Mid-IR Fibre Lasers Group.',
    long_description=readme(),
    url='https://github.com/riwoodward/mqlab',
    author='Robert I. Woodward',
    author_email='r.i.woodward@gmail.com',
    packages=[],
    # Define dependencies
    install_requires=[
        'numpy',
        'scipy',
        'matplotlib',
        'pyserial',
        'python-vxi11',
        'pyvisa',
        'zaber.serial',
        # 'ftd2xx',  # required for ThorLabs rotation mount, but manual install often required
    ],
    zip_safe=False
)
