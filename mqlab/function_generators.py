""" Definition of function generator interfacing commands. """
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

    def set_square_modulation_waveform(self, duty_cycle, num_points=2000, min_level = 0, max_level=2**14-2, silent=False):
        """ Set a square modulation waveform into the memory (e.g. for using as modulation shape).

        Args:
            duty_cycle : on-to-off ratio (0 to 1)
            num_points : number of samples to define waveform (0 to 131072)
        Notes:
            Empirically, it seems that >4000 points can produce waveforms with wrong duty cycle
            (even though they look correct on the AM waveform shown on the device screen)
        """
        # Set memory size
        self.send('DATA:POIN EMEM,' + str(num_points))

        # Set everything to zero
        define_zero_line_command = f'DATA:DATA:LINE EMEMory,1,{min_level},{num_points},{min_level}'
        self.send(define_zero_line_command)

        # Compute lines
        transition_point = int(num_points * duty_cycle)
        self.duty_cycle = duty_cycle
        define_on_line_command = f'DATA:DATA:LINE EMEMory,1,{max_level},{transition_point},{max_level}'
        define_on_to_off_line_command = f'DATA:DATA:LINE EMEMory,{transition_point},{max_level},{transition_point+1},{min_level}'
        self.send(define_on_line_command)
        self.send(define_on_to_off_line_command)

        # Print ON cycle information if not silenced
        if not silent:
            am_freq = self.get_AM_modulation_frequency()
            on_time = 1 / am_freq * duty_cycle
            print(f'Set {100 * duty_cycle:.1f}% duty cycle at {am_freq} Hz: {on_time * 1e6:.1f} us ON time')

    def set_AM_modulation_frequency(self, frequency, maintain_on_time=False):
        """ Set AM modulation frequency (Hz).

        Args:
            maintain_on_time : if True, the duty cycle will be adjusted to keep the absolute ON time the same as before
        """
        if maintain_on_time:
            existing_period = 1 / self.get_AM_modulation_frequency()
            new_period = 1 / frequency
            new_duty_cycle = self.duty_cycle * existing_period / new_period
            # Update AM frequency
            self.send(f'SOURce1:AM:INTernal:FREQuency {frequency}Hz')
            # Update duty cycle
            num_points = self.query('DATA:POIN? EMEM', dtype=int)
            self.set_square_modulation_waveform(duty_cycle=new_duty_cycle, num_points=num_points)
        else:
            self.send(f'SOURce1:AM:INTernal:FREQuency {frequency}Hz')

    def get_AM_modulation_frequency(self):
        """ Get AM modulation frequency (Hz). """
        return self.query('SOURce1:AM:INTernal:FREQuency?', dtype=float)


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
