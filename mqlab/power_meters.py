""" Definition of power meter interfacing commands. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import numpy as np

from mqlab.connections import Instrument


class PowerMeter(Instrument):
    pass


class ThorlabsPM100(PowerMeter):
    """ Interface for communication with ThorLabs Power Meters over USB.

    TODO: check. Notes:
        Drivers must be installed before use (see ThorLabs website).
    """

    def get_power(self):
        """ Read current power (W) displayed on device. """
        return self.query('READ?', dtype=float)

    def set_autoranging_on(self):
        """ Enable autoranging. """
        self.send(':CURR:RANG:AUTO 1')

    def set_autoranging_off(self):
        """ Disable autoranging. """
        self.send(':CURR:RANG:AUTO 0')


class Newport842PE(PowerMeter):
    """ Control interface for CVI Digikrom CM112 1/8m double monochromator. """
    # Device requires hexcode interfacing. We use struct module for packing/unpacking bytes objects: '>' indicates big endian convention, 'B' = unsigned one-byte character, 'H' = unsigned two-byte character

    def __init__(self, com_port):
        """ Initialise serial connection, but modify the initialisation command to set the correct default connection properties. """
        super().__init__(interface='serial', com_port=com_port, baud_rate=115200, terminating_char='\r')

    def get_power(self):
        """ Read current power (W) displayed on device. """
        # There seems to be an unreliabilty in this call, thus we return nan if no value obtained.
        try:
            response = self.query('*CVU')
            # Remove acknoweldgement text and return just the value
            value_str = response.decode().split(' ')[-1]
            value = float(value_str)
        except ValueError:
            value = np.nan
        return value
