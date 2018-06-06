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


class TektronixTDS794D(Oscilloscope):

    def grab(self, channel='1'):
        """ Return times [s] and amplitudes [V] data currently displayed on device. """
        if channel not in ('1', '2', '3', '4'):
            raise ValueError("Trace must be '1', '2', '3', or '4'")

        # Select chosen waveform channel, 16-bit (2 byte) per data point, and binary data format (signed integer, MSB sent first)
        self.send('DATa:SOUrce CH{};:DATa:WIDth 2;:DATA:ENCdg RIBinary'.format(channel))

        # Get preamble and data in one command (equivalent to self.query('CURVE?'), followed by self.query('WFMPRe?', dtype=str))
        preamble_and_data = self.query('WAVFrm?')
        preamble, data = preamble_and_data.split(b';:CURV ')

        # Decode preamble (according to Tektronix programming manual - we use their variable names here)
        # When using WAVFrm command, the preamble includes labels of each value, so strip these off to obtain just the values
        preamble = preamble.decode()  # Byte -> string conversion
        preamble_items = preamble.split(':WFMP:')[-1].split(';')
        BYT_Nr, BIT_Nr, ENCdg, BN_Fmt, BYT_Or, WFID, NR_Pt, PT_FMT, XUNit, XINcr, XZEro, PT_Off, Y_UNit, YMUlt, YOFf, YZEro = [item.split(' ')[-1] for item in preamble_items]
        tms = np.arange(int(NR_Pt)) * float(XINcr) + float(XZEro)

        # Convert data in arb units to volts
        intensities_arb_units = self._decode_binary_block(data, dtype='>i2')
        ys = float(YMUlt) * (intensities_arb_units.astype(np.float) - float(YOFf)) + float(YZEro)

        return tms, ys


class TektronixTDS2012B(Oscilloscope):
    """ Tektronix TDS2012B oscilloscope.

    The interfacing is similar to the Tektronix TDS794D, but seemingly subtly different wrt. the WAVFrm command, hence needing to fire preamble and curve commands separately. """

    def grab(self, channel='1'):
        """ Return times [s] and amplitudes [V] data currently displayed on device. """
        if channel not in ('1', '2'):
            raise ValueError("Trace must be '1' or '2'")

        # Select chosen waveform channel, 16-bit (2 byte) per data point, and binary data format (signed integer, MSB sent first)
        self.send('DATa:SOUrce CH{};:DATa:WIDth 2;:DATA:ENCdg RIBinary'.format(channel))

        # Get preamble and data
        preamble = self.query('WFMPRe?')
        data = self.query('CURVE?')

        # Decode preamble (according to Tektronix programming manual - we use their variable names here)
        # When using WAVFrm command, the preamble includes labels of each value, so strip these off to obtain just the values
        preamble = preamble.decode()  # Byte -> string conversion
        preamble_items = preamble.split(':WFMP:')[-1].split(';')
        BYT_Nr, BIT_Nr, ENCdg, BN_Fmt, BYT_Or, NR_Pt, WFID, PT_FMT, XINcr, PT_Off, XZEro, XUNit, YMUlt, YZEro, YOFf, YUNit = [item.split(' ')[-1] for item in preamble_items]
        tms = np.arange(int(NR_Pt)) * float(XINcr) + float(XZEro)

        # Convert data in arb units to volts
        intensities_arb_units = self._decode_binary_block(data, dtype='>i2')
        ys = float(YMUlt) * (intensities_arb_units.astype(np.float) - float(YOFf)) + float(YZEro)

        return tms, ys
