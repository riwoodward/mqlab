""" Definition of power meter interfacing commands. """
import numpy as np

from mqlab.connections import Instrument


class PowerMeter(Instrument):
    pass


class ThorlabsPM100(PowerMeter):
    """ Interface for communication with ThorLabs Power Meters over USB.

    Notes:
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
    """ Control interface for Newport 842PE power meter. """

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
