""" Communication protocol definitions, establishing common framework for instrument control. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import os
import socket
import numpy as np
from configparser import ConfigParser
from vxi11 import Instrument as VXI11Instrument

# Define location of MQ Instruments config file of addresses and interfacing parameters
mq_instruments_config_filepath = os.path.dirname(os.path.realpath(__file__)) + '/mq_instruments.txt'
mq_instruments_config_filepath = mq_instruments_config_filepath.replace('\\', '/')  # Windows -> Unix path mapping


class Instrument(object):
    """ Base class for lab instrument, defining connection protocols. """

    def __init__(self, interface, mq_id=None, ip_address=None, port=None, terminating_char='', gpib_address=None, com_port=None, baud_rate=None, timeout=2):
        """ Instantiate instrument object.

        If an mq_id is passed, the connection configuration will be read from the config file.
        Otherwise, these must be entered manually.

        Args:
            interface (str): connection type, either: 'ethernet', 'gpib', 'serial'
            Either, for automatic config:
                mq_id (str): ID of MQ lab instrument, as defined in the config file, "mq_instruments.txt"
            Or, for a manual ethernet config:
                ip_address (str): ip address of device
                port (int): port to use for connection
                terminating_char (str): character that signals an end-of-message for the device
            Or, for a manual GPIB config:
                gpib_address (int): address of device
                terminating_char (str): character that signals an end-of-message for the device
            Or, for a manual RS232 serial config:
                com_port (int) : serial port number of this computer's port, NOT the instrument
                baud_rate (int): baud rate required for the device
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

        # Ignore case of interface string
        interface = interface.lower()

        # Instantiate connections.
        if interface == 'ethernet':
            self.connection = EthernetConnection(ip_address=ip_address, port=port, terminating_char=terminating_char, timeout=timeout)
        elif interface == 'gpib-ethernet':
            self.connection = GPIBOverEthernetConnection(gpib_address=gpib_address)
        elif interface == 'gpib-usb':
            raise ValueError('Not implemented yet.')
        elif interface == 'serial':
            raise ValueError('Not implemented yet.')
        else:
            raise ValueError('Interface not recognised - must be "ethernet", "gpib_over_ethernet", or "serial".')

    def get_ident(self):
        """ Query the device using the standard IDN command, often triggering it to return the make, model etc. """
        return self.connection.query('*IDN?')

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
        num_bytes_that_specify_length = int(block[start_idx+1:start_idx+2])
        data_length = int(block[start_idx+2:start_idx+2+num_bytes_that_specify_length])
        data_start_idx = start_idx + 2 + num_bytes_that_specify_length
        # Finally, slice the relevant data from the block and convert to an array based on the data type
        data = block[data_start_idx:data_start_idx + data_length]
        data = np.fromstring(data, dtype=dtype)
        return data


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
        self.terminating_char = terminating_char.replace('LF', '\n').replace('CR', '\r')

        # Open socket ready for communication
        self.open_socket()

    def open_socket(self):
        """ Create a socket for a network transaction. """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        self.socket.connect((self.ip_address, self.port))

    def close_socket(self):
        """ Destroy  open socket. """
        self.socket.shutdown(socket.SHUT_RDWR)  # Close the socket properly (RDWR closes read and write access)
        self.socket.close()

    def send(self, command):
        """ Send command (str) to the device. """
        message = command + self.terminating_char
        self.socket.send(message.encode('utf-8'))  # Use encode to cast from str to UTF-8 unicode bytes object

    def receive(self, decode_as_string=False):
        """ Read response from device. """
        response = b''
        while not response.endswith(b'\r\n'):
            response += self.socket.recv(1024)

        # Strip off any end-of-line terminating characters / blank space
        response = response.rstrip()

        if decode_as_string:
            response = response.decode('utf-8')
        return response

    def query(self, command, decode_response_as_string=False):
        """ Send command to device, read reply. """
        self.send(command)
        return self.receive(decode_as_string=decode_response_as_string)


class GPIBOverEthernetConnection(object):
    """ Connection protocols for GPIB devices though a LAN/GPIB gateway. """

    def __init__(self, gpib_address):
        """ Constructor for an ethernet port connected instrument.

        Args:
            gpib_address (int): GPIB address set in instrument
        """
        host_ip_address = '10.46.25.51'  # IP address of HP E2050A LAN/GPIB Gateway (fixed IP set in unit)
        self.vxi11 = VXI11Instrument(host=host_ip_address, name="gpib0,%i" % gpib_address)

    def get_status_byte(self):
        """ Return status byte as array of 8 boolean values.

        e.g. get_status_bye[7] is the 8th bit (MSB) of the byte
        """
        status_byte_as_int = self.vxi11.read_stb()
        status_byte = [bool(int(i)) for i in "{0:08b}".format(status_byte_as_int)]
        status_byte.reverse()  # Set so MSB is the list item with the highest index
        return status_byte

    def send(self, command):
        """ Send command to device. """
        self.vxi11.write(command)

    def receive(self, decode_as_string=False):
        """ Read data from device. """
        response = self.vxi11.read_raw()

        # Strip off any end-of-line terminating characters / blank space
        response = response.rstrip()

        if decode_as_string:
            response = response.decode('utf-8')
        return response

    def query(self, command, decode_response_as_string=False):
        """ Send command to device, read reply. """
        self.send(command)
        response = self.receive(decode_as_string=decode_response_as_string)

        # Set VXI11 device back in LOCAL mode, ready for user interaction
        self.vxi11.local()

        return response
