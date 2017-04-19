""" Definition of power meter interfacing commands. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

from mqlab.connections import Instrument


class PowerMeter(Instrument):
    pass


class ThorlabsPM100A(PowerMeter):
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
