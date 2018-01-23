""" Communication protocol definitions, establishing common framework for instrument control.

Requirements:
    for RS232: pyserial
    for Ethernet: socket (installed by default)
    for GPIB: python-vxi11
"""
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import os
import socket
import numpy as np
import serial
import time
import visa
from configparser import ConfigParser
from vxi11 import Instrument as VXI11Instrument

# Define location of MQ Instruments config file of addresses and interfacing parameters
mq_instruments_config_filepath = os.path.dirname(os.path.realpath(__file__)) + '/mq_instruments.txt'
mq_instruments_config_filepath = mq_instruments_config_filepath.replace('\\', '/')  # Windows -> Unix path mapping


class Instrument(object):
    """ Base class for lab instrument, defining connection protocols. """

    def __init__(self, interface, mq_id=None, ip_address=None, port=None, terminating_char='', gpib_address=None, gpib_location='hearing_hub', com_port=None, baud_rate=None, serial_number=None, timeout=2):
        """ Instantiate instrument object.

        If an mq_id is passed, the connection configuration will be read from the config file.
        Otherwise, these must be entered manually.

        Args:
            interface (str): connection type, either: 'ethernet', 'gpib-ethernet', 'serial' or 'usb'
            Either, for automatic config:
                mq_id (str): ID of MQ lab instrument, as defined in the config file, "mq_instruments.txt"
            Or, for a manual ethernet config:
                ip_address (str): ip address of device
                port (int): port to use for connection
            Or, for a manual GPIB config:
                gpib_address (int): address of device
                gpib_location (str): 'hearing_hub' or 'engineering', so the GPIB host IP can be automatically obtained
            Or, for a manual RS232 serial config:
                com_port (int) : serial port number of this computer's port, NOT the instrument
                baud_rate (int): baud rate required for the device
            Or, for a manual USB config:
                serial_number : device serial number used to identify it from the list of connected USB devices
            terminating_char (str): character that signals an end-of-message for the device
            timeout (float, optional): wait time [s] until no reply to a command is considered a failure

        """
        # If an mq_id is given, look up instrument config in the mq_instruments.cfg file (this overrides any manually entered params)
        if mq_id:
            config_filepath = mq_instruments_config_filepath
            config = ConfigParser()
            config.read(config_filepath)
            port = config[mq_id].getint('port')
            ip_address = config[mq_id].get('ip_address')
            terminating_char = config[mq_id].get('terminating_char')
            gpib_address = config[mq_id].getint('gpib_address')
            baud_rate = config[mq_id].getint('baud_rate')
            serial_number = config[mq_id].get('serial_number')

        # Ignore case of interface string
        self._interface = interface.lower()

        # Instantiate connections.
        if self._interface == 'ethernet':
            if (ip_address is None) or (port is None):
                raise ValueError('For an ethernet device connection, ip_address and port must be specified. Ensure correct device type was specified and all parameters are given.')
            self.connection = EthernetConnection(ip_address=ip_address, port=port, terminating_char=terminating_char, timeout=timeout)

        elif self._interface == 'gpib-ethernet':
            if gpib_address is None:
                raise ValueError('For a GPIB-over-ethernet device connection, gpib_address must be specified. Ensure correct device type was specified and all parameters are given.')
            # Get GPIB-LAN gateway box IP address (different box for each lab)
            if 'hub' in gpib_location.lower():
                # Hearing Hub
                host_ip_address = '10.204.43.240'
            else:
                # Engineering Dept.
                host_ip_address = '10.46.25.190'
            self.connection = GPIBOverEthernetConnection(gpib_address=gpib_address, host_ip_address=host_ip_address)

        elif self._interface == 'gpib-usb':
            raise ValueError('Not implemented yet.')

        elif self._interface == 'serial':
            if (com_port is None) or (baud_rate is None):
                raise ValueError('For a serial device connection, com_port and baud_rate must be specified. Ensure correct device type was specified and all parameters are given.')
            self.connection = SerialConnection(port=com_port, baud_rate=baud_rate, terminating_char=terminating_char, timeout=timeout)

        elif self._interface == 'usb':
            if serial_number is None:
                raise ValueError('For a USB device connection, serial_number must be specified. Ensure correct device type was specified and all parameters are given.')
            self.connection = USBConnection(serial_number=serial_number)

        else:
            raise ValueError('Interface not recognised - must be "ethernet", "gpib_over_ethernet", or "serial".')

    def get_ident(self):
        """ Query the device using the standard IDN command, often triggering it to return the make, model etc. """
        return self.query('*IDN?')

    def set_local_mode(self):
        """ Set instrument back to local mode, if it's locked in remote access only mode. """
        try:
            self.connection.vxi11.local()
        except Exception:
            print('Failed: command only works for GPIB-Ethernet devices.')

    def _decode_binary_block(self, block, dtype):
        """ Convert a binary block (as defined by IEEE 488.2), which is commonly returned by lab
        instruments, to a numpy array.

        Args:
            block : binary block bytestring
            dtype : data encoding format e.g. 'float32'
        """
        # The fixed length block is defined by IEEE 488.2 and consists of `#'' (ASCII), one numeric (ASCII) indicating the number of bytes that specifies the length after #, then the length designation (ASCII), and finally the actual binary data of a specified length.
        # First, locate start of block
        start_idx = block.find(b'#')
        # Read header that indicates the data length
        num_bytes_that_specify_length = int(block[start_idx + 1: start_idx + 2])
        data_length = int(block[start_idx + 2: start_idx + 2 + num_bytes_that_specify_length])
        data_start_idx = start_idx + 2 + num_bytes_that_specify_length
        # Finally, slice the relevant data from the block and convert to an array based on the data type
        data = block[data_start_idx:data_start_idx + data_length]
        data = np.fromstring(data, dtype=dtype)
        return data

    def send(self, command):
        """ Send command (str or bytes object, as required) to device. """
        self.connection.write(command)

    def receive(self, dtype=None):
        """ Read data from device and return as user-chosen datatype (None = bytes, or enter str, int or float). """
        response = self.connection.read()

        # Strip off any end-of-line terminating characters / blank space
        response = response.rstrip()

        if dtype is None:
            return response
        elif dtype == float:
            return float(response)
        elif dtype == str:
            return response.decode('utf-8')
        elif dtype == int:
            return int(float(response))

    def query(self, command, dtype=None):
        """ Send command to device, read reply and return as type (None = bytes, or enter str, int or float). """
        self.send(command)
        response = self.receive(dtype=dtype)
        return response


