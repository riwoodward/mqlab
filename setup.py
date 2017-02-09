""" Setup script for MQ Mid-IR Photonics Group lab control software.

Usage:
  - cd into this directory and execute: "python setup.py develop"
"""

from setuptools import setup


def readme():
    with open('README.rst') as f:
        return f.read()


setup(name='MQ Lab Control',
      version='0.1',
      description='Instrument control code for MQ Mid-IR Photonics Group lab devices.',
      long_description=readme(),
      url='https://bitbucket.org/tbc',
      author='Robert I. Woodward',
      author_email='r.i.woodward@gmail.com',
      packages=[],
      # Define dependencies
      install_requires=[
          'scipy',
          'numpy',
          'matplotlib',
          'pyserial',
          'matplotlib',
          'python-vxi11',
          'future',
      ],
      zip_safe=False)
