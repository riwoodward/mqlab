""" Definition of power supply interfacing commands. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

from mqlab.connections import Instrument


class PowerSupply(Instrument):
    pass


class HP6653A(PowerSupply):
    """ Interfacing code for HP6653A power supply. """

    def set_current(self, current):
        """ Set the current limit to the user specified current (A) maintaining all other settings. """
        self.send('CURR {:.3f}'.format(current))

    def set_voltage(self, voltage):
        """ Set the voltage limit to the user specified voltage (V) maintaining all other settings. """
        self.send('VOLT {:.3f}'.format(voltage))

    def get_current(self):
        """ Return current [A]. """
        return float(self.query('CURR?'))

    def get_voltage(self):
        """ Return voltage [V]. """
        return float(self.query('VOLT?'))

    def set_output_off(self):
        """ Disable output. """
        self.send('OUTP OFF')

    def set_output_on(self):
        """ Enable output. """
        self.send('OUTP ON')
