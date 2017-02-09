""" Definition of electrical spectrum analyser interfacing commands. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import numpy as np

from mqlab.connections import Instrument


class ElectricalSpectrumAnalyser(Instrument):
    pass


class AnritsuMS2683A(ElectricalSpectrumAnalyser):

    def sweep(self):
        """ Run a single sweep. """
        self.connection.send('TS')

    def grab(self):
        """ Return freqs [Hz] and spectral intensities [dBm] data currently displayed on device. """
        # Grab & decode binary data, which is returned in bin-endian 2-byte (16-bit) integer format
        # The values are integer values of 0.01 dBm units (log scale assumed)
        data = self.connection.query('BIN 1;XMA? 0,501')  # Set to binary data transfer mode and request y data
        intensities_arb_units = self._decode_binary_block(data, dtype='>i2')
        intensities_dBm = 0.01 * intensities_arb_units

        # Rebuild freqs axis based on centre freq and span
        # Queries return a label, space, then the data, so extract just the number of using ".split(' ')"
        centre_freq_response = self.connection.query('CNF?', decode_as_string=True)
        centre_freq = float(centre_freq_response.split(' ')[1])
        span_response = self.connection.query('SPF?', decode_as_string=True)
        span = float(span_response.split(' ')[1])
        freqs = (centre_freq + np.linspace(-span * 0.5, span * 0.5, intensities_dBm.size))
        return freqs, intensities_dBm
