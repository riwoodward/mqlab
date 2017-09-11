""" Definition of automated optomechanics interfaces. NOT FINISHED OR TESTED. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import time
import operator
import struct
import numpy as np

import mqlab.utils as ut
from mqlab.connections import Instrument

try:
    import ftd2xx
    from ftd2xx.defines import BITS_8, STOP_BITS_1, PARITY_NONE, FLOW_RTS_CTS
except Exception:
    print('FTD2xx (THORLABS motor controller) import failed. Install Kinesis software and check FTD2xx DLL is installed correctly.')
import zaber.serial as zaber


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
    # COMMS_DELAY = 0.02
    COMMS_DELAY = 0.05

    # Encoder information (mapping counts to real-world values), angular distance units are in degrees
    POS_COUNT_FACTOR = 136533
    VEL_COUNT_FACTOR = 7329109
    ACC_COUNT_FACTOR = 1502

    def __init__(self, serial='55000359'):
        """ Initialise connection. """
        serial_bytes = serial.encode()  # Convert serial number from string to bytes
        self.connection = ftd2xx.openEx(serial_bytes)
        device_info = self.connection.getDeviceInfo()

        device_description = device_info['description'].decode()
        if 'K10CR1' in device_description:
            print('Successful connection established to {} (serial: {})'.format(device_description, serial))
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

        # MQ lab init
        # self.set_max_speed()  # Sometimes doesn't work
        self.set_fast_speed()

    def jog_forwards(self):
        """ Jog rotator forwards (with default jog params saved to device). """
        self.send('\x6A\x04\x00\x01\x21\x01')

    def jog_backwards(self):
        """ Jog rotator backwards (with default jog params saved to device). """
        self.send('\x6A\x04\x00\x02\x21\x01')

    def home(self):
        """ Home stage. """
        self.send('\x43\x04\x00\x00\x22\x01')

    def close_connection(self):
        self.connection.close()

    @property
    def position(self):
        """ Return current position [deg]. """
        response = self.query('\x11\x04\x01\x00\x21\x01')

        # Get channel number
        chan_ident = np.fromstring(response[6:8], dtype='<u2')[0]  # Convert hex to 2-byte little endian unsigned int
        assert chan_ident == 1  # Check channel ident is 1 as expected (otherwise, comms error may have occured)

        # Data returned is in position encoder counts, so we convert to degrees based on APT documentation (p20, Thorlabs issue 20 of APT docs)
        counts = np.fromstring(response[8:12], dtype='<i4')[0]  # Convert hex to 4-byte little endian signed int
        return counts / self.POS_COUNT_FACTOR

    def get_status(self):
        """ Return status bytes (PROCESSING INCOMPLETE). """
        response = self.query('\x29\x04\x01\x00\x21\x01')

        # while len(response) < 1:
            # print('Status failed. retrying..')
            # time.sleep(1)
            # response = self.query('\x29\x04\x01\x00\x21\x01')

            # in_queue2 = self.connection.getQueueStatus()
            # print(f'Status requested failed (null value returned). Check device and retry. DEBUG: query status = {in_queue} before, {in_queue2} retry.')

        # Get channel number
        chan_ident = np.fromstring(response[6:8], dtype='<u2')[0]  # Convert hex to 2-byte little endian unsigned int
        assert chan_ident == 1  # Check channel ident is 1 as expected (otherwise, comms error may have occured)

        # Decode status bytes using bit maskings (see APT documentation, and note that we reverse bit order here to use other endian convention to manual, p98)
        status = response[8:12]
        return np.fromstring(status, dtype='<u4')[0]

    def set_fast_speed(self):
        """ Set max vel and acc to 20 units, for move operations (not jog). """
        self.send(b'\x13\x04\x0e\x00\xa1\x01\x01\x00\x00\x00\x00\x00\x58\x75\x00\x00\xab\xaa\xbc\x08')

    def set_max_speed(self):
        """ Set max vel and max acc. to 25 degrees per second and second^2, for move operations (not jog). """
        self.send(b'\x13\x04\x0e\x00\xa1\x01\x01\x00\x00\x00\x00\x00\xae\x92\x00\x00\x55\xd5\xeb\x0a')

    @property
    def is_moving(self):
        """ Return True is stage moving. False otherwise. """
        status = self.get_status()
        if status & 0x00000010:
            moving = True
        else:
            moving = False
        return moving

    def move_to(self, position, wait_until_complete=True):
        """ Rotate stage to position [degrees]. """
        command = b'\x53\x04\x06\x00\xa1\x01\x01\x00'  # Command includes 6-digit header, and 2-digit chan identifier (01 default)
        counts = position * self.POS_COUNT_FACTOR
        command += struct.pack('<i', counts)  # Add on the absolute distance (as long type)
        self.send(command)

        if wait_until_complete:
            time.sleep(0.4)
            while self.is_moving:
                time.sleep(0.4)

    ############################################
    # DEFINE BASIC SEND/RECEIVE/QUERY COMMANDS #
    ############################################
    # If we start using more FTD2xx interfaces, this could be moved to mqlab/connections.py
    def send(self, command):
        """ Send command (entereted as hex string, e.g. '\x6A\x04\x00\x02\x21\x01') as bytes object to device. """
        if type(command) is not bytes:
            command = command.encode()
        self.connection.write(command)

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


class ZaberLinearTranslationStage(zaber.BinaryDevice):
    """ Control interface for Zaber linear translation stage, based on their provided library with added functionality (for data entry in physical units).

    References:
        https://www.zaber.com/products/product_detail.php?detail=T-LA60A
    """

    # Single step is called a "microstep" with 0.09921875 um phyical distance
    microstep_size_mm = 0.09921875 * 1e-3

    def __init__(self, com_port=None):
        """ Initialise Zaber connection.

        Args:
            port : port label e.g. 'COM1'
        """
        if not com_port:
            com_port = ut.available_serial_ports()[0]
        serial_connection = zaber.BinarySerial(com_port)
        super().__init__(serial_connection, 1)

        # Default to max acceleration
        time.sleep(0.1)
        self.set_acceleration_to_max()

    def send_no_reply(self, *args):
        """Sends a command to this device, without expecting a response. """
        if len(args) == 1 and isinstance(args[0], zaber.BinaryCommand):
            command = args[0]
        elif len(args) < 4:
            command = zaber.BinaryCommand(self.number, *args)

        command.device_number = self.number
        self.port.write(command)

    def _distance_microsteps_from_mm(self, distance_mm):
        return int(distance_mm / self.microstep_size_mm)

    def _speed_microsteps_from_mm_s(self, speed_mm_s):
        return int(speed_mm_s / (9.375 * self.microstep_size_mm))

    def home(self):
        self.send_no_reply(1)

    def get_position(self):
        """ Return position (mm). """
        return self.send(60).data

    def move_by(self, distance):
        """ Move relative distance (mm). """
        self.send_no_reply(21, self._distance_microsteps_from_mm(distance))
        # self.move_rel(self._distance_microsteps_from_mm(distance))

    def move_to(self, position):
        """ Move to an absolute position (only works in the stage has been homed first so it has a zero position known). """
        self.send_no_reply(20, self._distance_microsteps_from_mm(position))
        # self.move_abs(self._distance_microsteps_from_mm(position))

    def move_continuously(self, speed):
        """ Move continuously (unless self.stop executed / buffer is hit) at speed (mm/s). """
        self.send_no_reply(22, self._speed_microsteps_from_mm_s(speed))
        # self.move_vel(self._speed_microsteps_from_mm_s(speed))

    def set_default_move_speed(self, speed):
        """ Set default target speed, for move commands (mm/s).
        Permissible range is: 0.0009302 mm/s to 4 m /s
        """
        self.send_no_reply(42, self._speed_microsteps_from_mm_s(speed))

    def set_acceleration_to_max(self):
        """ From manual: If acceleration is set to 0, it is as if acceleration is set to (512*R-1). Effectively acceleration is turned off and the device will start moving at the target speed immediately. """
        self.send_no_reply(43, 0)
