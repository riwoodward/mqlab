""" Definition of optical spectrum analyser interfacing commands. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import numpy as np

from mqlab.connections import Instrument


class OpticalSpectrumAnalyser(Instrument):
    pass


class YokogawaAQ6376(OpticalSpectrumAnalyser):

    def __init__(self, **kwargs):
        """ Instantiate YokogawaAQ6376 communication. """
        super().__init__(**kwargs)
        # As user login is required for ethernet, this first instantiates a general instrument class (see Instrument definition for kwargs explanation)
        # then opens the socket connection to perform the login step.
        if self._interface == 'ethernet':
            self.authenticate()

    def authenticate(self):
        """ Log into the device to initiate remote connection. """
        self.connection.open_socket()
        response = self.query('OPEN "anonymous"')  # Defaults to anonymous user
        response = self.query('', dtype=str)                  # Defaults to no password
        if response != 'ready':
            raise Exception('Connection Error: User authentication failed. Check username/password and retry.')

    def sweep(self):
        """ Run a single sweep. """
        self.send(':init:smode 1; :init')

    def repeat_sweep(self):
        """ Run repeat sweeps. """
        self.send(':init:smode 2; :init')

    def stop_sweep(self):
        """ Abort current sweep(s). """
        self.send(':abort')

    def grab(self, channel='A'):
        """ Return wls [m] and spectral intensities [dBm] data for chosen channel. """
        # Read and format wls data
        # (also ensuring that 64-bit floating point data transfer format is selected for speed)
        data = self.query(':format:data real,64; :trace:data:x? TR%c' % channel)
        wls = self._decode_binary_block(data, 'float64')
        # Read and format spectral intensities
        data = self.query(':trace:data:y? TR%c' % channel)
        its = self._decode_binary_block(data, 'float64')
        return wls, its


class AndoAQ6317B(OpticalSpectrumAnalyser):

    def sweep(self):
        """ Run a single sweep. """
        self.send('SGL')

    def repeat_sweep_start(self):
        """ Sweep repeatedly until manually stopped. """
        self.send('RPT')

    def repeat_sweep_stop(self):
        """ Stop repeatedly sweeping. """
        self.send('STP')

    def grab(self, channel='A'):
        """ Return wls [m] and spectral intensities [dBm] data for chosen channel. """
        if channel not in ('A', 'B', 'C'):
            raise ValueError("Channel must be 'A' or 'B' or 'C'")

        # Set number of decimal digits to 3 for level data (highest accuracy setting)
        self.send('LDTDIG3')

        # Get wavelength data (only ASCII transfer supported)
        data = self.query('WDAT{}'.format(channel), dtype=str)
        wls = 1e-9 * np.array([float(x) for x in data.split(',')[1:]])  # Ignore first value in dataset, which indicates dataset length

        # Get intensities data
        data = self.query('LDAT{}'.format(channel), dtype=str)
        its = np.array([float(x) for x in data.split(',')[1:]])  # Ignore first value in dataset, which indicates dataset length
        its = np.clip(its, -90, 1e3)  # Clip off spuriously low values that sometimes appear as artefacts
        return wls, its