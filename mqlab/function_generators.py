""" Definition of function generator interfacing commands. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import subprocess

from mqlab.connections import Instrument


class TektronixAFG3022C(Instrument):

    def get_frequency(self):
        """ Return current frequency [Hz] of currently active channel. """
        return self.query('FREQ?', dtype=float)

    def set_frequency(self, frequency):
        """ Set frequency [Hz] of current channel. """
        self.send('FREQ {}'.format(frequency))

    def get_amplitude(self):
        """ Return current amplitude [Vpp] of currently active channel. """
        return self.query('VOLT?', dtype=float)

    def set_amplitude(self, amplitude):
        """ Set amplitude [Vpp] of current channel. """
        self.send('VOLT {}'.format(amplitude))

    def set_output_off(self):
        """ Turn channel 1 output off. """
        self.send('OUTP1:STATe 0')

    def set_output_on(self):
        """ Turn channel 1 output off. """
        self.send('OUTP1:STATe 1')


class GoochHousegoAOTFDriver(object):
    """ Communication with Gooch & Housego AOTF (drivers from G&H must be installed first).

    Notes:
        G&H provide an AOTFlibrary DLL file which is 32 bit and doesn't seem to permit communication using ctypes interfacing (even when using 32-bit Python).
        Therefore, as an alternative, use the provided AOTFcmd command line app for communication.
    """

    def __init__(self, aotfcmd_exe_path='"C:\\Program Files\\Crystal Technology\\AotfCmd\\AotfCmd.exe"'):
        self.cmd_path = aotfcmd_exe_path

    def query(self, command):
        # Put comman within double quotes: the required format by AOTF
        msg = '{} "{}"'.format(self.cmd_path, command)
        process = subprocess.run(msg, stdout=subprocess.PIPE)
        return process.stdout

    def get_optical_reading(self):
        response = self.query('adc read 2')
        return response