class EthernetConnection(object):
    """ Base ethernet connection class. """

    def __init__(self, ip_address, port, terminating_char='', timeout=3):
        """ Constructor for an ethernet port connected instrument.

        Args:
            ip (str): device ip_address (ideally, make this static in the router config)
            port (int) : communication port
            terminating_char (str) : character(s) that signals the end of message for the device.
            timeout (float, optional): wait time [s] until no reply to a command is considered a failure
        """
        self.ip_address = ip_address
        self.port = port
        self.timeout = timeout

        # Convert terminating character shorthand to the required escape sequence
        if terminating_char is not None:
            self.terminating_char = terminating_char.replace('LF', '\n').replace('CR', '\r')

        # Open socket ready for communication
        self.open_socket()

    def open_socket(self):
        """ Create a socket for a network transaction. """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        self.socket.connect((self.ip_address, self.port))

    def close_socket(self):
        """ Destroy open socket. """
        self.socket.shutdown(socket.SHUT_RDWR)  # Close the socket properly (RDWR closes read and write access)
        self.socket.close()

    def write(self, command):
        """ Send command (str or bytes) to the device. """
        # If device accepts ASCII commands, then we convert the command str to a bytes object to send over serial
        # Use encode to cast from str to UTF-8 unicode bytes object
        if type(command) == str:
            message = command + self.terminating_char
            message = message.encode('utf-8')
        # If command is already formatted specifically for the device, just encode the terminating string and add to message
        else:
            message = command + self.terminating_char.encode('utf-8')

        self.socket.send(message)

    def read(self):
        """ Read data from device. """
        # Read data in kbyte chunks
        response = b''
        while not response.endswith(b'\r\n'):
            response += self.socket.recv(1024)
        return response


