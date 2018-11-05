""" Definition of electrical spectrum analyser interfacing commands. """
import numpy as np

from mqlab.connections import Instrument


class ElectricalSpectrumAnalyser(Instrument):
    pass


class AnritsuMS2683A(ElectricalSpectrumAnalyser):

    def sweep(self):
        """ Run a single sweep. """
        self.send('TS')

    def grab(self):
        """ Return freqs [Hz] and spectral intensities [dBm] data currently displayed on device. """
        # Grab & decode binary data, which is returned in big-endian 2-byte (16-bit) integer format
        # The values are integer values of 0.01 dBm units (log scale assumed)
        data = self.query('BIN 1;XMA? 0,1001')  # Set to binary data transfer mode and request y data
        intensities_arb_units = self._decode_binary_block(data, dtype='>i2')
        intensities_dBm = 0.01 * intensities_arb_units

        # Rebuild freqs axis based on centre freq and span
        # Queries return a label, space, then the data, so extract just the number of using ".split(' ')"
        centre_freq_response = self.query('CNF?', dtype=str)
        centre_freq = float(centre_freq_response.split(' ')[1])
        span_response = self.query('SPF?', dtype=str)
        span = float(span_response.split(' ')[1])
        freqs = (centre_freq + np.linspace(-span * 0.5, span * 0.5, intensities_dBm.size))
        return freqs, intensities_dBm
