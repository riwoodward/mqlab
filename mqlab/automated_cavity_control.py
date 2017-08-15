from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import numpy as np
import time
import sys

from mqlab.oscilloscopes import TektronixTDS794D
from mqlab.optical_spectrum_analysers import YokogawaAQ6376
from mqlab.optomechanics import ThorlabsK10CR1


class AutomatedCavityControl():
    """ Class for automatng, and ultimately using machine learning to optimize, fibre laser cavity dynamics. """

    LASER_SETTLE_TIME = 1  # time before making measurements after setting waveplates

    def __init__(self):
        pass

    def initialise_waveplates(self):
        """ Connect to waveplate and home them. """
        self.hwp = ThorlabsK10CR1(serial='55000359')
        self.qwp = ThorlabsK10CR1(serial='55000360')

        self.hwp.home()
        self.qwp.home()
        time.sleep(0.2)

        print('Homing waveplates... please wait...')
        hwp_moving = True
        qwp_moving = True
        while (qwp_moving or hwp_moving):
            time.sleep(0.3)
            hwp_moving = self.hwp.is_moving
            time.sleep(0.3)
            qwp_moving = self.qwp.is_moving
        print('QWP and HWP homed.')

    def initialise_diagnostics(self):
        """ Connect to relevant diagnostics. """
        self.osa = YokogawaAQ6376(mq_id='YokogawaAQ6376', interface='ethernet')
        self.osc = TektronixTDS794D(mq_id='TektronixTDS794D', interface='gpib-ethernet')

    def sequential_scan(self, hwp_range=[0, 180], hwp_resolution=10, qwp_range=[0, 180], qwp_resolution=10):
        """ Sequentially explore parameter space. """
        hwp_angles = np.arange(min(hwp_range), max(hwp_range) + hwp_resolution, hwp_resolution)
        qwp_angles = np.arange(min(qwp_range), max(qwp_range) + qwp_resolution, qwp_resolution)

        # Initial grab for dimensioning
        osa_x, osa_y = self.osa.grab()
        osc_x, osc_y = self.osc.grab(channel='3')

        num_iterations = len(hwp_angles) * len(qwp_angles)
        osa_ys = np.zeros([num_iterations, len(osa_x)], dtype=float)
        osc_ys = np.zeros([num_iterations, len(osc_x)], dtype=float)
        labels = np.zeros(num_iterations, dtype=np.chararray)

        print(f'\nStarting sequential scan from HWP={hwp_angles.min()}-{hwp_angles.max()} (res={hwp_resolution}) & QWP={qwp_angles.min()}-{qwp_angles.max()} (res={qwp_resolution}):')

        measurement_idx = 0
        for hwp_angle in hwp_angles:
            self.hwp.move_to(hwp_angle, wait_until_complete=True)

            for qwp_angle in qwp_angles:
                sys.stdout.write(f'\rHWP = {hwp_angle} deg, QWP = {qwp_angle} deg            ')

                self.qwp.move_to(qwp_angle, wait_until_complete=True)

                # Let laser settle
                time.sleep(self.LASER_SETTLE_TIME)

                # Grab from both (TODO: thing about sending a run sweep command)
                osa_x, osa_y = self.osa.grab()
                osc_x, osc_y = self.osc.grab(channel='3')

                osa_ys[measurement_idx] = osa_y
                osc_ys[measurement_idx] = osc_y
                labels[measurement_idx] = f'HWP={hwp_angle} & QWP={qwp_angle}'

                measurement_idx += 1

        # Output the data
        np.savetxt('data_osa_x.txt', osa_x, header='Data from OSA')
        np.savetxt('data_osa.txt', osa_ys, header=f'OSA Data, osa_measurement_length={len(osa_x)}')
        np.savetxt('data_osc_x.txt', osc_x, header='Data from OSC')
        np.savetxt('data_osc.txt', osc_ys, header=f'OSC Data, osc_measurement_length={len(osc_x)}')
        np.savetxt('data_labels.txt', labels, fmt="%s")


if __name__ == '__main__':

    cavity = AutomatedCavityControl()
    cavity.initialise_waveplates()
    cavity.initialise_diagnostics()

    cavity.sequential_scan(hwp_range=[0, 180], hwp_resolution=90, qwp_range=[0, 180], qwp_resolution=90)
