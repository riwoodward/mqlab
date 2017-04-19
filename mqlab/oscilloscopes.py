""" Definition of oscilloscope interfacing commands. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import numpy as np

from mqlab.connections import Instrument


class Oscilloscope(Instrument):
    pass


class HP54616C(Oscilloscope):

    def grab(self, channel='1'):
        """ Return times [s] and amplitudes [V] data currently displayed on device. """
        if channel not in ('1', '2'):
            raise ValueError("Trace must be '1' or '2'")

        # Read preamble data
        data = self.query(':WAV:SOUR CHAN{};PRE?'.format(channel), dtype=str)
        preamble = data.split(',')

        # Converts the necessary preamble values from strings into numbers
        numdatapoints = int(preamble[2])  # The number of data points
        xincr = float(preamble[4])  # The x increment
        xoffset = float(preamble[5])  # The x offset (left side of screen)
        yincr = float(preamble[7])  # The y increment
        yzero = float(preamble[8])  # The y offset
        yoffset = float(preamble[9])  # The y value at the origin

        # Read trace data (returned in 1 byte integer format, then scaled appropriately)
        data_block = self.query(':WAV:SOUR CHAN{};FORM BYTE;DATA?'.format(channel))
        data = self._decode_binary_block(data_block, dtype='uint8')

        # Finally, scale the y values to repesent actual voltage and rebuild timebase
        ys = ((data - yoffset) * yincr) + yzero
        tms = xoffset + (np.arange(1, numdatapoints + 1, 1) * xincr)
        return tms, ys
