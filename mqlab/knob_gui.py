""" Quick and simple digital knob interface for remote control of instruments using arrow keys. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import numpy as np
import sys

# Import appropriate Qt GUI toolkit (depending on availability and py2/3)
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout


class KnobGui(QWidget):
    def __init__(self):
        super().__init__()

        #######################
        # Device Configuration
        from mqlab.power_supplies import HP6653A
        self.device = HP6653A(interface='gpib-ethernet', gpib_address=4, max_current_A=5)
        self.value = self.device.get_current()
        self.limits = (0, 9.5)
        #######################

        # GUI window sizing and positions
        x = 500  # x position
        y = 200  # y position
        w = 100  # width
        h = 200  # height
        self.setGeometry(x, y, w, h)

        # Display value as string, formbatted to highlight the currently selected digit
        self.digit_idx = 4

        # Define dictionary mapping the selected digit index to the magnitude
        self.digit_magnitude = [1, 0, 0.1, 0.01, 0.001]

        self.value_label = QLabel('', self)
        self.value_label.show()

        self.update_label()

        layout = QVBoxLayout()

        # Add the widgets to the layout
        layout.addWidget(self.value_label)

        # Set layout as the layout for the window
        self.setLayout(layout)

    def show_and_raise(self):
        self.show()
        self.raise_()

    def change_selected_digit(self, direction):
        if direction == 'left':
            self.digit_idx = max(0, self.digit_idx - 1)
            # Skip over decimal points
            if self.digit_idx == 1:
                self.digit_idx = 0

        elif direction == 'right':
            self.digit_idx = min(self.digit_idx + 1, len(self.value_string) - 1)
            # Skip over decimal points
            if self.digit_idx == 1:
                self.digit_idx = 2
        self.update_label()

    def change_digit_value(self, direction):
        """ Direction is +1 or -1. """
        # Increment / decrement the value
        self.value += direction * self.digit_magnitude[self.digit_idx]
        # Enforce limits
        self.value = np.clip(self.value, *self.limits)
        # Send value to device
        self.device.set_current(self.value)
        self.update_label()

    def update_label(self):
        # Convert float to str with 3 decimal places
        self.value_string = '{:0.3f}'.format(self.value)

        # Format str with colour to highlight currently selected digit
        coloured_value_string = '<font color="black">{}</font><font color="red">{}</font><font color="black">{}</font>'.format(self.value_string[:self.digit_idx], self.value_string[self.digit_idx], self.value_string[self.digit_idx + 1:])
        self.value_label.setText('<h1>Current (A): {}</h1>'.format(coloured_value_string))

    def keyPressEvent(self, evt):
        key = evt.key()

        if key == QtCore.Qt.Key_Left:
            self.change_selected_digit(direction='left')

        elif key == QtCore.Qt.Key_Right:
            self.change_selected_digit(direction='right')

        elif key == QtCore.Qt.Key_Up:
            self.change_digit_value(direction=+1)

        elif key == QtCore.Qt.Key_Down:
            self.change_digit_value(direction=-1)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    win = KnobGui()
    win.show_and_raise()

    sys.exit(app.exec_())
