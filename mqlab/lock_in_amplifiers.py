""" Definition of lock-in amplifier interfacing commands. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import time
import numpy as np

from mqlab.connections import Instrument


class LockInAmplifier(Instrument):
    pass


class SR830(LockInAmplifier):

    # List of sensitivites (interfacing with lock-in uses only the index to refer to a given sensitivity: SENSITIVITIES[1] = 5 nV)
    SENSITIVITIES = np.array([
        2e-9, 5e-9, 10e-9, 20e-9, 50e-9, 100e-9, 200e-9,
        500e-9, 1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6, 100e-6,
        200e-6, 500e-6, 1e-3, 2e-3, 5e-3, 10e-3, 20e-3,
        50e-3, 100e-3, 200e-3, 500e-3, 1
    ])

    TIME_CONSTANTS = np.array([
        10e-6, 30e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3,
        30e-3, 100e-3, 300e-3, 1, 3, 10, 100, 300, 1e3,
        3e3, 10e3, 30e3
    ])

    RESERVE_VALUES = ['High Reserve', 'Normal', 'Low Noise']

    def __init__(self, sensitivity_min_idx=5, manual_autorange_settle_time='auto', silent=True, **kwargs):
        """ Instantiate SR830 communication.

        Args:
            sensitivity_min : index of minimum sensitivity value (see below for voltage this corresponds to) [0-26 where 0 is most sensitive]
            manual_autorange_settle_time : if using our auto autoranging func, this sets delay before reading voltage again after changing the sensitivity
        """
        super().__init__(**kwargs)

        # If manual autorange settle not specified, just use two time constants
        if manual_autorange_settle_time == 'auto':
            self.manual_autorange_settle_time = self.get_time_constant() * 2
        else:
            self.manual_autorange_settle_time = manual_autorange_settle_time

        self.sensitivity_min_idx = sensitivity_min_idx
        self.silent = silent  # For outputting information to aid debugging

        # For quick access to sensitivities, we save the current index value to the class. Thus, need to query device when first connecting.
        self.sensitivity_idx = self.get_sensitivity(return_idx=True)

    def get_idn(self):
        """ Return make, model, firmware etc. to test connection. """
        return self.query('*IDN?', dtype=str)

    def get_x_voltage(self):
        """ Return voltage X [V].

        Notes:
            If wanting to read multiple values at once, simultaneously, use the SNAP command (see: 5-15 of the manual)
        """
        return self.query('OUTP?1', dtype=float)

    def get_y_voltage(self):
        """ Return voltage Y [V]. """
        return self.query('OUTP?2', dtype=float)

    def get_ref_freq(self):
        """ Return reference frequency [Hz]. """
        return self.query('FREQ?', dtype=float)

    def get_ref_phase(self):
        """ Return reference phase shift [deg]. """
        return self.query('PHAS?', dtype=float)

    def get_sensitivity(self, return_idx=False):
        """ Return sensitivity setting [V] or the index value is return_idx is True. """
        sensitivity_idx = self.query('SENS?', dtype=int)
        if return_idx:
            return sensitivity_idx
        else:
            return self.SENSITIVITIES[sensitivity_idx]

    def get_time_constant(self, return_idx=False):
        """ Return time constant [s] or the index value is return_idx is True. """
        time_constant_idx = self.query('OFLT?', dtype=int)
        if return_idx:
            return time_constant_idx
        else:
            return self.TIME_CONSTANTS[time_constant_idx]

    def get_reserve_mode(self):
        """ Returns the reserve mode option: 'High Reserve', 'Normal' or 'Low Noise'. """
        reserve_idx = self.query('RMOD?', dtype=int)
        return self.RESERVE_VALUES[reserve_idx]

    def auto_gain(self):
        """ Run auto gain function. """
        self.send('AGAN')

    def auto_reserve(self):
        """ Run auto reserve function. """
        self.send('ARSV')

    def auto_phase(self):
        """ Run auto phase function. """
        self.send('APHS')

    def set_sensitivity(self, idx):
        """ Set sensitivity using the index value (see table for corresponding voltage). """
        self.send('SENS{}'.format(idx))
        self.sensitivity_idx = idx

    def set_time_constant(self, idx):
        """ Set time constant using the index value (see table for corresponding voltage). """
        self.send('OFLT{}'.format(idx))
        self.sensitivity_idx = idx

    def get_x_voltage_with_manual_autoranging(self):
        """ Read X voltage on device, including our own "fast autoranging" function to optimise sensitivity and avoid overload. """
        acceptable_reading = False

        while not acceptable_reading:
            sensitivity_volts = self.SENSITIVITIES[self.sensitivity_idx]
            voltage = self.get_x_voltage()

            # If overloaded
            if voltage > (1.09 * sensitivity_volts):
                if not self.silent: print('Overload (sens %s = %0.2e, volts = %0.2e)...' % (self.sensitivity_idx, sensitivity_volts, voltage))
                if self.sensitivity_idx == 26:
                    print('Warning, max possible range (i.e. sensitivity) exceeded. Reduce signal level.')
                else:
                    self.set_sensitivity(self.sensitivity_idx + 5)  # ... decrease sensitivity to next value (edit: jump 5 for speed)
                    if not self.silent: print('Fix is: S %s = %0.2e' % (self.sensitivity_idx, self.SENSITIVITIES[self.sensitivity_idx]))
                    time.sleep(self.manual_autorange_settle_time)  # Let device settle with new sensitivity setting

            # If underloaded (i.e. signal less than sensitivity of the next possible sensitivity bin), but not at min sensitivity
            elif ((voltage < self.SENSITIVITIES[self.sensitivity_idx - 1]) and (self.sensitivity_idx > self.sensitivity_min_idx)):
                if not self.silent: print('Underload (sens %s = %0.2e, volts = %0.2e)...' % (self.sensitivity_idx, sensitivity_volts, voltage))
                # Find the sensitivity value which is just above the measured signal
                sensitivity_idx = np.where(self.SENSITIVITIES > voltage)[0][0]
                sensitivity_idx = max(sensitivity_idx, self.sensitivity_min_idx)  # Don't let it go below the minimum sensitivity
                self.set_sensitivity(sensitivity_idx)
                if not self.silent: print('Fix is: S %s = %0.2e' % (self.sensitivity_idx, self.SENSITIVITIES[self.sensitivity_idx]))
                time.sleep(self.manual_autorange_settle_time)  # # Let device settle with new sensitivity setting

            # If no over/underloading, then return the value
            else:
                acceptable_reading = True

        return voltage
