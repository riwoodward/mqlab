**MQ Lab - Instrument Control Code**
######################################

Instrumentation interfacing & control code for MQ Mid-IR Fibre Lasers Group.

* All devices are based on underlying communication classes (in ``connections.py``), determined by their connection type (GPIB, Serial, Ethernet or USB). See docstring of ``connections.py`` for discussion of networking protocols and the python packages used for each.
* Each lab device is assigned a unique ID (in ``mq_instruments.txt``) which defines commuication defaults (address, baud rate etc) for simplifying access to them.
* Each device type should be a class, with specific devices created as subclasses.
* GUIs / more specialised interfacing code are separate python files, which create instances of device classes as required.
* ``gui.py`` is a (continually growing) attempt to build a single interface for interfacing with all commonly used metrological equipment.

Installation
-------------
MQ Lab has been tested with Windows, Mac and Ubuntu and should work using Python 2 or Python 3. It is recommended to use the latest Python version (v3.6), however.

To install MQLab, open a terminal / command prompt window (with current folder path as this folder) and run::

    $ python setup.py install

This copies all source files to the main Python site-packages directory.

Alternatively, if you expect to modify MQ Lab code manually, you can install it and still leave the source files in the current folder for quick and easy editing. In this case, instead of the above, run::

    $ python setup.py develop

Usage
-----
The instrument classes can be imported and used in custom code as required (see docstrings for examples).

For quick access to core data grabbing, plotting and analysis tools in a GUI, run::

    $ python gui.py


General Code Structure
----------------------
* ``connections.py`` : master code to establish common interface for all connection protocols (GPIB, RS232, Ethernet, USB etc.)

* device drivers are saved in files according to the device type

* ``gui.py`` : graphical interface for quick access to grab, plot and analysis functions

* ``utils.py`` : misc. scripts for data handling and processing

* ``mq_instruments.txt`` : configuration file containing default settings for MQ lab instruments


.. image:: https://raw.githubusercontent.com/riwoodward/mqlab/master/mqlab/resources/gui_screenshot.jpg
        :width: 50%
