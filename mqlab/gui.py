""" GUI for grabbing data and plotting / analysis using MQ instruments. """
# Import interface code for MQ instruments
import mqlab.optical_spectrum_analysers as mq_osa
import mqlab.oscilloscopes as mq_osc
import mqlab.electrical_spectrum_analysers as mq_esa
import mqlab.monochromators as mq_monochromator
import mqlab.optomechanics as mq_optomechanics
import mqlab.lock_in_amplifiers as mq_lockin
import mqlab.autocorrelators as mq_ac

import mqlab.utils as ut
from mqlab.connections import mq_instruments_config_filepath
# General Imports
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import sys, os, time, traceback, itertools, datetime
from scipy.integrate import trapz
from glob import glob
from collections import OrderedDict
from threading import Thread
import socket
from configparser import ConfigParser
from PyQt5 import QtCore, Qt
from PyQt5.QtCore import QObject, QThread, QSize, pyqtSlot, pyqtSignal
from PyQt5.QtGui import QPixmap, QTextCursor, QIcon, QKeySequence, QColor, QBrush, QPalette, QImage, QTextBlockFormat
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QGroupBox, QHBoxLayout, QVBoxLayout, QRadioButton, QSpinBox, QDoubleSpinBox, QFormLayout, QCheckBox, QComboBox, QLineEdit, QSplitter, QFileDialog, QInputDialog, QMainWindow, QPushButton, QToolButton, QSizePolicy, QTextEdit, QAction, QMessageBox, QTabWidget, QFrame, QDockWidget, QTreeWidget, QMenu, QTabBar, QListWidget, QAbstractItemView, QStyle, QGridLayout, QShortcut
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
# Import Vxi11 Exception for helpful error catching (if user has grabbing library installed)
from vxi11.vxi11 import Vxi11Exception

# Set plot styling
matplotlib.rcParams['font.size'] = 16