class GPIBOverEthernetConnection(object):
    """ Connection protocols for GPIB devices though a LAN/GPIB gateway. """

    def __init__(self, gpib_address, host_ip_address):
        """ Constructor for an ethernet port connected instrument.

        Args:
            gpib_address (int): GPIB address set in instrument
            host_ip_address (str): IP of GPIB-LAN gateway, e.g. '10.204.43.240' for hearing hub network
        """
        self.vxi11 = VXI11Instrument(host=host_ip_address, name="gpib0,%i" % gpib_address)

    def get_status_byte(self):
        """ Return status byte as array of 8 boolean values.

        e.g. get_status_bye[7] is the 8th bit (MSB) of the byte
        """
        status_byte_as_int = self.vxi11.read_stb()
        status_byte = [int(i) for i in "{0:08b}".format(status_byte_as_int)]
        status_byte.reverse()  # Set so MSB is the list item with the highest index
        return status_byte

    def write(self, command):
        """ Send command (str) to device. """
        # Note, VXI11 takes a string command, not bytes object
        self.vxi11.write(command)

    def read(self):
        """ Read data from device. """
        response = self.vxi11.read_raw()

        # Set VXI11 device back in LOCAL mode, ready for user interaction
        self.vxi11.local()

        return response


class SerialConnection(object):
    """ Connection protocols for RS232 devices. """

    def __init__(self, port='COM1', baud_rate=9600, terminating_char='', byte_size=8, parity=serial.PARITY_NONE, stop_bits=1, xonxoff=0, rtscts=0, timeout=1):
        """ Constructor for an serial port connected instrument.

        Args:
            port (str): use 'COM#' format for Windows.
            buadrate (int): baud rate [bit/s] for instrument
            terminating_char (str): character that signals an end-of-message for the device
            bytesize, parity, stopbits, xonoff, rtscts : see serial documentation
            timeout : timeout time [s]
        """
        # Convert terminating character shorthand to the required escape sequence
        self.terminating_char = terminating_char.replace('LF', '\n').replace('CR', '\r')

        # Set delay between send and receive operations to allow for processing
        self.delay = 0.15

        self.serial = serial.Serial(port=port, baudrate=baud_rate, bytesize=byte_size, parity=parity, stopbits=stop_bits, timeout=timeout, xonxoff=xonxoff, rtscts=rtscts)

    def close_bus(self):
        """ Close serial connection. """
        self.serial.close()

    def write(self, command):
        """ Send command to device. """
        # Flush buffers, clearing any data waiting to be read out that hasn't been
        self.serial.flushOutput()
        self.serial.flushInput()
        # If device accepts ASCII commands, then we must convert the command str to a bytes object to send over serial
        if type(command) == str:
            message = command + self.terminating_char
            message = message.encode('utf-8')
        # If command is already formatted specifically for the device, just encode the terminating string and add to message
        else:
            message = command + self.terminating_char.encode('utf-8')
        self.serial.write(message)

    def read(self):
        """ Read data from device. """
        # Allow small delay for data to be placed on buffer after operation
        time.sleep(self.delay)
        response = self.serial.read_all()
        return response


class USBConnection(object):
    """ Connection protocols for USB devices.

    Unfortunately requires VISA backend to operate (must be installed separately).

    TODO: New Installation Idea:
        Install USB backend (for linux, libusb probably already installed, for Windows, download libusb binaries [http://libusb.info/] and copy
        the appropraite libusb-1.0.dll file into C:/Windows/System32 folder.
    """

    def __init__(self, serial_number):
        """ Constructor for an serial port connected instrument.

        Args:
            serial_numer : serial number of device, which is used to identify it from other connected USB devices
            (if this doesn't work - we could add args for vendorID and modelID too)
        """
        rm = visa.ResourceManager()
        devices = rm.list_resources()

        found = False
        for device in devices:
            if serial_number in device:
                self.usb = rm.open_resource(device)
                found = True

        if not found:
            raise ValueError('USB connected device not found')

    def write(self, command):
        """ Send command to device. """
        self.usb.write(command)

    def read(self):
        """ Read data from device. """
        return self.usb.read()
