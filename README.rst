**MQ Lab - Instrument Control Code**
######################################

Instrumentation interfacing & control code for MQ Mid-IR Photonics Group.

* All devices are based on underlying communication classes (in connections.py), determined by their connection type (GPIB, Serial, Ethernet or USB). See docstring of connections.py for discussion of networking protocols and the python packages used for each.
* Each device type should be a class, with specific devices created as subclasses.
* GUIs / more specialised interfacing code are separate python files, which create instances of device classes as required.
* ``gui.py`` is a (continually growing) attempt to build a single interface for interfacing with all commonly used metrological equipment.

Installation
-------------
Python is required (should work on all versions and operating systems). Recommended to install the latest version (v3.6) using the handy Anaconda Python distribution.

To install MQLab, open a terminal / command prompt window (with current folder path as this folder) and run::
    $ python setup.py install


Usage
-----
The instrument classes can be imported and used in custom code as required.

For quick access to core data grabbing, plotting and analysis tools in a GUI, run::
    $ python gui.py


General Code Structure
----------------------
* ``connections.py`` : master code to establish common interface for all connection protocols (GPIB, RS232, Ethernet, USB etc.)

* device drivers are saved in files according to the device type

* ``gui.py`` : graphical interface for quick access to grab, plot and analysis functions

* ``utils.py`` : misc. scripts for data handling and processing

* ``mq_instruments.txt`` : configuration file containing default settings for MQ lab instruments

