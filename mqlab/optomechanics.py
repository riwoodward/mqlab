""" Definition of automated optomechanics interfaces. NOT FINISHED OR TESTED. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import time
import operator
import numpy as np

import mqlab.utils as ut
from mqlab.connections import Instrument

import ftd2xx
from ftd2xx.defines import BITS_8, STOP_BITS_1, PARITY_NONE, FLOW_RTS_CTS


class ThorlabsK10CR1(object):
    """ Control interface for Thorlabs K10CR1 rotation mount.

    Thorlabs provided APT / Kinesis Dlls seemed buggy and unreliable, so this is based
    on direct communication with FTDI USB chip using hex codes defined in APT reference manual.
    The init route is the same as that used in Thorlabs Kinesis GUI, as determined
    by USB packet sniffing (Wireshark).

    References:
        Inspired by comment at: https://github.com/qpit/thorlabs_apt/issues/3
    """
    # Device takes a short while to prepare data from reading once command received
    # 0.02 s seems to work well
    COMMS_DELAY = 0.02

    def __init__(self, serial='55000359'):
        """ Initialise connection. """
        serial_bytes = serial.encode()  # Convert serial number from string to bytes
        self.connection = ftd2xx.openEx(serial_bytes)
        device_info = self.connection.getDeviceInfo()

        device_description = device_info['description'].decode()
        if 'K10CR1' in device_description:
            print('Successful connection established to {}'.format(device_description))
        else:
            raise ValueError('Connection failed / incorrect device serial specified. Description retuned is: {}'.format(device_description))

        # Connection initialisation
        self.connection.setBaudRate(115200)
        self.connection.setDataCharacteristics(BITS_8, STOP_BITS_1, PARITY_NONE)
        time.sleep(self.COMMS_DELAY)
        self.connection.purge()
        time.sleep(self.COMMS_DELAY)
        self.connection.resetDevice()
        self.connection.setFlowControl(FLOW_RTS_CTS, 0, 0)
        self.connection.setRts()

        self.connection.setTimeouts(10, 10)

        # Thorlabs device initialisation (determined from Wireshark )

        # MGMSG_HW_NO_FLASH_PROGRAMMING
        # This message is sent on start up to notify the controller of the source and destination addresses.
        # A client application must send this message as part of its initialization process.
        self.send('\x18\x00\x00\x00\x21\x01')

        # MGMSG_MOT_SET_POWERPARAMS
        # The power needed to hold a motor in a fixed position is much smaller than that required for a move.
        # It is good practice to decrease the power in a stationary motor in order to reduce heating, and thereby minimize thermal movements caused by expansion.
        # This message sets a reduction factor for the rest power and the move power values as a percentage of full power.
        # Typically, move power should be set to 100% and rest power to a value significantly less than this.
        # This sets rest power to 10% of full move; I think the move power is set to 30% of max (why?)
        # self.send('\x26\x04\x06\x00\xa1\x01\x01\x00\x0a\x00\x1e\x00')
        # At present, this seems to prevent motion of the stage!

    def jog_forwards(self):
        """ Jog rotator forwards. """
        self.send('\x6A\x04\x00\x01\x21\x01')

    def jog_backwards(self):
        """ Jog rotator backwards. """
        self.send('\x6A\x04\x00\x02\x21\x01')

    def home(self):
        """ Home stage. """
        self.send('\x43\x04\x00\x00\x22\x01')

    def close_connection(self):
        self.connection.close()

    def get_position(self):
        """ Return current position [deg]. """
        response = self.query('\x11\x04\x01\x00\x21\x01')
        print(response)

        # Get channel number
        chan_ident = np.fromstring(response[6:8], dtype='<u2')[0]  # Convert hex to 2-byte little endian unsigned int
        assert chan_ident == 1  # Check channel ident is 1 as expected (otherwise, comms error may have occured)

        # Data returned is in position encoder counts, so we convert to degrees based on APT documentation (p20, Thorlabs issue 20 of APT docs)
        counts = np.fromstring(response[8:12], dtype='<i4')[0]  # Convert hex to 4-byte little endian signed int
        return counts / 136533

    def get_status(self):
        """ Return status bytes. """
        response = self.query('\x29\x04\x01\x00\x21\x01')
        print(response)

        # Get channel number
        chan_ident = np.fromstring(response[6:8], dtype='<u2')[0]  # Convert hex to 2-byte little endian unsigned int
        assert chan_ident == 1  # Check channel ident is 1 as expected (otherwise, comms error may have occured)

        # Decode status bytes using bit maskings (see APT documentation, and note that we reverse bit order here to use other endian convention to manual, p98)
        status = response[8:12]

        masked_bits = bytes(map(operator.and_, status, b'\x00\x04\x00\x00'))
        if np.fromstring(masked_bits, 'u4')[0] != 0:
            print('Homed')
            homed = True
        else:
            print('Not homed')
            homed = False

        masked_bits = bytes(map(operator.and_, status, b'\x40\x00\x00\x00'))
        if np.fromstring(masked_bits, 'u4')[0] != 0:
            print('jogging forw')
        else:
            print('not jogging forw')

        return status


    ############################################
    # DEFINE BASIC SEND/RECEIVE/QUERY COMMANDS #
    ############################################
    # If we start using more FTD2xx interfaces, this could be moved to mqlab/connections.py
    def send(self, command):
        """ Send command (entereted as hex string, e.g. '\x6A\x04\x00\x02\x21\x01') as bytes object to device. """
        command_bytes = command.encode()
        self.connection.write(command_bytes)

    def receive(self, dtype=None):
        """ Read data from device and return as user-chosen datatype (None = bytes, or enter str, int or float). """
        response = self.connection.read(1024)  # Read up to 1 kbyte (comms here not likely to exceed this)

        if dtype is None:
            return response
        elif dtype == str:
            return response.decode('utf-8')
        else:
            return np.fromstring(response, dtype=dtype)

    def query(self, command, dtype=None):
        """ Send command to device, read reply and return as type (None = bytes, or enter dtype). """
        self.connection.purge()  # Clear buffers of any current data
        time.sleep(self.COMMS_DELAY)
        self.send(command)
        time.sleep(self.COMMS_DELAY)
        response = self.receive(dtype=dtype)
        return response