class MainWindow(QMainWindow):
    """ Generalised data grab / analysis GUI.
    Qt naming convention suggests camelCaps. These are used for GUI objects here, whereas underscore_convention is used for all other objects. """

    def __init__(self):
        super().__init__()

        # Init useful globals
        self.global_i = 0  # Global counter for consistent formatting etc
        self.live_view_active = False  # Status of Live View functionality
        self.x_max = 0  # Custom span (default to null)
        self.x_min = 0
        self.savefig_dpi = 50

        # Save the absolute resources folder location (in Unix "/" separator format)
        self.resources_folder = os.path.dirname(os.path.realpath(__file__)) + '/resources/'
        self.resources_folder = self.resources_folder.replace('\\', '/')

        # Set application icon
        self.setWindowIcon(QIcon(self.resources_folder + 'icon.ico'))

        # Set window background color to white
        palette = QPalette()
        palette.setColor(QPalette.Background, QColor(255, 255, 255))
        self.setPalette(palette)

        # Initialise hardware and GUI options
        self.load_config_file()
        self.initialise_hardware_options()

        # Build window widgets and layout
        self.createLayout()
        self.createStatusBar()

        # Define window geomtry
        self.setWindowTitle('MQ Lab GUI')
        x_pos = 100
        y_pos = 100
        width = 800
        height = 650
        self.setGeometry(x_pos, y_pos, width, height)
        self.setUnifiedTitleAndToolBarOnMac(True)

    def load_config_file(self):
        """ Load settings from config.ini file. """
        config_filepath = os.path.dirname(os.path.realpath(__file__)) + '/config_gui.ini'
        config_filepath = config_filepath.replace('\\', '/')
        config = ConfigParser()

        # If config file doesn't exist, create it with default settings
        if os.path.isfile(config_filepath):
            config.read(config_filepath)
            self.automatically_save_plots_to_disk = config['gui'].getboolean('automatically_save_plots_to_disk')
        # Otherwise, create a new config file with default settings
        else:
            self.automatically_save_plots_to_disk = True
            config['gui'] = {'automatically_save_plots_to_disk': 'True'}
            with open('config_gui.ini', 'w') as f:
                f.write('# Configuration file for global MQ Lab GUI settings\n')
                config.write(f)

    def initialise_hardware_options(self):
        """ Load GPIB instrument database. """
        self.units = {'osa': 'm', 'osc': 's', 'pdd': 's', 'esa': 'Hz'}

        config = ConfigParser()
        config.read(mq_instruments_config_filepath)

        self.OSAs = []
        self.OSCs = []
        self.ESAs = []
        self.PDDs = []

        for device_id in config.sections():
            device_type = config[device_id]['device_type']
            if device_type == 'osa':
                self.OSAs.append(device_id)
            elif device_type == 'osc':
                self.OSCs.append(device_id)
            elif device_type == 'esa':
                self.ESAs.append(device_id)
            elif device_type == 'pdd':
                self.PDDs.append(device_id)

        # Sort device lists alphabetically
        self.OSAs.sort()
        self.OSCs.sort()
        self.ESAs.sort()
        self.PDDs.sort()

    def initialise_colors(self):
        """ Initialise / reset the color cycle (use matplotlib2.0 colour cycle). """
        colors = ('C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9')
        self.colors = itertools.cycle(colors)

    def createLayout(self):
        """ Build overall GUI layout. """
        self.createRibbonLayout()
        self.createPlotsLayout()

        self.masterLayout = QSplitter(QtCore.Qt.Vertical)
        self.masterLayout.addWidget(self.ribbon)
        self.masterLayout.addWidget(self.plotTabs)

        self.masterLayout.setStretchFactor(0, 0)  # Disallow ribbon area from expanding on window resize
        self.masterLayout.setStretchFactor(1, 20)  # Disallow ribbon area from expanding on window resize

        self.setCentralWidget(self.masterLayout)

    def createPlotsLayout(self):
        # Create figure, canvas and toolbar, with a tabbed interface supporting numerous figure tabs
        self.plotTabs = QTabWidget(self)
        self.plotTabs.currentChanged.connect(self.plotTabChanged)
        self.plotTabs.setTabPosition(QTabWidget.East)
        self.plotTabs.tabCloseRequested.connect(self.plotTabCloseRequested)
        self.tabJustDeleted = False  # Useful flag

        # Create dictionary mapping the tab index to plot index (not necessarily linear since we expect random user opening and closing of tabs)
        self.plots = dict()
        self.plotNumbers = dict()
        self.global_plot_i = 1
        self.newPlotTab(newIndex=0)

        # Add "Add New Tab" tab
        self.plotTabs.addTab(QWidget(self.plotTabs), '+')

        # Allow closable tabs, apart from Fig 1 and the + icon
        self.plotTabs.setTabsClosable(True)
        self.plotTabs.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.plotTabs.tabBar().setTabButton(1, QTabBar.RightSide, None)

    def newPlotTab(self, newIndex=None):
        """ Create tab for a new figure in the plots area. """
        if newIndex is not None:
            tabIndex = newIndex
        else:
            tabIndex = self.plotTabs.count() - 1
        self.plotNumbers[tabIndex] = self.global_plot_i
        self.plots[tabIndex] = QWidget(self.plotTabs)
        self.plots[tabIndex].figure = plt.Figure()
        self.plots[tabIndex].canvas = FigureCanvas(self.plots[tabIndex].figure)
        self.plots[tabIndex].toolbar = NavigationToolbar(self.plots[tabIndex].canvas, self.plotTabs)

        # Create axis
        self.plots[tabIndex].ax = self.plots[tabIndex].figure.add_subplot(111)
        self.initialise_colors()

        # Tighten the canvas and neaten up
        self.plots[tabIndex].figure.tight_layout()

        # Set the default background color
        self.plots[tabIndex].figure.set_facecolor('white')

        # Set layout of widget
        layout = QVBoxLayout()
        layout.addWidget(self.plots[tabIndex].canvas)
        layout.addWidget(self.plots[tabIndex].toolbar)
        self.plots[tabIndex].setLayout(layout)

        # Define resizing conditions to permit stretching
        self.plots[tabIndex].canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plots[tabIndex].toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.plotTabs.insertTab(newIndex, self.plots[tabIndex], 'Fig %i' % self.global_plot_i)
        self.global_plot_i += 1

    def plotTabChanged(self, newIndex):
        """ If user chooses the "+" for adding a new tab, insert this and give focus correctly. """
        if self.tabJustDeleted is True:
            self.tabJustDeleted = False
        else:
            numTabs = self.plotTabs.count() - 1
            if (newIndex == numTabs) and (newIndex > 0):
                self.newPlotTab(newIndex=newIndex)
                self.plotTabs.setCurrentIndex(newIndex)

        self.tab_idx = self.plotTabs.currentIndex()
        self.setStatusBar('Ready')

        # Since the fitting buttons act on the current data in fileList box and NOT the data in the plot (which may be from a previous interaction), disable fitting routines
        self.fittingBox.setEnabled(False)

    def plotTabCloseRequested(self, currentIndex):
        """ Delete a tab and its contents (to free up memory). """
        self.tabJustDeleted = True

        # Ripple widgets to fill up index space
        temp = self.plots.copy()
        for i in range(self.plotTabs.count()-2):
            if i >= currentIndex:
                self.plots[i] = temp[i+1]
        self.plotTabs.removeTab(currentIndex)

    def createRibbonLayout(self):
        """ Create the ribbon widgets and layout, consistent of three main tabs. """
        self.ribbon = QTabWidget(self)
        self.ribbon.currentChanged.connect(self.ribbonTabChanged)

        self.grabTab = QWidget(self.ribbon)
        self.plottingTab = QWidget(self.ribbon)
        self.advancedTab = QWidget(self.ribbon)
        self.spectrometerTab = QWidget(self.ribbon)
        self.autocorrelatorTab = QWidget(self.ribbon)

        # Assign custom names to these objects, so the stylesheet can uniquely set their background (without forced inheritance affecting all children)
        self.grabTab.setObjectName('tabContentsBackground')
        self.plottingTab.setObjectName('tabContentsBackground')
        self.advancedTab.setObjectName('tabContentsBackground')
        self.spectrometerTab.setObjectName('tabContentsBackground')
        self.autocorrelatorTab.setObjectName('tabContentsBackground')

        # Create interface for each tab
        self.grabTabUI()
        self.plottingTabUI()
        self.advancedTabUI()
        self.spectrometerTabUI()
        self.autocorrelatorTabUI()

        self.ribbon.addTab(self.grabTab, ' Data Grab ')
        self.ribbon.addTab(self.plottingTab, ' Plotting ')
        self.ribbon.addTab(self.advancedTab, ' Advanced ')
        self.ribbon.addTab(self.spectrometerTab, ' MQ Spectrometer ')
        self.ribbon.addTab(self.autocorrelatorTab, ' MQ Autocorrelator ')

        # Apply Style Sheet
        stylesheet_filepath = self.resources_folder + 'lab_gui_stylesheet.qss'
        style_sheet_string = open(stylesheet_filepath).read()
        style_sheet_string = style_sheet_string.replace('resources/', self.resources_folder)  # Manually ensure the resource folder points to correct directory
        self.ribbon.setStyleSheet(style_sheet_string)

    def ribbonTabChanged(self, newIndex):
        """ When user changes the current ribbon tab, position the filesList widget in either the Plotting or Advanced Tab, depending on which has focus. """
        if newIndex == 1:
            self.filesWidget.setLayout(self.filesWidgetLayout)
        if newIndex == 2:
            self.filesWidgetAdvancedTab.setLayout(self.filesWidgetLayout)

    def createRibbonBtn(self, parent, onPushMethod, text, icon_filepath, icon_size=25, icon_pos='left', btn_type='toolbutton'):
        """ Create button for the ribbon. If Qt toolbutton is used, there's more flexibility in configuration, but for nicely centred text/icons, Qt pushbuttons are easier. """
        if btn_type == 'toolbutton':
            btn = QToolButton(parent)
            icon_pos_dict = {'left': QtCore.Qt.ToolButtonTextBesideIcon, 'bottom': QtCore.Qt.ToolButtonTextUnderIcon}
            btn.setToolButtonStyle(icon_pos_dict[icon_pos])
        else:
            btn = QPushButton(parent)
        btn.setText(text)
        btn.setIcon(QIcon(icon_filepath))
        btn.setIconSize(QtCore.QSize(icon_size, icon_size))
        btn.clicked.connect(onPushMethod)
        btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)  # Stretch to fill space
        return btn

    def grabTabUI(self):
        """ Create interface for Tab #1: the grabbing tools. """
        layout = QHBoxLayout(self.grabTab)
        hardwareLayout = QVBoxLayout()
        hardwareBoxesLayout = QHBoxLayout()

        # LOGO AND GLOBAL SETTINGS FRAME #
        logoFrame = QFrame(self.grabTab)
        logoFrameLayout = QVBoxLayout(logoFrame)
        mqLogo = QLabel(logoFrame)
        logoPixmap = QPixmap(os.path.dirname(os.path.abspath(__file__)) + '/resources/mq_logo.png')
        mqLogo.setPixmap(logoPixmap)
        mqLogo.setAlignment(QtCore.Qt.AlignCenter)

        grabSettings = QWidget(self.grabTab)
        grabSettingsLayout = QFormLayout(grabSettings)
        self.grabMode = QComboBox()
        self.grabMode.addItems(['Grab', 'Live View'])
        self.connectionType = QComboBox()
        self.connectionType.addItems(['GPIB-Ethernet', 'GPIB-USB', 'Ethernet', 'USB'])
        self.location = QComboBox()
        self.location.addItems(['Hearing Hub', 'Engineering I', 'Engineering II'])
        grabSettingsLayout.addRow('Mode:', self.grabMode)
        grabSettingsLayout.addRow('Conn.:', self.connectionType)
        grabSettingsLayout.addRow('Lab:', self.location)

        logoFrameLayout.addWidget(mqLogo)
        logoFrameLayout.addWidget(grabSettings)

        # OSA FRAME #
        osaFrame = QGroupBox('Optical Spectrum', self.grabTab)
        osaFrameLayout = QVBoxLayout(osaFrame)
        self.osaCmb = QComboBox()
        self.osaCmb.addItems(self.OSAs)

        channelChoice = QWidget(osaFrame)
        channelChoiceLayout = QHBoxLayout(channelChoice)
        self.osaCh1 = QRadioButton('A')
        self.osaCh2 = QRadioButton('B')
        self.osaCh3 = QRadioButton('C')
        self.osaCh1.setChecked(True)
        channelChoiceLayout.addWidget(QLabel('Channel:'))
        channelChoiceLayout.addWidget(self.osaCh1)
        channelChoiceLayout.addWidget(self.osaCh2)
        channelChoiceLayout.addWidget(self.osaCh3)

        grabOsaBtn = self.createRibbonBtn(parent=osaFrame, onPushMethod=lambda: self.onPushGrabBtn(target=self.grab_osa), text='   &Grab', icon_filepath=self.resources_folder + 'icon_optical_spectrum.png', icon_size=30, btn_type='pushbutton')

        osaFrameLayout.addWidget(self.osaCmb)
        osaFrameLayout.addWidget(channelChoice)
        osaFrameLayout.addWidget(grabOsaBtn)

        ## OSC FRAME ##
        oscFrame = QGroupBox('Oscilloscope Trace', self.grabTab)
        oscFrameLayout = QVBoxLayout(oscFrame)
        self.oscCmb = QComboBox()
        self.oscCmb.addItems(self.OSCs)

        channelChoice = QWidget(oscFrame)
        channelChoiceLayout = QHBoxLayout(channelChoice)
        self.oscCh1 = QRadioButton('1')
        self.oscCh2 = QRadioButton('2')
        self.oscCh3 = QRadioButton('3')
        self.oscCh4 = QRadioButton('4')
        self.oscCh1.setChecked(True)
        channelChoiceLayout.addWidget(QLabel('Ch:'))
        channelChoiceLayout.addWidget(self.oscCh1)
        channelChoiceLayout.addWidget(self.oscCh2)
        channelChoiceLayout.addWidget(self.oscCh3)
        channelChoiceLayout.addWidget(self.oscCh4)


        grabOscBtn = self.createRibbonBtn(parent=osaFrame, onPushMethod=lambda: self.onPushGrabBtn(target=self.grab_osc), text='   G&rab', icon_filepath=self.resources_folder + 'icon_temporal_trace.png', icon_size=30, btn_type='pushbutton')

        oscFrameLayout.addWidget(self.oscCmb)
        oscFrameLayout.addWidget(channelChoice)
        oscFrameLayout.addWidget(grabOscBtn)

        ## ESA FRAME ##
        esaFrame = QGroupBox('Electrical Spectrum', self.grabTab)
        esaFrameLayout = QVBoxLayout(esaFrame)
        self.esaCmb = QComboBox()
        self.esaCmb.addItems(self.ESAs)
        self.esaCmb.currentIndexChanged.connect(self.onEsaCmbChanged)

        self.esaSettings = QWidget(self.grabTab)
        esaSettingsLayout = QFormLayout(self.esaSettings)
        esaFrameLayout.setSpacing(0)  # Minimise padding to avoid making ribbon too thick

        grabEsaBtn = self.createRibbonBtn(parent=esaFrame, onPushMethod=lambda: self.onPushGrabBtn(target=self.grab_esa), text='   Gr&ab', icon_filepath=self.resources_folder+'icon_electrical_spectrum.png', icon_size=30, btn_type='pushbutton')

        esaFrameLayout.addWidget(self.esaCmb)
        esaFrameLayout.addWidget(self.esaSettings)
        esaFrameLayout.addWidget(grabEsaBtn)

        ## PULSE DIAGNOSTIC DEVICE (pdd) ##
        pddFrame = QGroupBox('Pulse Diagnostics', self.grabTab)
        pddFrameLayout = QVBoxLayout(pddFrame)
        self.pddCmb = QComboBox()
        self.pddCmb.addItems(self.PDDs)
        self.pddCmb.currentIndexChanged.connect(self.onPddCmbChanged)

        self.pddSettingsStreakCam = QWidget(self.grabTab)
        pddSettingsStreakCamLayout = QHBoxLayout(self.pddSettingsStreakCam)
        self.streakCamTimebase = QLineEdit(pddFrame)
        pddSettingsStreakCamLayout.addWidget(QLabel('ns/div:'))
        pddSettingsStreakCamLayout.addWidget(self.streakCamTimebase)
        self.pddSettingsStreakCam.hide()

        self.pddSettingsAutocorrelator = QWidget(self.grabTab)

        grabPddBtn = self.createRibbonBtn(parent=pddFrame, onPushMethod=lambda: self.onPushGrabBtn(target=self.grab_pdd), text='   Gra&b', icon_filepath=self.resources_folder+'icon_pulse_diagnostic.png', icon_size=30, btn_type='pushbutton')

        pddFrameLayout.addWidget(self.pddCmb)
        pddFrameLayout.addWidget(self.pddSettingsStreakCam)
        pddFrameLayout.addWidget(self.pddSettingsAutocorrelator)
        pddFrameLayout.addWidget(grabPddBtn)

        ## FINALISE LAYOUT ##
        hardwareBoxesLayout.addWidget(osaFrame)
        hardwareBoxesLayout.addWidget(oscFrame)
        hardwareBoxesLayout.addWidget(esaFrame)
        hardwareBoxesLayout.addWidget(pddFrame)

        hardwareLayout.addLayout(hardwareBoxesLayout)

        saveDataBtn = self.createRibbonBtn(parent=self.grabTab, onPushMethod=self.onPushSaveDataBtn, text='   &Save Data', icon_filepath=self.resources_folder+'icon_save.png', icon_size=30, btn_type='pushbutton')

        hardwareLayout.addWidget(saveDataBtn)

        layout.addWidget(logoFrame)
        layout.addLayout(hardwareLayout)

    def onEsaCmbChanged(self):
        """ Show settings for ESA only if the Anritsu device is selected. """
        if 'Anritsu' in str(self.esaCmb.currentText()):
            self.esaSettings.show()
        else:
            self.esaSettings.hide()

    def onPddCmbChanged(self):
        """ Show appropriate settings depending on user's choice of pulse diagnostic device. """
        pass

    def plottingTabUI(self):
        """ Create widgets and layout for plotting tab. """
        layout = QHBoxLayout(self.plottingTab)

        ## FILE HANDLING ##
        self.filesWidget = QWidget(self.plottingTab)
        self.filesWidgetLayout = QVBoxLayout(self.filesWidget)

        filesBtnsLayout = QHBoxLayout()

        addFilesBtn = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=self.onPushAddFilesBtn, text='&Add Files', icon_filepath=self.resources_folder + 'icon_add.png', icon_size=25, icon_pos='left', btn_type='toolbutton')
        clearFilesBtn = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=self.onPushClearFilesBtn, text='&Clear Files', icon_filepath=self.resources_folder + 'icon_remove.png', icon_size=25, icon_pos='left', btn_type='toolbutton')
        clearPlotBtn = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=self.clear_plot, text='Clear &Plot', icon_filepath=self.resources_folder + 'icon_refresh.png', icon_size=25, icon_pos='left', btn_type='toolbutton')

        filesBtnsLayout.addWidget(addFilesBtn)
        filesBtnsLayout.addWidget(clearFilesBtn)
        filesBtnsLayout.addWidget(clearPlotBtn)

        # Files List Widget
        self.filesList = QListWidget()
        self.filesList.setMaximumHeight(110)
        self.filesList.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # Enable right click menu
        self.filesList.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.filesList.customContextMenuRequested.connect(self.onFilesListRightClick)

        self.filesWidgetLayout.addLayout(filesBtnsLayout)
        self.filesWidgetLayout.addWidget(self.filesList)

        ## PLOTTING AND CUSTOMISATION ##
        self.plotBtnAndCustomisationWidget = QWidget()
        plotBtnAndCustomisationLayout = QVBoxLayout(self.plotBtnAndCustomisationWidget)
        plottingBtnsLayout = QHBoxLayout()

        plotOpticalSpectrumBtn = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=self.plot_optical_spectrum, text='Plot\n&Optical Spectrum', icon_filepath=self.resources_folder + 'icon_optical_spectrum.png', icon_size=30, icon_pos='bottom', btn_type='toolbutton')
        plotTemporalTraceBtn = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=lambda: self.plot_temporal_trace(source='osc'), text='Plot\n&Temporal Trace', icon_filepath=self.resources_folder + 'icon_temporal_trace.png', icon_size=30, icon_pos='bottom', btn_type='toolbutton')
        plotElectricalSpectrumBtn = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=self.plot_electrical_spectrum, text='Plot\n&Electrical Spectrum', icon_filepath=self.resources_folder + 'icon_electrical_spectrum.png', icon_size=30, icon_pos='bottom', btn_type='toolbutton')

        plottingBtnsLayout.addWidget(plotOpticalSpectrumBtn)
        plottingBtnsLayout.addWidget(plotTemporalTraceBtn)
        plottingBtnsLayout.addWidget(plotElectricalSpectrumBtn)

        self.customBtns = QGroupBox('Customise Plots')
        self.customBtns.setCheckable(True)
        self.customBtns.setChecked(False)
        customBtnsLayout = QFormLayout(self.customBtns)

        self.rdbLog = QRadioButton('Log', self.customBtns)
        self.rdbLog.setChecked(True)
        self.rdbLin = QRadioButton('Lin', self.customBtns)
        loglin = QHBoxLayout()
        loglin.addWidget(self.rdbLog)
        loglin.addWidget(self.rdbLin)

        self.normalisePlot = QCheckBox()
        loglin.addWidget(QLabel('Normalised'))
        loglin.addWidget(self.normalisePlot)

        customBtnsLayout.addRow('Scale:', loglin)

        normAndStyleBox = QHBoxLayout()
        self.plotStyle = QLineEdit('-')
        normAndStyleBox.addWidget(QLabel('Plot Style'))
        normAndStyleBox.addWidget(self.plotStyle)
        customBtnsLayout.addRow(normAndStyleBox)

        plotBtnAndCustomisationLayout.addLayout(plottingBtnsLayout)
        plotBtnAndCustomisationLayout.addWidget(self.customBtns)

        ## FITTING ##
        self.fittingBox = QWidget()
        fittingLayout = QVBoxLayout(self.fittingBox)

        # Fitting Buttons
        fittingBtnsTopLayout = QFormLayout()
        dataFwhmBtn = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=self.onPushDataFwhmBtn, text=' Find F&WHM', icon_filepath=self.resources_folder+'icon_fwhm.png', icon_size=25, icon_pos='left', btn_type='toolbutton')
        dataCentreBtn = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=self.onPushDataCentreBtn, text=' Find Ce&ntre', icon_filepath=self.resources_folder+'icon_centre.png', icon_size=25, icon_pos='left', btn_type='toolbutton')
        dataIntegrate = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=self.onPushDataIntegrateBtn, text=' &Integrate', icon_filepath=self.resources_folder+'icon_integrate.png', icon_size=25, icon_pos='left', btn_type='toolbutton')
        dataPulseTrain = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=self.onPushDataPulseTrainBtn, text=' Pulse Train &Analysis', icon_filepath=self.resources_folder+'icon_pulse_train.png', icon_size=25, icon_pos='left', btn_type='toolbutton')

        fittingBtnsTopLayout.addRow(dataFwhmBtn, dataCentreBtn)
        fittingBtnsTopLayout.addRow(dataIntegrate, dataPulseTrain)

        # Shape Fitting
        shapeFittingBox = QGroupBox('Shape Fitting')
        shapeFittingLayout = QFormLayout(shapeFittingBox)

        self.shapeFitCmb = QComboBox(shapeFittingBox)
        self.shapeFitCmb.addItems(['Sech^2','Gaussian', 'Sech^2 (AC)', 'Gaussian (AC)'])
        self.shapeFitBtn = self.createRibbonBtn(parent=self.plottingTab, onPushMethod=self.onPushShapeFitBtn, text='&Fit Data', icon_filepath=self.resources_folder+'icon_fit.png', icon_size=25, icon_pos='left', btn_type='pushbutton')

        shapeFittingLayout.addRow('Shape', self.shapeFitCmb)
        shapeFittingLayout.addRow(self.shapeFitBtn)

        fittingLayout.addLayout(fittingBtnsTopLayout)
        fittingLayout.addWidget(shapeFittingBox)

        # Initially disable plotting fitting options
        self.fittingBox.setEnabled(False)
        self.plotBtnAndCustomisationWidget.setEnabled(False)

        ## FINALISE LAYOUT ##
        layout.addWidget(self.filesWidget)
        layout.addWidget(self.plotBtnAndCustomisationWidget)
        layout.addWidget(self.fittingBox)

    def onFilesListRightClick(self, QPos):
        """ Create pop-up menu for right click options in the files list. """
        self.listMenu= QMenu()
        menu_item = self.listMenu.addAction("Remove Item")
        if self.filesList.count() == 0: menu_item.setDisabled(True)  # Disable if no items in QListWidget
        menu_item.triggered.connect(self.removeClickedFile)
        parentPosition = self.filesList.mapToGlobal(QtCore.QPoint(0, 0))
        self.listMenu.move(parentPosition + QPos)
        self.listMenu.show()

    def removeClickedFile(self):
        """ When file(s) rigth clicked and remove selected in files list, delete these items. """
        for item in self.filesList.selectedItems():
            self.filesList.takeItem(self.filesList.row(item))

    def onPushAddFilesBtn(self):
        """ Open file dialog for user to select file(s) to plot. """
        file_paths = QFileDialog.getOpenFileNames(self, "Select data files ", filter="Data files (*.txt *.dat *.csv *.h5 *.bmData *.ProcSpec);;All files (*.*)")
        # There's a strange occurence where getOpenFileNames sometimes returns the extensions, and other times doesn't (perhaps Qt4/5 issue?). Catch this:
        if ('Data files' in file_paths[-1]) or ('All files' in file_paths[-1]):
            file_paths = file_paths[0]
        if type(file_paths) is list:  # If user presses ok (if cancel, empty string / tuple returned)
            for file_path in file_paths:
                self.filesList.addItem(file_path)

            self.save_file_name = os.path.splitext(os.path.split(file_path)[-1])[0]  # Set filename using last read datafile, which is used to save the plotted data as a png

            # Enable plotting buttons
            self.plotBtnAndCustomisationWidget.setEnabled(True)
            self.plotAdvancedBtns.setEnabled(True)

    def onPushClearFilesBtn(self):
        """ Clears the file list (self.filesList widget). """
        self.filesList.clear()
        # Disable plotting buttons
        self.plotBtnAndCustomisationWidget.setEnabled(False)
        self.plotAdvancedBtns.setEnabled(False)

    def advancedTabUI(self):
        """ Create widgets and layout for the advanced features tab. """
        layout = QHBoxLayout(self.advancedTab)

        ## FILE HANDLING (will be imported from basic plotting tab when the tabs are selected by user) ##
        self.filesWidgetAdvancedTab = QWidget(self.advancedTab)

        ## ADVANCED PLOTTING BUTTONS ##
        self.plotAdvancedBtns = QWidget()
        plotAdvancedBtnsLayout = QHBoxLayout(self.plotAdvancedBtns)

        plotTransmissionBtn = self.createRibbonBtn(parent=self.advancedTab, onPushMethod=self.onPushPlotTransmissionBtn, text='Plot\nTransmission', icon_filepath=self.resources_folder+'icon_transmission.png', icon_size=35, icon_pos='bottom', btn_type='toolbutton')
        plotBeamProfileBtn = self.createRibbonBtn(parent=self.advancedTab, onPushMethod=self.onPushPlotBeamProfileBtn, text='Plot\nBeam Profile', icon_filepath=self.resources_folder+'icon_beam_profile.png', icon_size=35, icon_pos='bottom', btn_type='toolbutton')
        plotPowerScanBtn = self.createRibbonBtn(parent=self.advancedTab, onPushMethod=self.OnPushPlotPowerScanBtn, text='Plot\nPower Scan', icon_filepath=self.resources_folder+'icon_power.png', icon_size=35, icon_pos='bottom', btn_type='toolbutton')
        plotTemperatureScanBtn = self.createRibbonBtn(parent=self.advancedTab, onPushMethod=self.onPushPlotTemperatureScanBtn, text='Plot\nTemperature Scan', icon_filepath=self.resources_folder+'icon_temperature.png', icon_size=35, icon_pos='bottom', btn_type='toolbutton')

        plotAdvancedBtnsLayout.addWidget(plotTransmissionBtn)
        plotAdvancedBtnsLayout.addWidget(plotBeamProfileBtn)
        plotAdvancedBtnsLayout.addWidget(plotPowerScanBtn)
        plotAdvancedBtnsLayout.addWidget(plotTemperatureScanBtn)

        self.plotAdvancedBtns.setEnabled(False)  # Initially, disable plotting buttons until files selected

        ## NETWORK SETTINGS BUTTONS ##
        settingBtns = QGroupBox('Settings')
        settingBtnsLayout = QVBoxLayout(settingBtns)

        viewDevicesBtn = self.createRibbonBtn(parent=self.advancedTab, onPushMethod=self.onPushViewGpibAddressesBtn, text='Configure\n Devices', icon_filepath=self.resources_folder + 'icon_network.png', icon_size=30, icon_pos='left', btn_type='toolbutton')

        settingBtnsLayout.addWidget(viewDevicesBtn)

        layout.addWidget(self.filesWidgetAdvancedTab)
        layout.addWidget(self.plotAdvancedBtns)
        layout.addWidget(settingBtns)

    #####################
    # GUI FUNCTIONALITY #
    #####################

    def data_grab_preparation(self, device_type):
        """ Misc utils to prepare for data grabbing. """
        # Save relevant arguments into dictionary
        kwargs = dict()

        id_dict = {'osa': self.osaCmb.currentText(), 'osc': self.oscCmb.currentText(), 'esa': self.esaCmb.currentText(), 'pdd': self.pddCmb.currentText()}
        kwargs['mq_id'] = id_dict[device_type]
        kwargs['interface'] = self.connectionType.currentText()
        kwargs['gpib_location'] = self.location.currentText()

        interface = self.connectionType.currentText()

        if (('usb' in interface) or ('serial' in interface)):
            kwargs['com_port'] = self.acComPort.text()  # Prepare arguments for a serial-based instrument connection (default to using the first found COM port)

        self.filesList.clear()  # Remove all files from plotting list
        self.filesList.addItem('Data Grab (%s)    ' % datetime.datetime.now().strftime('%H:%M:%S'))  # Add line to plotting list to indicate instrument access
        return kwargs

    def clear_plot(self, skip_update_canvas=True):
        """ Refresh button: reset matplotlib figure axes. """
        self.save_file_name = ''  # Blank canvas title
        self.plots[self.tab_idx].ax.clear()

        if not skip_update_canvas:
            self.plots[self.tab_idx].figure.canvas.draw()

        self.global_i = 0
        self.initialise_colors()  # Reset colour cycle
        self.get_span_coords(0, 0)

        # Disable fitting controls as not data to fit to
        self.fittingBox.setEnabled(False)

    def onPushGrabBtn(self, target):
        """ Grab data from instrument, where target is the instrument grab function """
        # If live-view mode: then toggle start / stop action depending if Live View is active (using threads).
        # Otherwise, run as a single function
        if self.grabMode.currentText() == 'Grab':
            target()
        else:
            if self.live_view_active:
                self.live_view_active = False
            else:
                self.grab_thread = Thread(target=target)
                self.live_view_active = True
                self.grab_thread.start()

    def plot_scale_log_or_lin(self):
        """ Convenience function: returns 'log' or 'lin' depending on state of the Log/Lin radio buttons. """
        if self.rdbLog.isChecked():
            return 'log'
        elif self.rdbLin.isChecked():
            return 'lin'

    def instrument_data_grab(self, device, **kwargs):
        """ Convenience function to grab data from a device class and handle errors.

        Returns None on the case of an error.
        """
        try:
            data = device.grab(**kwargs)
            return data
        except socket.error as e:
            self.show_error_dialog('Socket error: %s.\n\nCheck the computer is on the MQ ethernet network and retry.' % e)
        except Vxi11Exception as e:
            self.show_error_dialog('VXI11 error: %s.\n\nComputer can see the VXI11 GPIB-to-Ethernet server, but cannot contact the requested instrument by GPIB. Check connections and retry. Restart the GPIB-to-Ethernet server if problems persist.' % e)
        except Exception as e:
            self.show_error_dialog('Error: %s.' % e)

        traceback.print_exc()
        return None

    def grab_osa(self):
        """ Function / thread for grabbing and displaying OSA trace data. """
        # Initialise OSA for grabbing
        kwargs = self.data_grab_preparation('osa')
        if 'YokogawaAQ' in kwargs['mq_id']:
            osa = mq_osa.YokogawaAQ6376(**kwargs)
        elif 'AndoAQ' in kwargs['mq_id']:
            osa = mq_osa.AndoAQ6317B(**kwargs)
        # Grab and plot data
        self.clear_plot()
        if self.osaCh1.isChecked():
            osa_channel = 'A'
        elif self.osaCh2.isChecked():
            osa_channel = 'B'
        elif self.osaCh3.isChecked():
            osa_channel = 'C'

        data = self.instrument_data_grab(osa, channel=osa_channel)
        if data is None:
            return  # Break out of function on error
        self.plots[self.tab_idx].grabbed_data = np.column_stack(data)

        self.setStatusBar('OSA Data Grab Successful', timestamp=True)
        self.plot_optical_spectrum()

        # If live view enabled, repeatedly grab until live_view is disabled.
        # We want the order to be: update plot first and grab 2nd, since grab operation is slower.
        while self.live_view_active:
            self.clear_plot(skip_update_canvas=True)
            self.plot_optical_spectrum()
            self.plots[self.tab_idx].grabbed_data = np.column_stack(osa.grab(osa_channel))

    def grab_osc(self):
        """ Function / thread for grabbing and displaying OSC trace data. """
        # Initialise oscilloscope for grabbing
        kwargs = self.data_grab_preparation('osc')
        if 'HP54616C' in kwargs['mq_id']:
            osc = mq_osc.HP54616C(**kwargs)
        elif 'TektronixTDS794D' in kwargs['mq_id']:
            osc = mq_osc.TektronixTDS794D(**kwargs)
        elif 'TektronixTDS2012B' in kwargs['mq_id']:
            osc = mq_osc.TektronixTDS2012B(**kwargs)
        else:
            raise ValueError('Oscilloscope not in database. Check code / mqinstruments folder.')

        # Grab and plot data
        self.clear_plot()
        if self.oscCh1.isChecked():
            osc_channel = '1'
        elif self.oscCh2.isChecked():
            osc_channel = '2'
        elif self.oscCh3.isChecked():
            osc_channel = '3'
        elif self.oscCh4.isChecked():
            osc_channel = '4'
        data = self.instrument_data_grab(osc, channel=osc_channel)

        if data is None:
            return  # Break out of function on error
        self.plots[self.tab_idx].grabbed_data = np.column_stack(data)

        self.setStatusBar('OSC Data Grab Successful', timestamp=True)
        self.plot_temporal_trace(source='osc')

        # If live view enabled, repeatedly grab until live_view is disabled.
        # We want the order to be: update plot first and grab 2nd, since grab operation is slower.
        while self.live_view_active:
            self.clear_plot(skip_update_canvas=True)
            self.plot_temporal_trace(source='osc')
            self.plots[self.tab_idx].grabbed_data = np.column_stack(osc.grab())

    def grab_esa(self):
        """ Function / thread for grabbing and displaying ESA trace data. """
        # Initialise ESA for grabbing
        kwargs = self.data_grab_preparation('esa')
        if 'AnritsuMS2683' in kwargs['mq_id']:
            esa = mq_esa.AnritsuMS2683A(**kwargs)

        # Grab and plot data
        self.clear_plot()

        data = self.instrument_data_grab(esa)
        if data is None:
            return  # Break out of function on error
        self.plots[self.tab_idx].grabbed_data = np.column_stack(data)

        self.setStatusBar('ESA Data Grab Successful', timestamp=True)
        self.plot_electrical_spectrum()

        # If live view enabled, repeatedly grab until live_view is disabled.
        # We want the order to be: update plot first and grab 2nd, since grab operation is slower.
        while self.live_view_active:
            self.clear_plot(skip_update_canvas=True)
            self.plot_electrical_spectrum()
            self.plots[self.tab_idx].grabbed_data = np.column_stack(esa.grab())

    def grab_pdd(self):
        """ Function / thread for grabbing and displaying PulseDiagnosticDevice trace data. """
        # Initialise device for grabbing (at present, we only have APE as a pdd, so hard-core it's configuration (since it's a bit odd and uses TCP/IP over USB)
        pdd = mq_ac.APEPulseCheck()

        # Grab and plot data
        self.clear_plot()

        data = self.instrument_data_grab(pdd)
        if data is None:
            return  # Break out of function on error
        self.plots[self.tab_idx].grabbed_data = np.column_stack(data)

        self.setStatusBar('Pulse Diagnostic Device Data Grab Successful', timestamp=True)
        self.plot_temporal_trace(source='pdd')

        # If live view enabled, repeatedly grab until live_view is disabled.
        # We want the order to be: update plot first and grab 2nd, since grab operation is slower.
        while self.live_view_active:
            self.clear_plot(skip_update_canvas=True)
            self.plot_electrical_spectrum()
            self.plots[self.tab_idx].grabbed_data = np.column_stack(pdd.grab())

    def plot_optical_spectrum(self):
        """ Plots optical spectrum, either from file or the recently grabbed data. """
        self.data_source = 'osa'  # Set data source variable so the GUI knows what type of data it's dealing with

        x_short = [] # Set up arrays to store max and min axis ranges, so all data can be properly displayed by plot formatting after the loop
        x_long = []
        y_high = []
        y_low = []

        # Plot Formatingg #
        # If custom plot style not enabled, set defaults
        if not self.customBtns.isChecked():
            self.rdbLog.setChecked(True)
            self.rdbLin.setChecked(False)
            self.plotStyle.setText('-')
            self.normalisePlot.setChecked(False)

        style = self.plotStyle.text()

        # Actually plot the data
        for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
            color = next(self.colors)
            data, data_label = self.preprocess_data(file_path)
            self.plots[self.tab_idx].ax.plot(ut.eng_prefix(data[:,0], self.data_source)[0], data[:,1], style, color=color, label=data_label)
            x_short.append(min(ut.eng_prefix(data[:,0], self.data_source)[0]))
            x_long.append(max(ut.eng_prefix(data[:,0], self.data_source)[0]))
            y_low.append(min(data[:,1]))
            y_high.append(max(data[:,1]))

        if self.plot_scale_log_or_lin() == 'log':
            self.plots[self.tab_idx].ax.set_ylabel('Spectral Intensity (a.u. dB)')
            if min(y_low) < -120: self.plots[self.tab_idx].ax.set_ylim(-90, max(y_high) + 5) # Don't show spriously low values (e.g. -200 dB) which are unphysical but sometimes are grabbed
        else:
            self.plots[self.tab_idx].ax.set_ylabel('Spectral Intensity (a.u.)')
        self.plots[self.tab_idx].ax.set_xlabel('Wavelength (' + ut.eng_prefix(data[:, 0], self.data_source)[1] + 'm)')
        self.plots[self.tab_idx].ax.set_xlim([min(x_short), max(x_long)])
        if not 'Data Grab' in file_path:
            leg = self.plots[self.tab_idx].ax.legend(loc='best', framealpha=0.5)
        self.update_canvas()

    def plot_temporal_trace(self, source='osc'):
        """ Plots temporal traces (inc. autocorrelations, streak camera and oscilloscope traces), either from file or the recently grabbed data. """
        # Pulse Diagnostic Device (autocorrelator, streak cam etc.) Plotting #
        if source == 'pdd':
            self.data_source = 'pdd'
            # Plot Formatingg #
            # If custom plot style not enabled, set defaults
            if not self.customBtns.isChecked():
                self.rdbLog.setChecked(False)
                self.rdbLin.setChecked(True)
                self.plotStyle.setText('o')
                self.normalisePlot.setChecked(False)
            style = self.plotStyle.text()

            if self.plot_scale_log_or_lin() == 'lin':
                self.plots[self.tab_idx].ax.set_ylabel('Intensity (a.u.)')
            else:
                self.plots[self.tab_idx].ax.set_ylabel('Intensity (a.u. dB)')

            # Actually plot the data
            for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
                data, data_label = self.preprocess_data(file_path)
                # Style and plot
                color = next(self.colors)
                if style == 'o':
                    self.plots[self.tab_idx].ax.plot(ut.eng_prefix(data[:, 0])[0], data[:, 1], 'o', mec=color, mfc='None', mew=1, label=data_label)
                else:
                    self.plots[self.tab_idx].ax.plot(ut.eng_prefix(data[:, 0])[0], data[:, 1], '-', color=color, mew=1, label=data_label)

        # Oscilloscope Trace Plotting
        elif source == 'osc':
            self.data_source = 'osc'  # Set data source variable so the GUI knows what type of data it's dealing with
            # Plot Formatingg #
            # If custom plot style not enabled, set defaults
            if not self.customBtns.isChecked():
                self.rdbLog.setChecked(False)
                self.rdbLin.setChecked(True)
                self.plotStyle.setText('-')
                self.normalisePlot.setChecked(False)
            style = self.plotStyle.text()

            if self.plot_scale_log_or_lin() == 'lin':
                self.plots[self.tab_idx].ax.set_ylabel('Amplitude (V)')
            else:
                self.plots[self.tab_idx].ax.set_ylabel('Amplitude (a.u. dB)')

            # Actually plot the data
            for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
                data, data_label = self.preprocess_data(file_path)
                color = next(self.colors)
                self.plots[self.tab_idx].ax.plot(ut.eng_prefix(data[:, 0])[0], data[:, 1], style, color=color, mew=1, label=data_label)

        # Plot formatting
        if source == 'osc':
            self.plots[self.tab_idx].ax.set_xlabel('Time (' + str(ut.eng_prefix(data[:, 0])[1]) + 's)')
        elif source == 'pdd':
            self.plots[self.tab_idx].ax.set_xlabel('Delay (' + str(ut.eng_prefix(data[:, 0])[1]) + 's)')

        self.plots[self.tab_idx].ax.set_xlim([min(ut.eng_prefix(data[:, 0])[0]), max(ut.eng_prefix(data[:, 0])[0])])

        self.peak_threshold = (data[:, 1].max() - data[:, 1].min()) / 2 + data[:, 1].min()  # Set a threshold for pulse train interpreetation
        if 'Data Grab' not in file_path:
            leg = self.plots[self.tab_idx].ax.legend(loc='best', framealpha=0.5)
        self.update_canvas()

    def plot_electrical_spectrum(self):
        """ Plots electrical specta, either from file or the recently grabbed data. """
        self.data_source = 'esa'

        # Plot Formatingg #
        # If custom plot style not enabled, set defaults
        if not self.customBtns.isChecked():
            self.rdbLog.setChecked(True)
            self.rdbLin.setChecked(False)
            self.plotStyle.setText('-')
            self.normalisePlot.setChecked(False)
        style = self.plotStyle.text()

        for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
            color = next(self.colors)
            data, data_label = self.preprocess_data(file_path)
            self.plots[self.tab_idx].ax.plot(ut.eng_prefix(data[:, 0])[0], data[:, 1], style, color=color, label=data_label)

        if self.plot_scale_log_or_lin() == 'log':
            self.plots[self.tab_idx].ax.set_ylabel('Spectral Intensity (dBm)')
        else:
            self.plots[self.tab_idx].ax.set_ylabel('Spectral Intensity (a.u.)')
        self.plots[self.tab_idx].ax.set_xlabel('Frequency (%sHz)' % str(ut.eng_prefix(data[:,0])[1]))

        if 'Data Grab' not in file_path:
            leg = self.plots[self.tab_idx].ax.legend(loc='best', framealpha=0.5)
        self.update_canvas()

    def preprocess_data(self, file_path):
        """ Returns most recently imported data for plotting, be it from a file or grabbed. Performs log-lin conversion and normalisation here too. """
        # First, get data from a file or the just-grabbed data from a device
        if 'Data Grab' in file_path:
            data = self.plots[self.tab_idx].grabbed_data.copy()
            data_label = ''
        else:
            try:
                data = ut.read_data(file_path, self.data_source).copy()  # Use .copy() to break link to original data
            except:
                self.show_warning_dialog('Data file not recognised. Check file is valid and retry.')
                return np.ones((100, 2)), 'Plotting Error'
            self.setStatusBar('Data plotted from %s' % file_path)
            data_label = os.path.splitext(os.path.split(file_path)[-1])[0]

        # Apply log-lin conversion
        # OSA & ESA y data is grabbed in dB scale
        if self.data_source == 'osa' or self.data_source == 'esa':
            if self.plot_scale_log_or_lin() == 'lin':
                data[:, 1] = 1e3 * (10**(data[:, 1] / 10))  # Ignores scaling (i.e. the values are arbitrary)
        # OSC and PDD data is grabbed by default in lin scale
        else:
            if self.plot_scale_log_or_lin() == 'log':
                if data[:, 1].min() < 0:
                    data[:, 1] += abs(data[:, 1].min())
                    print('Data shifted to positive y values in order to set scale to log for visualisation')
                data[:, 1] = np.log10(data[:, 1])  # Ignores scaling (i.e. the dB values are arbitrary)

        # Apply normalisation if requested
        if self.normalisePlot.isChecked():
            data[:, 1] = ut.normalise(data[:, 1], scale=self.plot_scale_log_or_lin())

        # Enable fitting and analysis controls
        self.fittingBox.setEnabled(True)

        return data.copy(), data_label # Return a copy of the array so as not to link the returned array with the original

    def onPushSaveDataBtn(self):
        """ Saves most recetly grabbed data to a text file, appending a header and datetime stamp too. """
        header1 = {'osa':'# Optical spectrum measured with: %s\n' % self.osaCmb.currentText(),
                  'osc':'# Oscilloscope trace measured with: %s\n' % self.oscCmb.currentText(),
                  'esa':'# Electrical spectrum measured with: %s\n' % self.esaCmb.currentText(),
                  'pdd':'# Temporal data measured with: %s\n' % self.pddCmb.currentText()}
        header2 = '# Date: %s\n' % time.asctime()

        # Open dialgoue window then save data to the user-specified path
        savefile_path = QFileDialog.getSaveFileName(self, 'Save grabbed data', filter="Data files (*.dat);;All files (*.*)")
        if savefile_path[0]:  # If user presses cancel, two empty strings return, so only process for an OK click
            # There's a strange occurence where getSaveFileName sometimes returns the extensions, and other times doesn't (perhaps Qt4/5 issue?). Catch this:
            if ('Data files' in savefile_path[-1]) or ('All files' in savefile_path[-1]):
                savefile_path = savefile_path[0]

            data_to_save = self.plots[self.tab_idx].grabbed_data.copy()

            with open(savefile_path, 'wb') as f:
                f.write(header1[self.data_source].encode())  # Encode converts string to bytes object for python 3 (since file has to be opened in wb mode)
                f.write(header2.encode())
                np.savetxt(f, data_to_save)

            self.setStatusBar('Data saved to %s' % savefile_path)

            # Add the recently assigned file name to the plot title
            save_file_name = savefile_path.replace('\\', '/')  # Default paths to linux style (works on Windows too, but not vice versa)
            display_filepath = save_file_name.split('/')[-2] + '/' + save_file_name.split('/')[-1]

            savefile_path_img = savefile_path[:-4].replace('.', ',') + '.dat'  # Strip off dots from file name so it allows saving an image
            self.plots[self.tab_idx].ax.set_title(display_filepath)
            self.update_canvas(self, save_png_path=savefile_path_img)

    def preprocess_data_for_fitting(self, file_path):
        """ Get data and preprocess by taking into account custom span selected. """
        color = next(self.colors)
        data_full, data_label = self.preprocess_data(file_path)
        data_full[:, 0], unit_prefix = ut.eng_prefix(data_full[:, 0], self.data_source)  # Get data in SI units and save prefix to a variable
        units = unit_prefix + self.units[self.data_source]  # returns the dimension: m, s or Hz

        # If not a custom fitting, then use all the data
        if ((self.x_max == 0) and (self.x_min == 0)):
            _x_min = data_full[:, 0][0]
            _x_max = data_full[:, 0][-1]
        else:
            # Get xmin and max from the span selector
            _x_min = self.x_min
            _x_max = self.x_max
        lower_idx = np.where(data_full[:, 0] <= _x_min)
        upper_idx = np.where(data_full[:, 0] >= _x_max)
        data = data_full[lower_idx[0][-1]:upper_idx[0][0], :].copy()

        # If a custom fitting enabled, then highlight the chosen data
        if not ((self.x_max == 0) and (self.x_min == 0)):
            self.plots[self.tab_idx].ax.plot(data[:, 0], data[:, 1], 'o', color=color, ms=4, mec='None')
            self.update_canvas()

        return data, units, color

    def onPushShapeFitBtn(self):
        """ Fitting function: fits to user-specified unput and paints the results on the canvas """
        for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
            data, units, color = self.preprocess_data_for_fitting(file_path)

            fit_type = self.shapeFitCmb.currentText()
            fit_type = fit_type.replace('Sech^2', 'sech2')  # Present sech^2 pulses as sech2 for fitting
            fit_type = fit_type.replace('Gaussian', 'gaussian')

            x_fit, y_fit, coefs, pcov = ut.fitted(data[:, 0], data[:, 1], fit_type)
            fwhm_interpolated = ut.width_of_dataset(x=x_fit, y=y_fit, threshold=0.5, scale=self.plot_scale_log_or_lin(), interpolate=True)

            # If an autocorrelation trace, show deconvolved width
            if '(AC)' in fit_type:
                if 'sech2' in fit_type:
                    decon_factor = 0.647
                elif 'gaussian' in fit_type:
                    decon_factor = 0.707
                decon_fwhm = fwhm_interpolated * decon_factor
                annotation = '%s FWHM:\n%0.3f %s (AC) -> %0.3f %s (Deconvolved)' % (fit_type, fwhm_interpolated, units, decon_fwhm, units)
            else:
                annotation = '%s FWHM:\n%0.3f %s' % (fit_type, fwhm_interpolated, units)

            self.setStatusBar('%s Fit: coeffs = %s.' % (fit_type, coefs))
            self.plots[self.tab_idx].ax.plot(x_fit, y_fit, '-', color=color, lw=3)

            self.annotate_canvas(annotation, color)
            self.update_canvas()

    def onPushDataPulseTrainBtn(self):
        """ Interpret data as pulse train to find pulse spacing and rep rate. """
        for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
            data, units, color = self.preprocess_data_for_fitting(file_path)
            fit_type = self.shapeFitCmb.currentText()
            fit_type = fit_type.replace('Sech^2', 'sech2')  # Present sech^2 pulses as sech2 for fitting
            fit_type = fit_type.replace('Gaussian', 'gaussian')

            try:
                peaks = ut.peak_detect(data[:, 1], self.peak_threshold, data[:, 0])
                spacings = np.ediff1d(peaks[:, 0])
                pulse_separation = np.mean(spacings)
                separation_variation = 100 * (max(abs(spacings - pulse_separation))) / pulse_separation  # fluctuations in pulse spacing
                unit_prefix = units[0]
                multiplier = ut.unit_dict_return_exp(unit_prefix)
                rep_rate = 1 / (pulse_separation * 10**multiplier)
                annotation = 'Pulse spacing = %.3f %ss (+/- %.2f %%) -> %.2f %sHz' % (pulse_separation, unit_prefix, separation_variation, ut.eng_prefix(rep_rate)[0], ut.eng_prefix(rep_rate)[1])
                self.annotate_canvas(annotation, color)
                self.update_canvas()
            except Exception:
                import traceback
                traceback.print_exc()
                self.setStatusBar('ERROR: Automated pulse train analysis failed - check code or perform manually.')

    def onPushDataFwhmBtn(self):
        """ Prints the 'raw FWHM', that is the FWHM using only the source data """
        for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
            data, units, color = self.preprocess_data_for_fitting(file_path)

            fwhm = ut.width_of_dataset(x=data[:, 0], y=data[:, 1], threshold=0.5, scale=self.plot_scale_log_or_lin(), interpolate=True)
            fwqm = ut.width_of_dataset(x=data[:, 0], y=data[:, 1], threshold=0.25, scale=self.plot_scale_log_or_lin(), interpolate=True)
            annotation = 'Raw FWHM:%0.3f %s, FWQM:%0.3f %s' % (fwhm, units, fwqm, units)
            self.annotate_canvas(annotation, color)

    def onPushDataCentreBtn(self):
        """ Prints the 'raw centre', that is the centre value in x-axis, of y-axis peak using only the source data """
        for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
            data, units, color = self.preprocess_data_for_fitting(file_path)

            centre = ut.centre_of_dataset(x=data[:, 0], y=data[:, 1], threshold=0.5, scale=self.plot_scale_log_or_lin(), interpolate=True)
            annotation = 'Centre:\n%0.3f %s' % (centre, units)
            self.annotate_canvas(annotation, color)

    def onPushDataIntegrateBtn(self):
        """ Integrates chosen selection of data, divided by the integral of whole dataset. """
        for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
            data, units, color = self.preprocess_data_for_fitting(file_path)
            data_full, data_label = self.preprocess_data(file_path)
            data_full[:, 0], unit_prefix = ut.eng_prefix(data_full[:, 0], self.data_source)  # Get data in SI units and save prefix to a variable

            # Highlight the integration region
            self.plots[self.tab_idx].ax.axvspan(self.x_min, self.x_max, color='red', alpha=0.4)

            # Cast into linear scale if data is in log scale
            if self.plot_scale_log_or_lin() == 'log':
                data[:, 1] = 1e3 * (10**(data[:, 1] / 10))  # Ignores scaling (i.e. the values are arbitrary)
                data_full[:, 1] = 1e3 * (10**(data_full[:, 1] / 10))  # Ignores scaling (i.e. the values are arbitrary)

            # Compute integrations (note: trapz is more robust than simps here - see SciPy documentation re. simps' handling of even/odd length arrays)
            selection_integral = trapz(data[:, 1], data[:, 0])
            full_integral = trapz(data_full[:, 1], data_full[:, 0])
            percentage_integral = selection_integral / full_integral * 100

            annotation = 'Integral of selection / full integral = %0.2f%%' % (percentage_integral)
            self.annotate_canvas(annotation, color)

    ##########################
    # ADVANCED TAB FUNCTIONS #
    ##########################

    def onPushPlotTransmissionBtn(self):
        """ Plots transmission spectra for components scanned with MQ Cary spectrophotometer. """
        self.data_source = 'cary'

        # Force linear display
        self.rdbLog.setChecked(False)
        self.rdbLin.setChecked(True)

        for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
            data, data_label = self.preprocess_data(file_path)
            self.plots[self.tab_idx].ax.plot(data[:, 0], data[:, 1], label=data_label)

        # Plot formatting
        self.plots[self.tab_idx].ax.set_xlabel('Wavelength (nm)')
        self.plots[self.tab_idx].ax.set_ylabel('Transmission (%)')
        leg = self.plots[self.tab_idx].ax.legend(loc='best', framealpha=0.5)
        self.plots[self.tab_idx].ax.set_ylim([-5, 105])
        self.plots[self.tab_idx].ax.grid(True)
        self.update_canvas()

    def OnPushPlotPowerScanBtn(self):
        """ Plots power scans obtained using power_scan tool. """
        print('Not yet implemented.')

    def onPushPlotTemperatureScanBtn(self):
        """ Plots temperature scans of data grabbed from temperature controller devices. """
        for file_path in [self.filesList.item(i).text() for i in range(self.filesList.count())]:
            datfile = open(file_path,'rb')
            dates = []
            temps = []
            for line in datfile.readlines()[2:]:
                s1 = line.split()
                sdate = [int(part) for part in s1[0].split(':')]
                read_datetime = datetime.datetime(2000+sdate[0], sdate[1], sdate[2], sdate[3], sdate[4])
                dates.append(read_datetime)
                temps.append(float(s1[1]))
            datfile.close()
            temps = np.array(temps)
            dates = mdates.date2num(dates)
            self.plots[self.tab_idx].ax.plot_date(dates,temps, 'o-', color='red')

        self.plots[self.tab_idx].figure.autofmt_xdate()
        self.plots[self.tab_idx].ax.set_ylabel('Temperature ($^\circ$)')
        self.update_canvas()


    def onPushPlotBeamProfileBtn(self, show_colorbar=False):
        """ Plots beam profile from ASCII data. Only works for one file to be plotted. """
        file_path = [self.filesList.item(i).text() for i in range(self.filesList.count())][0]  # Assumes only one file to be plotted
        data = ut.read_data(file_path, 'ccd')

        im = self.plots[self.tab_idx].ax.imshow(data)
        if show_colorbar:
            self.plots[self.tax_idx].figure.colorbar(im, orientation='horizontal')
        self.update_canvas(span_selector_enable=False)


    def onPushViewGpibAddressesBtn(self):
        """ Show mq_instruments.txt file. """
        os.system(mq_instruments_config_filepath)


    ################
    # SPECTROMETER #
    ################

    def spectrometerTabUI(self):
        """ Create widgets and layout for spectrometer tab. """
        layout = QHBoxLayout(self.spectrometerTab)

        # MONOCHROMATOR SETTINGS #
        monochromatorFrame = QFrame()
        monochromatorFrameLayout = QVBoxLayout(monochromatorFrame)

        monochromatorHardwareFrame = QGroupBox('Monochromator')

        # Connections
        monochromatorConnectionsLayout = QHBoxLayout(monochromatorHardwareFrame)
        self.monochromatorCmb = QComboBox(monochromatorFrame)
        self.monochromatorCmb.addItems(['CVI CM112'])
        self.monochromatorComPort = QLineEdit(monochromatorFrame)
        self.monochromatorComPort.setText(ut.available_serial_ports()[0])
        connectMonochromatorBtn = self.createRibbonBtn(parent=self.spectrometerTab, onPushMethod=self.onPushConnectMonochromatorBtn, text='Connect', icon_filepath=self.resources_folder + 'icon_network.png', icon_size=20, icon_pos='left', btn_type='toolbutton')

        monochromatorConnectionsLayout.addWidget(self.monochromatorCmb)
        monochromatorConnectionsLayout.addWidget(self.monochromatorComPort)
        monochromatorConnectionsLayout.addWidget(connectMonochromatorBtn)

        # Forwards / backwards buttons
        self.monochromatorBtns = QWidget()
        self.monochromatorBtns.setEnabled(False)  # Disable monochromator commands until connected
        monochromatorBtnsLayout = QVBoxLayout(self.monochromatorBtns)
        monochromatorBtnsRow1Layout = QHBoxLayout()
        monochromatorBtnsRow2Layout = QHBoxLayout()
        monochromatorBtnsRow3Layout = QHBoxLayout()
        plus1Btn = self.createRibbonBtn(parent=self.spectrometerTab, onPushMethod=lambda: self.moveMonochromator(step=+0.1), text='0.1 nm', icon_filepath=self.resources_folder+'icon_f1.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        plus2Btn = self.createRibbonBtn(parent=self.spectrometerTab, onPushMethod=lambda: self.moveMonochromator(step=+1.0), text='1 nm', icon_filepath=self.resources_folder+'icon_f2.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        plus3Btn = self.createRibbonBtn(parent=self.spectrometerTab, onPushMethod=lambda: self.moveMonochromator(step=+10), text='10 nm', icon_filepath=self.resources_folder+'icon_f3.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        minus1Btn = self.createRibbonBtn(parent=self.spectrometerTab, onPushMethod=lambda: self.moveMonochromator(step=-0.1), text='0.1 nm', icon_filepath=self.resources_folder+'icon_b1.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        minus2Btn = self.createRibbonBtn(parent=self.spectrometerTab, onPushMethod=lambda: self.moveMonochromator(step=-1.0), text='1 nm', icon_filepath=self.resources_folder+'icon_b2.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        minus3Btn = self.createRibbonBtn(parent=self.spectrometerTab, onPushMethod=lambda: self.moveMonochromator(step=-10), text='10 nm', icon_filepath=self.resources_folder+'icon_b3.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        monochromatorBtnsRow1Layout.addWidget(plus1Btn)
        monochromatorBtnsRow1Layout.addWidget(plus2Btn)
        monochromatorBtnsRow1Layout.addWidget(plus3Btn)
        monochromatorBtnsRow2Layout.addWidget(minus1Btn)
        monochromatorBtnsRow2Layout.addWidget(minus2Btn)
        monochromatorBtnsRow2Layout.addWidget(minus3Btn)

        self.monochromatorWlBox = QLineEdit(monochromatorFrame)
        monochromatorGoToBtn = self.createRibbonBtn(parent=self.spectrometerTab, onPushMethod=lambda: self.moveMonochromator(goto_wl=float(self.monochromatorWlBox.text())), text='Goto', icon_filepath=self.resources_folder+'icon_goto.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        monochromatorBtnsRow3Layout.addWidget(QLabel('Position [nm]:'))
        monochromatorBtnsRow3Layout.addWidget(self.monochromatorWlBox)
        monochromatorBtnsRow3Layout.addWidget(monochromatorGoToBtn)

        monochromatorBtnsLayout.addLayout(monochromatorBtnsRow1Layout)
        monochromatorBtnsLayout.addLayout(monochromatorBtnsRow2Layout)
        monochromatorBtnsLayout.addLayout(monochromatorBtnsRow3Layout)

        monochromatorFrameLayout.addWidget(monochromatorHardwareFrame)
        monochromatorFrameLayout.addWidget(self.monochromatorBtns)

        # DETECTION SETTINGS #
        detectorFrame = QFrame()
        detectorFrameLayout = QVBoxLayout(detectorFrame)
        detectorHardwareFrame = QGroupBox('Detector')

        # Connections
        detectorConnectionsLayout = QHBoxLayout(detectorHardwareFrame)
        self.detectorCmb = QComboBox(detectorHardwareFrame)
        self.detectorCmb.addItems(['SR830 Lock-In'])
        self.detectorInterface = QComboBox(detectorHardwareFrame)
        self.detectorInterface.addItems(['GPIB-Ethernet'])
        connectDetectorBtn = self.createRibbonBtn(parent=self.spectrometerTab, onPushMethod=self.onPushConnectDetectorBtn, text='Connect', icon_filepath=self.resources_folder + 'icon_network.png', icon_size=20, icon_pos='left', btn_type='toolbutton')

        detectorConnectionsLayout.addWidget(self.detectorCmb)
        detectorConnectionsLayout.addWidget(self.detectorInterface)
        detectorConnectionsLayout.addWidget(connectDetectorBtn)

        sensitivitySettingsLayout = QFormLayout()
        self.sensitivityMode = QComboBox()
        self.sensitivityMode.addItems(['Auto Gain (Software)', 'Auto Gain (Hardware)', 'Fixed'])
        self.sensitivityMin = QComboBox(detectorFrame)
        self.sensitivityMin.addItems([str(i) for i in range(26)])
        self.sensitivityMin.setCurrentIndex(9)
        sensitivitySettingsLayout.addRow('Sens. Mode:', self.sensitivityMode)
        sensitivitySettingsLayout.addRow('Sens. Min:', self.sensitivityMin)

        self.monitorBtn = self.createRibbonBtn(parent=self.grabTab, onPushMethod=self.onPushMonitorBtn, text='Alignment Monitor Start/Stop', icon_filepath=self.resources_folder+'icon_monitor.png', icon_size=30, btn_type='pushbutton')
        self.monitorBtn.setEnabled(False)  # Disable monitoring commands until detector connected

        detectorFrameLayout.addWidget(detectorHardwareFrame)
        detectorFrameLayout.addLayout(sensitivitySettingsLayout)
        detectorFrameLayout.addWidget(self.monitorBtn)

        # SCAN SETTINGS #
        self.scanFrame = QFrame()
        self.scanFrame.setEnabled(False)

        scanFrameLayout = QVBoxLayout(self.scanFrame)

        scanRangeLayout = QHBoxLayout()
        self.sweepWl1 = QLineEdit(self.scanFrame)
        self.sweepWl2 = QLineEdit(self.scanFrame)
        scanRangeLayout.addWidget(QLabel('Range (nm):'))
        scanRangeLayout.addWidget(self.sweepWl1)
        scanRangeLayout.addWidget(QLabel('to '))
        scanRangeLayout.addWidget(self.sweepWl2)

        stepLayout = QHBoxLayout()
        self.sweepWlStep = QLineEdit(self.scanFrame)
        self.spectrometerDelay = QLineEdit(self.scanFrame)
        self.spectrometerDelay.setText('1')
        self.spectrometerLogLin = QComboBox(self.scanFrame)
        self.spectrometerLogLin.addItems(['Lin', 'Log'])

        stepLayout.addWidget(QLabel('Step (nm):'))
        stepLayout.addWidget(self.sweepWlStep)
        stepLayout.addWidget(QLabel('Wait (s):'))
        stepLayout.addWidget(self.spectrometerDelay)
        stepLayout.addWidget(self.spectrometerLogLin)

        btnRow1 = QHBoxLayout()
        btnRow2 = QHBoxLayout()

        self.startScanBtn = self.createRibbonBtn(parent=self.grabTab, onPushMethod=self.onPushSpectrometerStart, text='  Start', icon_filepath=self.resources_folder + 'icon_start.png', icon_size=30, btn_type='pushbutton')
        self.stopScanBtn = self.createRibbonBtn(parent=self.grabTab, onPushMethod=self.onPushSpectrometerStop, text='  Stop', icon_filepath=self.resources_folder + 'icon_stop.png', icon_size=30, btn_type='pushbutton')
        self.stopScanBtn.setEnabled(False)
        saveScanBtn = self.createRibbonBtn(parent=self.grabTab, onPushMethod=self.onPushSaveSpectrometerDataBtn, text='    Save Data', icon_filepath=self.resources_folder + 'icon_save.png', icon_size=30, btn_type='pushbutton')

        scanFrameLayout.addLayout(scanRangeLayout)
        scanFrameLayout.addLayout(stepLayout)
        btnRow1.addWidget(self.startScanBtn)
        btnRow1.addWidget(self.stopScanBtn)
        btnRow2.addWidget(saveScanBtn)
        scanFrameLayout.addLayout(btnRow1)
        scanFrameLayout.addLayout(btnRow2)

        layout.addWidget(monochromatorFrame)
        layout.addWidget(detectorFrame)
        layout.addWidget(self.scanFrame)

    def onPushConnectMonochromatorBtn(self):
        """ Establish connection with monochromator. """
        try:
            self.monochromator = mq_monochromator.CM112(com_port=self.monochromatorComPort.text())
            self.monochromator.wl = self.monochromator.get_position()  # Save current position locally for quick access
            self.monochromatorWlBox.setText(str(self.monochromator.wl))
            self.setStatusBar('Successfully connected to {}.'.format(self.monochromatorCmb.currentText()))
            self.update_interface_disabled_options()
        except Exception as e:
            self.show_error_dialog('Serial connection error: %s.\n\nCheck the COM port is correct and that device is powered on.' % e)

    def moveMonochromator(self, goto_wl=None, step=None):
        """ Move monochromator to either a given positoin (goto_wl [nm]), or a step (+ = forward, - = backwards [nm]).

        This uses the monochromator set_position command. For scanning, the in-built step command is used.
        """
        if goto_wl is not None:
            print('Going to {}'.format(goto_wl))
            self.monochromator.set_position(goto_wl)
            self.monochromator.wl = goto_wl

        elif step is not None:
            new_wl = np.round(self.monochromator.wl + step, 2)  # Use round to avoid floating point errors -> we won't get below 0.01 nm accuracy anyway
            print('Stepping by {}, from {} to {}'.format(step, self.monochromator.wl, new_wl))
            self.monochromator.set_position(new_wl)
            self.monochromator.wl = new_wl

        self.monochromatorWlBox.setText(str(self.monochromator.wl))

        time.sleep(0.5)
        actual_wl = self.monochromator.get_position()
        self.setStatusBar('Monochromator moved to: {:.1f} nm'.format(actual_wl))

        # Due to weird bugs with CMI monochromator, double check the position it's moved to is correct
        if not np.allclose(actual_wl, goto_wl):
            self.show_error_dialog('Monochromator error: Device has decided to move to a different wavelength instead (hardware bug?). Try resending the command after a few seconds.')

    def onPushConnectDetectorBtn(self):
        """ Establish connection with lock-in detection system. """
        try:
            # For now, hard-code gpib-ethernet interface. If flexbility needed, this can be revised.
            # Save relevant arguments into dictionary
            kwargs = dict()
            kwargs['mq_id'] = 'SR830'
            kwargs['interface'] = 'gpib-ethernet'
            kwargs['gpib_location'] = self.location.currentText()

            self.lockin = mq_lockin.SR830(sensitivity_min_idx=int(self.sensitivityMin.currentText()), **kwargs)
            ident = self.lockin.get_idn()
            if 'SR830' not in ident:
                raise Exception('GPIB connection failed.')
            self.setStatusBar('Successfully connected to {}.'.format(self.detectorCmb.currentText()))
            self.update_interface_disabled_options()
        except Exception as e:
            self.show_error_dialog('Connection error: %s.\n\nCheck the computer is on same network as GPIB-LAN gateway, GPIB address is correct in the MQLAB settings table and that device is powered on.' % e)

    def update_interface_disabled_options(self, status='ready'):
        """ Enable UI options if the user has connected to monochromator and/or detector. """
        # For spectrometer usage, we always want to disable automatic saving of plots
        self.automatically_save_plots_to_disk = False

        if hasattr(self, 'monochromator'):
            self.monochromatorBtns.setEnabled(True)  # Enable monochromator commands

        if hasattr(self, 'lockin'):
            self.monitorBtn.setEnabled(True)  # Enable lock-in voltage monitoring command

        if hasattr(self, 'monochromator') & hasattr(self, 'lockin'):
            self.scanFrame.setEnabled(True)  # Enable spectrometer measurements
            self.startScanBtn.setEnabled(True)
            self.stopScanBtn.setEnabled(False)

        # Disable options if scan is running
        if status == 'monitoring':
            self.scanFrame.setEnabled(False)
        elif status == 'scanning':
            self.monochromatorBtns.setEnabled(False)
            self.monitorBtn.setEnabled(False)
            self.startScanBtn.setEnabled(False)
            self.stopScanBtn.setEnabled(True)

    def onPushMonitorBtn(self):
        """ Start or stop polling lock-in to show the voltage - useful for aligning the system. """
        # If the thread is already running, kill it
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.wants_abort = True
        # Otherwise, start the thread
        else:
            self.monitor_thread = Thread(target=self.runMonitor)
            self.update_interface_disabled_options(status='monitoring')
            self.monitor_thread.wants_abort = False
            self.monitor_thread.start()

    def runMonitor(self):
        self.setStatusBar('Monitoring')
        voltages = []
        self.plots[self.tab_idx].ax.cla()  # Clear axis
        while (not self.monitor_thread.wants_abort):
            if 'Software' in self.sensitivityMode.currentText():
                voltages.append(self.lockin.get_amplitude_with_manual_autoranging())
            elif 'Hardware' in self.sensitivityMode.currentText():
                self.lockin.auto_gain()
                voltages.append(self.lockin.get_amplitude())
            elif 'Fixed' in self.sensitivityMode.currentText():
                voltages.append(self.lockin.get_amplitude())

            # Plot data
            self.plots[self.tab_idx].ax.plot(np.arange(len(voltages)), np.array(voltages), color='C1')
            self.plots[self.tab_idx].ax.set_xlabel('Time (a.u.)')
            self.plots[self.tab_idx].ax.set_ylabel('Intensity on detector (a.u.)')
            self.update_canvas(copy_to_clipboard=False)

        self.setStatusBar('Ready')
        self.update_interface_disabled_options(status='ready')
        del self.monitor_thread  # Kill thread once it finishes

    def onPushSpectrometerStart(self):
        """ Start a spectrometer measurement. """
        self.lockin.sensitivity_min_idx = int(self.sensitivityMin.currentText())  # Update the min sensitivity in case user changed it after initialising connection
        try:
            wl1 = float(self.sweepWl1.text())
            wl2 = float(self.sweepWl2.text())
            wl_step = float(self.sweepWlStep.text())
        except ValueError:
            self.show_error_dialog('Invalid scan range. Please check start, stop and step wavelengths.')
            return None  # Cease execution of this function

        self.setStatusBar('Scanning')
        self.scanner_thread = Thread(target=self.runScanner, args=(wl1, wl2, wl_step))
        self.update_interface_disabled_options(status='scanning')
        self.scanner_thread.wants_abort = False
        self.scanner_thread.start()

    def onPushSpectrometerStop(self):
        """ Stop a currently running spectrometer measurement. """
        if hasattr(self, 'scanner_thread'):
            self.scanner_thread.wants_abort = True
            self.update_interface_disabled_options(status='ready')
            self.setStatusBar('Ready')

    def runScanner(self, wl1, wl2, wl_step):
        # Prepare data ararys
        self.wls = np.arange(wl1, wl2 + wl_step, wl_step)
        self.intensities = np.ones(len(self.wls), 'float') * 1e-10  # Set null value as essentially 0

        # Set up monochromator for scanning
        self.monochromator.set_step_size(wl_step)
        time.sleep(1)
        self.monochromator.set_position(self.wls[0])
        time.sleep(1)

        start_time = time.time()

        delay_between_measurements = float(self.spectrometerDelay.text())

        y_scale = self.spectrometerLogLin.currentText()

        for i, wl in enumerate(self.wls):
            # Wait for everything to settle
            time.sleep(delay_between_measurements)

            if 'Software' in self.sensitivityMode.currentText():
                self.intensities[i] = self.lockin.get_amplitude_with_manual_autoranging()
            elif 'Hardware' in self.sensitivityMode.currentText():
                self.lockin.auto_gain()
                self.intensities[i] = self.lockin.get_amplitude()
            elif 'Fixed' in self.sensitivityMode.currentText():
                self.intensities[i] = self.lockin.get_amplitude()

            # Neatening up data for presentation
            if y_scale == 'Lin':
                y_label = 'Intensity (a.u.)'
            else:
                y_label = 'Intensity (a.u. dB)'

            # Save to class (for saving OSA data, we always save in dB for consistency)
            # Question, since it's a voltage measurement, log conversion should technically be 20*log(val)? Doesn't matter as a.u. anyway.
            self.intensities_dB = np.clip(10 * np.log10(abs(self.intensities)), -100.0, 100.0)  # Catch infs
            self.plots[self.tab_idx].grabbed_data = np.column_stack([self.wls * 1e-9, self.intensities_dB])

            # Plot data
            self.plots[self.tab_idx].ax.cla()
            self.plots[self.tab_idx].ax.plot(self.wls, self.intensities, '-o', color='C0')
            self.plots[self.tab_idx].ax.set_xlabel('Wavelength (nm)')
            self.plots[self.tab_idx].ax.set_ylabel(y_label)
            self.update_canvas(copy_to_clipboard=False)

            # Exit the FOR loop if the thread is to be aborted
            if self.scanner_thread.wants_abort:
                print('Scan aborting...')
                break

            # Double check first and last data point correspond to correct actual monochromator wl position (due to weird CMI bug)
            if ((wl == self.wls[0]) or (wl == self.wls[-1])):
                actual_wl = self.monochromator.get_position()
                if not np.allclose(actual_wl, wl):
                    self.show_error_dialog('Monochromator error: device actual position and expected wavelength are out of sync (hardware bug?). Retry the scan (if bug persists, try a slightly different step size or range)')
                    break
                else:
                    print('Monochromator and software are synced correctly.')

            # Move to next step
            self.monochromator.step()

        elapsed_time = time.time() - start_time
        self.setStatusBar('Scan completed (duration = {0:.1f} s)'.format(elapsed_time))
        self.update_interface_disabled_options(status='ready')
        self.monochromator.set_position(self.wls[0])  # Go back to start ready for next scan
        self.monochromatorWlBox.setText(str(self.wls[0]))
        del self.scanner_thread  # Kill thread once it finishes

    def onPushSaveSpectrometerDataBtn(self):
        """ Saves grabbed spectrometer data to a text file, appending a header and datetime stamp too. """
        header1 = '# Optical spectrum from MQ spectrometer, measured with: {} and {}'.format(self.monochromatorCmb, self.detectorCmb)
        header2 = '# Date: %s\n' % time.asctime()

        # Open dialgoue window then save data to the user-specified path
        savefile_path = QFileDialog.getSaveFileName(self, 'Save grabbed data', filter="Data files (*.dat);;All files (*.*)")
        if savefile_path[0]:  # If user presses cancel, two empty strings return, so only process for an OK click
            # There's a strange occurence where getSaveFileName sometimes returns the extensions, and other times doesn't (perhaps Qt4/5 issue?). Catch this:
            if ('Data files' in savefile_path[-1]) or ('All files' in savefile_path[-1]):
                savefile_path = savefile_path[0]

            data_to_save = self.plots[self.tab_idx].grabbed_data.copy()

            with open(savefile_path, 'wb') as f:
                f.write(header1.encode())  # Encode converts string to bytes object for python 3 (since file has to be opened in wb mode)
                f.write(header2.encode())
                np.savetxt(f, data_to_save)

            self.setStatusBar('Data saved to %s' % savefile_path)

            # Add the recently assigned file name to the plot title
            save_file_name = savefile_path.replace('\\', '/')  # Default paths to linux style (works on Windows too, but not vice versa)
            display_filepath = save_file_name.split('/')[-2] + '/' + save_file_name.split('/')[-1]

            savefile_path_img = savefile_path[:-4].replace('.', ',') + '.dat'  # Strip off dots from file name so it allows saving an image
            self.plots[self.tab_idx].ax.set_title(display_filepath)
            self.update_canvas(self, save_png_path=savefile_path_img)

    ##################
    # AUTOCORRELATOR #
    ##################

    def autocorrelatorTabUI(self):
        """ Create widgets and layout for autocorrelator tab. """
        layout = QHBoxLayout(self.autocorrelatorTab)

        # MONOCHROMATOR SETTINGS #
        zstageFrame = QFrame()
        zstageFrameLayout = QVBoxLayout(zstageFrame)

        zstageHardwareFrame = QGroupBox('Translation Stage')

        # Connections
        zstageConnectionsLayout = QHBoxLayout(zstageHardwareFrame)
        self.zstageCmb = QComboBox(zstageFrame)
        self.zstageCmb.addItems(['Zaber'])
        self.zstageComPort = QLineEdit(zstageFrame)
        self.zstageComPort.setText(ut.available_serial_ports()[0])
        connectZstageBtn = self.createRibbonBtn(parent=self.autocorrelatorTab, onPushMethod=self.onPushConnectZstageBtn, text='Connect', icon_filepath=self.resources_folder + 'icon_network.png', icon_size=20, icon_pos='left', btn_type='toolbutton')

        zstageConnectionsLayout.addWidget(self.zstageCmb)
        zstageConnectionsLayout.addWidget(self.zstageComPort)
        zstageConnectionsLayout.addWidget(connectZstageBtn)

        # Forwards / backwards buttons
        self.zstageBtns = QWidget()

        self.zstageBtns.setEnabled(False)  # Disable Z stage commands until connected
        zstageBtnsLayout = QVBoxLayout(self.zstageBtns)
        zstageBtnsRow1Layout = QHBoxLayout()
        zstageBtnsRow2Layout = QHBoxLayout()
        zstageBtnsRow3Layout = QHBoxLayout()
        plus1Btn = self.createRibbonBtn(parent=self.autocorrelatorTab, onPushMethod=lambda: self.moveZstage(step=+0.1), text='0.1 mm', icon_filepath=self.resources_folder+'icon_f1.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        plus2Btn = self.createRibbonBtn(parent=self.autocorrelatorTab, onPushMethod=lambda: self.moveZstage(step=+1.0), text='1 mm', icon_filepath=self.resources_folder+'icon_f2.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        plus3Btn = self.createRibbonBtn(parent=self.autocorrelatorTab, onPushMethod=lambda: self.moveZstage(step=+10), text='10 mm', icon_filepath=self.resources_folder+'icon_f3.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        minus1Btn = self.createRibbonBtn(parent=self.autocorrelatorTab, onPushMethod=lambda: self.moveZstage(step=-0.1), text='0.1 mm', icon_filepath=self.resources_folder+'icon_b1.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        minus2Btn = self.createRibbonBtn(parent=self.autocorrelatorTab, onPushMethod=lambda: self.moveZstage(step=-1.0), text='1 mm', icon_filepath=self.resources_folder+'icon_b2.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        minus3Btn = self.createRibbonBtn(parent=self.autocorrelatorTab, onPushMethod=lambda: self.moveZstage(step=-10), text='10 mm', icon_filepath=self.resources_folder+'icon_b3.png', icon_size=20, icon_pos='left', btn_type='toolbutton')
        zstageBtnsRow1Layout.addWidget(plus1Btn)
        zstageBtnsRow1Layout.addWidget(plus2Btn)
        zstageBtnsRow1Layout.addWidget(plus3Btn)
        zstageBtnsRow2Layout.addWidget(minus1Btn)
        zstageBtnsRow2Layout.addWidget(minus2Btn)
        zstageBtnsRow2Layout.addWidget(minus3Btn)

        zstageBtnsLayout.addLayout(zstageBtnsRow1Layout)
        zstageBtnsLayout.addLayout(zstageBtnsRow2Layout)
        zstageBtnsLayout.addLayout(zstageBtnsRow3Layout)

        zstageFrameLayout.addWidget(zstageHardwareFrame)
        zstageFrameLayout.addWidget(self.zstageBtns)

        # DETECTION SETTINGS #
        detectorFrame = QFrame()
        detectorFrameLayout = QVBoxLayout(detectorFrame)

        detectorSettingsLayout = QFormLayout()
        self.acOscCmb = QComboBox()
        self.acOscCmb.addItems(self.OSCs)

        acChannelChoice = QWidget(detectorFrame)
        acChannelChoiceLayout = QHBoxLayout(acChannelChoice)
        self.acOscCh1 = QRadioButton('1')
        self.acOscCh2 = QRadioButton('2')
        self.acOscCh3 = QRadioButton('3')
        self.acOscCh4 = QRadioButton('4')
        self.acOscCh1.setChecked(True)
        acChannelChoiceLayout.addWidget(QLabel('Ch:'))
        acChannelChoiceLayout.addWidget(self.acOscCh1)
        acChannelChoiceLayout.addWidget(self.acOscCh2)
        acChannelChoiceLayout.addWidget(self.acOscCh3)
        acChannelChoiceLayout.addWidget(self.acOscCh4)

        self.acScanRange = QSpinBox(detectorFrame)
        max_distance = 60  # mm, for Zaber stage
        max_delay = 2 * max_distance / ut.c_mm_ps
        self.acScanRange.setRange(0, max_delay)
        self.acScanRange.setValue(10)
        self.acFit = QComboBox(detectorFrame)
        self.acFit.addItems(['None', 'Sech^2', 'Gaussian'])

        self.zstageScanSpeed = QDoubleSpinBox(detectorFrame)
        self.zstageScanSpeed.setDecimals(3)
        self.zstageScanSpeed.setRange(0.001, 4)  # As per: https://www.zaber.com/products/product_detail.php?detail=T-LA60A
        self.zstageScanSpeed.setValue(4)

        acOscFrame = QGroupBox('Oscilloscope')
        acOscFrameLayout = QFormLayout(acOscFrame)

        acOscFrameLayout.addRow('Device:', self.acOscCmb)
        acOscFrameLayout.addRow(acChannelChoice)

        detectorSettingsLayout.addRow('Z stage speed (mm/s):', self.zstageScanSpeed)
        detectorSettingsLayout.addRow('Scan Range (ps):', self.acScanRange)

        acMoveStageNoGrabBtn = self.createRibbonBtn(parent=self.autocorrelatorTab, onPushMethod=self.moveStageNoGrab, text='Start Alignment Mode', icon_filepath=self.resources_folder + 'icon_monitor.png', icon_size=25, btn_type='pushbutton')

        detectorFrameLayout.addWidget(acOscFrame)
        detectorFrameLayout.addLayout(detectorSettingsLayout)
        detectorFrameLayout.addWidget(acMoveStageNoGrabBtn)

        # SCAN SETTINGS #
        self.acScanFrame = QFrame()
        self.acScanFrame.setEnabled(False)

        scanFrameLayout = QVBoxLayout(self.acScanFrame)

        acScanSettingsLayout = QFormLayout()
        acScanSettingsLayout.addRow('Pulse Fit:', self.acFit)

        btnRow1 = QHBoxLayout()
        btnRow2 = QHBoxLayout()

        self.acStartScanBtn = self.createRibbonBtn(parent=self.grabTab, onPushMethod=self.onPushAutocorrelatorStart, text='  Start', icon_filepath=self.resources_folder+'icon_start.png', icon_size=30, btn_type='pushbutton')
        self.acStopScanBtn = self.createRibbonBtn(parent=self.grabTab, onPushMethod=self.onPushAutocorrelatorStop, text='  Stop', icon_filepath=self.resources_folder+'icon_stop.png', icon_size=30, btn_type='pushbutton')
        self.acStopScanBtn.setEnabled(False)
        saveScanBtn = self.createRibbonBtn(parent=self.grabTab, onPushMethod=self.onPushSaveAutocorrelatorDataBtn, text='    Save Data', icon_filepath=self.resources_folder+'icon_save.png', icon_size=30, btn_type='pushbutton')

        btnRow1.addWidget(self.acStartScanBtn)
        btnRow1.addWidget(self.acStopScanBtn)
        btnRow2.addWidget(saveScanBtn)

        scanFrameLayout.addLayout(acScanSettingsLayout)
        scanFrameLayout.addLayout(btnRow1)
        scanFrameLayout.addLayout(btnRow2)

        layout.addWidget(zstageFrame)
        layout.addWidget(detectorFrame)
        layout.addWidget(self.acScanFrame)

    def onPushConnectZstageBtn(self):
        """ Establish connection with linear translation stage. """
        try:
            self.zstage = mq_optomechanics.ZaberLinearTranslationStage(com_port=self.zstageComPort.text())
            self.setStatusBar('Successfully connected to {}.'.format(self.zstageCmb.currentText()))
            self.ac_update_interface_disabled_options()
        except Exception as e:
            self.show_error_dialog('Serial connection error: {}.\n\nCheck the COM port is correct and that device is powered on.'.format(e))

    def ac_update_interface_disabled_options(self, status='ready'):
        """ Enable UI options if the user has connected to zstage. """
        # For autcorrelator usage, we always want to disable automatic saving of plots
        self.automatically_save_plots_to_disk = False

        if hasattr(self, 'zstage'):
            self.zstageBtns.setEnabled(True)  # Enable zstage commands
            self.acScanFrame.setEnabled(True)  # Enable AC measurements
            self.acStartScanBtn.setEnabled(True)
            self.acStopScanBtn.setEnabled(False)

        if status == 'scanning':
            self.zstageBtns.setEnabled(False)
            self.acStartScanBtn.setEnabled(False)
            self.acStopScanBtn.setEnabled(True)

    def moveZstage(self, goto_pos=None, step=None):
        """ Move monochromator to either a given positoin (goto_pos [mm]), or a step (+ = forward, - = backwards [mm]). """
        if goto_pos is not None:
            self.zstage.move_to(goto_pos)

        elif step is not None:
            self.zstage.move_by(step)

    def moveStageNoGrab(self):
        """ Oscillate the stage to create AC trace on oscilloscope, but don't grab the data. Useful for aligning & optimising the setup. """
        self.setStatusBar('Autocorrelator running')
        self.ac_update_interface_disabled_options(status='scanning')
        self.ac_scanner_thread = Thread(target=self.runACScanner, args=(self.acScanRange.value(), self.zstageScanSpeed.value(), None, None, self.acFit.currentText(), True))
        self.ac_scanner_thread.wants_abort = False
        self.ac_scanner_thread.start()

    def onPushAutocorrelatorStart(self):
        """ Start an autocorrelation measurement. """
        # Connect to oscilloscope
        osc_id = self.acOscCmb.currentText()
        gpib_location = self.location.currentText()
        interface = self.connectionType.currentText()
        if 'HP54616C' in osc_id:
            osc = mq_osc.HP54616C(interface=interface, mq_id=osc_id, gpib_location=gpib_location)
        elif 'TektronixTDS794D' in osc_id:
            osc = mq_osc.TektronixTDS794D(interface=interface, mq_id=osc_id, gpib_location=gpib_location)
        elif 'TektronixTDS2012B' in osc_id:
            osc = mq_osc.TektronixTDS2012B(interface=interface, mq_id=osc_id, gpib_location=gpib_location)

        self.clear_plot()
        if self.acOscCh1.isChecked():
            osc_channel = '1'
        elif self.acOscCh2.isChecked():
            osc_channel = '2'
        elif self.acOscCh3.isChecked():
            osc_channel = '3'
        elif self.acOscCh4.isChecked():
            osc_channel = '4'

        self.setStatusBar('Autocorrelator running')
        self.ac_update_interface_disabled_options(status='scanning')
        self.ac_scanner_thread = Thread(target=self.runACScanner, args=(self.acScanRange.value(), self.zstageScanSpeed.value(), osc, osc_channel, self.acFit.currentText()))
        self.ac_scanner_thread.wants_abort = False
        self.ac_scanner_thread.start()

    def onPushAutocorrelatorStop(self):
        """ Stop a currently running autocorrelation measurement. """
        if hasattr(self, 'ac_scanner_thread'):
            self.ac_scanner_thread.wants_abort = True
            self.ac_update_interface_disabled_options(status='ready')
            self.setStatusBar('Ready')

    def runACScanner(self, scan_range, stage_speed, osc, osc_channel, fit, disable_grab=False):
        """ Autocorrelator scanning thread.

        Args:
            scan_range [ps]
            stage_speed [mm/s]
            zero_delay_position [mm]
            osc : instantiated oscilloscope object
            osc_channel (str)
            fit (str): fit type
        """
        # Prepare stage for scanning
        self.zstage.set_default_move_speed(stage_speed)
        time.sleep(0.1)

        # To improve stability, add a small delay between stage moving back and forwards
        scan_range_mm = scan_range * ut.c_mm_ps
        wait_delay = scan_range_mm / stage_speed * 1.1  # add 10% for safety
        print('Wait delay = {}'.format(wait_delay))

        # Assume initial position is zero delay pos, so first move back by half a delay
        self.zstage.move_by(-scan_range_mm / 2)
        time.sleep(wait_delay * 0.75)

        while True:
            # Oscillage 1 cycle of the stage
            self.zstage.move_by(scan_range_mm)
            time.sleep(wait_delay)
            self.zstage.move_by(-scan_range_mm)
            time.sleep(wait_delay)

            if not disable_grab:
                # Grab oscilloscope data (TODO: would this be better in a separate class, so grabbing and moving the stage are handled independently?)
                try:
                    tms, intensities = self.instrument_data_grab(osc, channel=osc_channel)
                    # Convert from oscilloscope timebase to AC delay using known stage movement speed
                    stage_positions = tms * stage_speed  # mm
                    delays = 2 * stage_positions / ut.c_mm_s  # [s], factor of two since light is reflected in the delay arm

                    # Save to class
                    self.plots[self.tab_idx].grabbed_data = np.column_stack([delays, intensities])

                    # Plot data
                    self.plots[self.tab_idx].ax.cla()
                    units = ut.eng_prefix(delays)[1] + 's'
                    self.plots[self.tab_idx].ax.plot(ut.eng_prefix(delays)[0], intensities, '-', color='C0')
                    self.plots[self.tab_idx].ax.set_xlabel('Delay ({})'.format(units))
                    self.plots[self.tab_idx].ax.set_ylabel('Intensity (V)')

                    # Apply fit if desired
                    annotation = ''
                    if fit != 'None':
                        try:
                            fit = fit.replace('Sech^2', 'sech2')  # Present sech^2 pulses as sech2 for fitting
                            fit = fit.replace('Gaussian', 'gaussian')
                            x_fit, y_fit, coefs, pcov = ut.fitted(ut.eng_prefix(delays)[0], intensities, fit)
                            fwhm_interpolated = ut.width_of_dataset(x=x_fit, y=y_fit, threshold=0.5, scale='lin', interpolate=True)
                            decon_fwhm = fwhm_interpolated * ut.ac_deconvolution_factor[fit]
                            annotation = '%s FWHM:\n%0.3f %s (AC) -> %0.3f %s (Deconvolved)' % (fit, fwhm_interpolated, units, decon_fwhm, units)
                            self.plots[self.tab_idx].ax.plot(x_fit, y_fit, '-', color='red', lw=3)
                        except Exception:
                            annotation = 'Fit failed.'

                except Exception:
                    annotation = 'Oscilloscope error - grab failed.'

                self.annotate_canvas(annotation, color='C0', update_global_i=False, update_canvas_afterwards=False)

                self.update_canvas(copy_to_clipboard=False, disable_autosave=True)

            # Assume initial position is zero delay pos, so put stage back there after complete scan
            self.zstage.move_by(+scan_range_mm / 2)

            # Exit the FOR loop if the thread is to be aborted
            if self.ac_scanner_thread.wants_abort:
                print('Killing AC thread NOW.')
                break

    def onPushSaveAutocorrelatorDataBtn(self):
        """ Saves grabbed autocorrelator data to a text file, appending a header and datetime stamp too. """
        header1 = '# Autocorrelation measured with MQ TPA autocorrelator'
        header2 = '# Date: %s\n' % time.asctime()

        # Open dialgoue window then save data to the user-specified path
        savefile_path = QFileDialog.getSaveFileName(self, 'Save grabbed data', filter="Data files (*.dat);;All files (*.*)")
        if savefile_path[0]:  # If user presses cancel, two empty strings return, so only process for an OK click
            # There's a strange occurence where getSaveFileName sometimes returns the extensions, and other times doesn't (perhaps Qt4/5 issue?). Catch this:
            if ('Data files' in savefile_path[-1]) or ('All files' in savefile_path[-1]):
                savefile_path = savefile_path[0]

            data_to_save = self.plots[self.tab_idx].grabbed_data.copy()

            with open(savefile_path, 'wb') as f:
                f.write(header1.encode())  # Encode converts string to bytes object for python 3 (since file has to be opened in wb mode)
                f.write(header2.encode())
                np.savetxt(f, data_to_save)

            self.setStatusBar('Data saved to %s' % savefile_path)

            # Add the recently assigned file name to the plot title
            save_file_name = savefile_path.replace('\\', '/')  # Default paths to linux style (works on Windows too, but not vice versa)
            display_filepath = save_file_name.split('/')[-2] + '/' + save_file_name.split('/')[-1]

            savefile_path_img = savefile_path[:-4].replace('.', ',') + '.dat'  # Strip off dots from file name so it allows saving an image
            self.plots[self.tab_idx].ax.set_title(display_filepath)
            self.update_canvas(self, save_png_path=savefile_path_img)

    #######################
    # PLOT AREA FUNCTIONS #
    #######################

    def update_canvas(self, span_selector_enable=True, save_png_path=None, copy_to_clipboard=True, disable_autosave=False):
        """ Updates the canvas with the latest data in self.ax and saves a copy of the canvas to disk """
        # Global plot formatting
        self.plots[self.tab_idx].ax.grid(True)
        try:
            self.plots[self.tab_idx].ax.get_yaxis().get_major_formatter().set_scientific(False)  # Turn off exponent form in y-axis
            self.plots[self.tab_idx].ax.get_yaxis().get_major_formatter().set_useOffset(False)
            self.plots[self.tab_idx].ax.get_xaxis().get_major_formatter().set_scientific(False)  # Turn off exponent form in x-axis
            self.plots[self.tab_idx].ax.get_xaxis().get_major_formatter().set_useOffset(False)
        except Exception:  # Error arises for axis manipulation beam plot and time-driven plots
            pass

        self.plots[self.tab_idx].figure.tight_layout(pad=0.2)
        self.plots[self.tab_idx].figure.canvas.draw()

        if copy_to_clipboard:
            self.copy_canvas()

        if not disable_autosave:
            # Save the plotted file automatically to the same directory (if selected in user config file), but only if the data file has been saved already
            if self.automatically_save_plots_to_disk:
                if 'Data Grab' in self.filesList.item(0).text():
                    if save_png_path:
                        self.save_file_name = self.save_file_name.replace('.', ',')  # Replace full stops with commas, since full stops aren't permitted in file names saved by Python
                        self.plots[self.tab_idx].figure.savefig(save_png_path[:-4], dpi=self.savefig_dpi)
                else:
                    self.save_file_name = self.save_file_name.replace('.', ',')  # Replace full stops with commas, since full stops aren't permitted in file names saved by Python
                    save_filepath = os.path.dirname(self.filesList.item(0).text()) + '/' + self.save_file_name
                    print('Saving to:')
                    print(save_filepath)
                    print('**')
                    self.plots[self.tab_idx].figure.savefig(save_filepath, dpi=self.savefig_dpi)

        # Enable span selector
        if span_selector_enable:
            self.span = matplotlib.widgets.SpanSelector(self.plots[self.tab_idx].ax, self.get_span_coords, 'horizontal', rectprops=dict(alpha=0.4, facecolor="red"))

    def annotate_canvas(self, msg, color, update_global_i=True, update_canvas_afterwards=True):
        """ Adds the argument msg to the canvas at a convenient position. """
        self.plots[self.tab_idx].ax.text(0.02, (0.85 - (self.global_i * 0.09)), msg, color=color, transform=self.plots[self.tab_idx].ax.transAxes)
        if update_global_i:
            self.global_i = self.global_i + 1

        if update_canvas_afterwards:
            self.update_canvas()

    def copy_canvas(self, info=None):
        """ Copies the matplotlib figure canvas to the clipboard for easy pasting into notes etc. """
        # If live_view is enabled, the grabbing and plotting commands come from a thread, which creates problems
        # when it comes to copying to clipboard. Should be resolvable using pythoncom.CoInialise() but this didn't work.
        # Hence, this IF statement is a quick work-around.
        if not self.live_view_active:
            # Qt wants us to save the figure to disk before copying to clipboard
            temp_img_filepath = 'temp.png'
            self.plots[self.tab_idx].figure.savefig(temp_img_filepath, dpi=self.savefig_dpi)
            tempImg = QImage(temp_img_filepath)
            self.cb = QApplication.clipboard()
            self.cb.setImage(tempImg)
            try:
                os.remove(temp_img_filepath)
            except Exception:
                pass

    def get_span_coords(self, x_min, x_max):
        self.x_min = x_min
        self.x_max = x_max
        x_span = x_max - x_min
        x_centre = x_min + 0.5 * x_span
        # Try to automatically detect units to display the selected range in status bar
        try:
            xlabel = self.plots[self.tab_idx].ax.get_xlabel()
            units = xlabel.split('(')[-1].split(')')[0]
            selected_range_text = 'Selection: %0.3f to %0.3f %s. Span: %0.3f %s. Centre: %0.3f %s' % (x_min, x_max, units, x_span, units, x_centre, units)
            self.setStatusBar(selected_range_text)
        except Exception:
            # If this fails, simply move on and don't raise an exception.
            pass

    def createStatusBar(self):
        self.statusBar().showMessage('Ready')

    def setStatusBar(self, text, timeout=None, timestamp=False):
        # Latex not support so remove Latex formatting
        text = text.replace('$\mu$', 'u')

        if timestamp:
            stamp = '[%s]' % time.strftime('%H:%M:%S')
        else:
            stamp = ''
        if timeout is not None:
            self.statusBar().showMessage(stamp + text, timeout)
        else:
            self.statusBar().showMessage(stamp + text)

    def show_warning_dialog(self, message):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setText(message)
        msg.setWindowTitle('Warning')
        msg.exec_()

    def show_error_dialog(self, message):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setText(message)
        msg.setWindowTitle('Error')
        msg.exec_()

    def except_hook(self, cls, exception, traceback):
        """ Reimplementation of general exception handler (http://stackoverflow.com/questions/35596250/pyqt5-gui-crashes-when-qtreewidget-is-cleared).
        When an error occurs, an abbreviated message is shown in a warning box to alert the user, while the full traceback exception print-out is shown in the terminal. """
        self.show_error_dialog('Unexpected Error: %s\n%s\n\nSee terminal for full error trace.' % (cls, exception))
        sys.__excepthook__(cls, exception, traceback)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWin = MainWindow()

    # In PyQt v5.5 an unhandled Python exception will result in a call to Qt's qFatal() function. By default this will call abort() and the application will terminate
    # Override this to force the error to print and allow user to carry on in the GUI
    sys.excepthook = mainWin.except_hook

    mainWin.show()
    sys.exit(app.exec_())
