""" Definition of monochromator interfacing commands. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import struct
import time

import mqlab.utils as ut
from mqlab.connections import Instrument


class Monochromator(Instrument):
    pass


class CM112(Monochromator):
    """ Control interface for CVI Digikrom CM112 1/8m double monochromator. """
    # Device requires hexcode interfacing. We use struct module for packing/unpacking bytes objects: '>' indicates big endian convention, 'B' = unsigned one-byte character, 'H' = unsigned two-byte character

    def __init__(self, com_port):
        """ Initialise serial connection, but modify the initialisation command to set the correct default connection properties. """
        super().__init__(interface='serial', com_port=com_port, baud_rate=9600)
        # Save current units locally for quick re-use
        self.get_units()

    def echo(self):
        """ Verifies communication with device by sending 27 in decimal (0x1b) and reading response, which should also be 0x1b. """
        cmd = struct.pack('>B', 27)
        response = self.query(cmd)
        if response[0] == 27:
            print('Communication successful.')
        else:
            raise Exception('Communication error: echo command failed')

    def home(self):
        """ Set grating to home position. """
        cmd = struct.pack('>3B', 255, 255, 255)
        self.send(cmd)

    def step(self):
        """ Advance position by step, where step amount is set by size parameter in device. """
        cmd = struct.pack('>B', 54)
        self.send(cmd)

    def set_position(self, wl):
        """ Moves monochromator to user-given wavelength, wl [nm]. """
        # FORCE USING nm
        if self._current_units != 'nm':
            self.set_units('nm')

        # Combine the one-byte goto command with two-byte wl position
        cmd = struct.pack('>B', 16) + struct.pack('>H', int(wl))
        self.send(cmd)

        # # Wavelength position can be sent in either um, nm or Angstrom, as 2-byte form.
        # # Since an int value must be sent, this limits both the resolution and max value that can be set
        # if wl > (2**16 / 10):  # 6553.6 nm
        #     # Value too high to send in Angstrom units, so send in nm (setting resolution = 1 nm)
        #     if self._current_units != 'nm':
        #         self.set_units('nm')
        #     # Combine the one-byte goto command with two-byte wl position
        #     cmd = struct.pack('>B', 16) + struct.pack('>H', wl)
        # else:
        #     # Value low enough to use Angstrom units (setting resolution = 1A = 0.1 nm)
        #     if self._current_units != 'A':
        #         self.set_units('A')
        #     wl_angstrom = int(wl * 10)
        #     cmd = struct.pack('>B', 16) + struct.pack('>H', wl_angstrom)
        # self.send(cmd)

    def scan(self, wl1, wl2):
        """ Scan monochromator from wl1 to wl2 as rate "determined by Spectral ProductsEED command". """
        # Wavelength position can be sent in either um, nm or Angstrom, as 2-byte form.
        # Since an int value must be sent, this limits both the resolution and max value that can be set
        if max(wl1, wl2) > (2**16 / 10):
            # Value too high to send in Angstrom units, so send in nm (setting resolution = 1 nm)
            if self._current_units != 'nm': self.set_units('nm')
            # Combine the one-byte goto command with two-byte wl position
            cmd = struct.pack('>B', 12) + struct.pack('>H', wl1) + struct.pack('>H', wl2)
        else:
            # Value low enough to use Angstrom units (setting resolution = 1A = 0.1 nm)
            if self._current_units != 'A': self.set_units('A')
            wl1_angstrom = int(wl1 * 10)
            wl2_angstrom = int(wl2 * 10)
            cmd = struct.pack('>B', 12) + struct.pack('>H', wl1_angstrom) + struct.pack('>H', wl2_angstrom)

        self.send(cmd)

    def set_step_size(self, step_size):
        """ Set step size in position [nm]. """
        # Max step size for each unit is based on one byte of SIGNED data -> range = 2**8 / 2 = 128
        # if step_size < 12.8:
            # if self._current_units != 'A':
                # self.set_units('A')
                # time.sleep(1)
            # step_size_angstrom = int(step_size * 10)
            # cmd = struct.pack('>B', 55) + struct.pack('>b', step_size_angstrom)  # note: lower case b here since we want a signed step_size byte (sign indicates direction)
        if step_size < 128:
            if self._current_units != 'nm':
                self.set_units('nm')
            cmd = struct.pack('>B', 55) + struct.pack('>b', int(step_size))
        else:
            raise ValueError('Step size should be less than 128 nm. Overriding this is possible by sending size in micron units - needs this code to be updated.')
        self.send(cmd)

    def set_units(self, units):
        """ Set units to either: 'A' for Angstroms, nm' for nanometres, or 'um' for microns. """
        if units == 'A':
            units_byte = 2
        elif units == 'nm':
            units_byte = 1
        elif units == 'um':
            units_byte == 0
        else:
            raise ValueError('Units not recognised.')

        cmd = struct.pack('>2B', 50, units_byte)
        self.send(cmd)
        time.sleep(0.2)  # Allow time for this to be accepted

    def get_position(self):
        """ Return current monochromator position in wavelengths [nm]. """
        msg = struct.pack('>2B', 56, 00)
        response = self.query(msg)
        # Read and decode wavelength value (unknown units)
        encoded_wl = response[:2]
        wl = struct.unpack('>H', encoded_wl)[0]
        units, to_nm_multiplier = self.get_units()
        return wl * to_nm_multiplier

    def get_num_gratings(self):
        """ Return the number of gratings. """
        msg = struct.pack('>2B', 56, 13)
        response = self.query(msg)
        return response[1]

    def get_double_mode(self):
        """ Determine whether the double monochromator is set for additive (more dispersion) or subtractive (less distortion) operation. """
        msg = struct.pack('>2B', 56, 1)
        response = self.query(msg)
        if response[1] == 254:
            return 'Subtractive mode selected.'
        elif response[1] == 1:
            return 'Additive mode selected.'
        else:
            raise ValueError('Mode not recognised.')

    def get_grating_lines_per_mm(self):
        """ Return current grating setting's lines per mm. """
        msg = struct.pack('>2B', 56, 2)
        response = self.query(msg)
        return struct.unpack('>H', response[:2])[0]

    def get_grating_blaze(self):
        """ Return blaze wavelength [nm] for current grating. """
        msg = struct.pack('>2B', 56, 3)
        response = self.query(msg)
        return struct.unpack('>H', response[:2])[0]

    def get_speed(self):
        """ Return speed setting. """
        msg = struct.pack('>2B', 56, 5)
        response = self.query(msg)
        return struct.unpack('>H', response[:2])[0]

    def get_serial_number(self):
        """ Return speed setting. """
        msg = struct.pack('>2B', 56, 19)
        response = self.query(msg)
        return struct.unpack('>H', response[:2])[0]

    def get_step_size(self):
        """ Return step size of "STEP" command. Units are defined internally by monochromator. Two's complement form -> -ve / +ve set direction."""
        msg = struct.pack('>2B', 56, 6)
        response = self.query(msg)
        return response[1]

    def get_units(self):
        """ Return units and the multiplier to multiply position by in order to find the wavelength in [nm]. """
        msg = struct.pack('>2B', 56, 14)
        response = self.query(msg)

        if response[1] == 2:
            units = 'A'
            to_nm_multiplier = 1 / 10
        elif response[1] == 1:
            units = 'nm'
            to_nm_multiplier = 1
        elif response[1] == 0:
            units = 'um'
            to_nm_multiplier = 1000
        else:
            raise ValueError('Units not recognised.')

        # Save results locally too for quick re-use
        self._current_units = units
        self._current_to_nm_multiplier = to_nm_multiplier

        return units, to_nm_multiplier
