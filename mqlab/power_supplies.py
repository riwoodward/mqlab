""" Definition of power supply interfacing commands. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import time
from mqlab.connections import Instrument


class PowerSupply(Instrument):

    def __init__(self, max_current_A=1000, **kwargs):
        """ Init for power supply including a safety routine to limit accidental setting of erroneously high currents. """

        # Store current limit
        self.max_current_A = max_current_A

        # Init main MQ instrument class
        super().__init__(**kwargs)


class HP6653A(PowerSupply):
    """ Interfacing code for HP6653A power supply. """

    def set_current(self, current):
        """ Set the current limit to the user specified current (A) maintaining all other settings. """
        if current > self.max_current_A:
            raise ValueError('Entered current value [{} A] is above the device max current limit [{} A]. Check input and raise the current limit when initialising the device connection if needed.'.format(current, self.max_current_A))
        else:
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


class Newport5600(PowerSupply):
    """ Interfacing code for Newport 5600 diode driver. """

    def set_current(self, current):
        """ Set the current limit to the user specified current (A) maintaining all other settings. """
        if current > self.max_current_A:
            raise ValueError('Entered current value [{} A] is above the device max current limit [{} A]. Check input and raise the current limit when initialising the device connection if needed.'.format(current, self.max_current_A))
        else:
            self.send('LASer:LDI {:.3f}'.format(current))

    def set_voltage(self, voltage):
        """ Set the voltage limit to the user specified voltage (V) maintaining all other settings. """
        self.send('LASer:LDV {:.3f}'.format(voltage))

    def get_current(self):
        """ Return current [A]. """
        return self.query('LASer:LDI?', dtype=float)

    def get_voltage(self):
        """ Return voltage [V]. """
        return self.query('LASer:LDV?', dtype=float)

    def set_output_off(self):
        """ Disable output. """
        self.send('LASer:OUTput 0')

    def set_output_on(self):
        """ Enable output. """
        self.send('LASer:OUTput 1')

    def current_kick(self, low_value, high_value, delay=1):
        """ Set current to low value for a given delay, then jump back up to high value - useful for kick-starting mode-locking! """
        self.set_current(low_value)
        time.sleep(delay)
        self.set_current(high_value)

    def multiple_current_kicks(self, low_value, high_values, delay=1, delay_between_kicks=5):
        for high_value in high_values:
            self.set_current(low_value)
            time.sleep(delay)
            print('{:.2f} A'.format(high_value))
            self.set_current(high_value)
            time.sleep(delay_between_kicks)

    # Create virtual entities for current and votlage so they can be simply accessed as variables (e.g. self.current=1) rather than using setters / getters
    current = property(get_current, set_current)
    voltage = property(get_voltage, set_voltage)
