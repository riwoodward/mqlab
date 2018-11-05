""" Definition of autocorrelator interfacing commands. """
import numpy as np
import time

from mqlab.connections import Instrument


class Autocorrelator(Instrument):
    pass


class APEPulseCheck(Autocorrelator):
    """ Communication with APE Autocorrelator. Due to a bug (/"feature") of the APE software, it seems that to use the device remotely you must install (AND RUN CONTINUOUSLY) their pulseLink software and set the TCP/IP port for the device (e.g. using the one hard-coded below: 51123). It seems this is not saved when the device is power cycled and hence, must be entered each time. """

    def __init__(self):
        """ Instantiate communication, with has to be using TCP/IP ethernet protocols over the USB connection. """
        super().__init__(interface='ethernet', ip_address='127.0.0.1', port=51123, terminating_char='\r\n', timeout=5)

    def start(self):
        """ Start continuously sweeping. """
        self.send(':sta:start 1')

    def stop(self):
        """ Stop continuously sweeping. """
        self.send(':sta:start 0')

    def grab(self, raw=False, debug=False):
        """ Return delays [s] and AC intensities [a.u.] data, as shown on APE software (inc. filtering, averaging etc).

        Args:
            raw (bool): if True, grab data without any filtering / averaging etc.
        """
        # Manually request data as it seems the standard way of reading data in chunks doesn't work too well.
        if raw:
            self.send(':acf:data?')
        else:
            self.send(':acf:dacf?')
        # Short delay to allow data to be prepared for reading
        time.sleep(0.1)
        data = self.connection.socket.recv(100000)
        if debug:
            return data
        # Data is returned in little endian double float format, interlacing x and y data.
        # Thus, we must first decode and split it up.
        data_decoded = self._decode_binary_block(data, dtype='<d')
        delays = data_decoded[0::2] * 1e-12
        ys = data_decoded[1::2]
        return delays, ys
