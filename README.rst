**MQ Lab - Instrument Control Code**
######################################

Instrumentation interfacing & control code for MQ Mid-IR Photonics Group.
Still very much a work in progress as new devices are added.

General structure:
- connections.py : master code to establish common interface for all connection protocols (GPIB, RS232, Ethernet, USB etc.)
- device drivers are saved in files according to the device type
- gui.py : graphical interface for quick access to grab, plot and analyse functions
- utils.py : misc. scripts for data handling and processing
- mq_instruments.txt: configuration file containing default settings for MQ lab instruments

Installation instructions:
- Python is required (should work on all versions and operating systems). Recommended to install the latest version (v3.6) using the handy Anaconda Python distribution.
- To install automatically, open windows command prompt (with current folder as this folder) and type "python setup.py install"
- To run the GUI, type "python gui.py"

TODO:
- create exe installer