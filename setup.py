""" Setup script for MQ Mid-IR Photonics Group lab control software.

Usage:
    'cd' into this directory and execute:
        "python setup.py install" [for a simple install to python site-packages folder]
        "python setup.py develop" [for an active development environment]
"""

from setuptools import setup


def readme():
    with open('README.rst') as f:
        return f.read()


setup(name='mqlab',
      version='0.1',
      description='Instrument control code for MQ Mid-IR Photonics Group lab devices.',
      long_description=readme(),
      url='https://github.com/riwoodward/mqlab',
      author='Robert I. Woodward',
      author_email='r.i.woodward@gmail.com',
      packages=[],
      # Define dependencies
      install_requires=[
          'future',
          'numpy',
          'scipy',
          'matplotlib',
          'pyserial',
          'python-vxi11',
          'pyvisa',
      ],
      zip_safe=False)
