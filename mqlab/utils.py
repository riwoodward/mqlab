""" Utils for data grabbing, manipulation and analysis. """
from __future__ import division, print_function, absolute_import, unicode_literals
from builtins import ascii, bytes, chr, dict, filter, hex, input, int, map, next, oct, open, pow, range, round, str, super, zip

import serial
import os
import numpy as np
import pickle as Pickle
from glob import glob
from scipy.optimize import curve_fit
from scipy.interpolate import InterpolatedUnivariateSpline
from scipy.constants import c

###############################
# PYTHON 2 TO 3 COMPATIBILITY #
###############################
# Enable checking if objects are strings (http://stackoverflow.com/questions/11301138/how-to-check-if-variable-is-string-with-python-2-and-3-compatibility)
try:
    basestring  # Py2
except NameError:
    basestring = str  # Py3

####################
# USEFUL CONSTANTS #
####################
c_mm_ps = c * 1e3 / 1e12   #: Speed of light in vacuum [mm/ps]
c_mm_s = c * 1e3           #: Speed of light in vacuum [mm/s]

#: Deconvolution factors to convert from measured AC FWHM to true pulse FWHM.
#:
#: References:
#:     http://spie.org/x32463.xml, R. Paschotta
ac_deconvolution_factor = {
    'sech': 0.647,
    'sech2': 0.647,
    'gaussian': 0.707,
    'triangular': 0.692,
    'rectangular': 1
}


#######################
# MISC HARDWARE UTILS #
#######################


def available_serial_ports():
    """ Returns a list of available COM ports on a computer.

    Useful for identifying a COM port quickly when using a USB-Serial adapter.
    """
    ports = []
    if os.name == 'nt':  # Windows
        for port_number in range(256):
            # Try connecting to each port and return array of those which were successful
            try:
                s = serial.Serial('COM%i' % port_number)
                ports.append('COM%i' % (port_number))
                s.close()
            except serial.SerialException:
                pass
    else:  # Unix (CHECK: this code needs testing)
        ports = sorted(glob('dev/ttyUSB*'))
        ports.reverse()  # Reverse list so the most recently attached USB serial port is first in line (i.e. use [0] index to reference it)

    if len(ports) == 0:
        ports.append('No COM port')
    return ports


def decimal_to_bool_array(decimal, num_bits=8):
    """ Convert base-10 integer to base-2 format comprising num_bits, represented by an array of boolean (0 or 1) values. """
    bool_list = [int(x) for x in list('{:0{num_bits}b}'.format(decimal, num_bits=num_bits))]
    bool_list.reverse()  # Reverse list so bool_list[0] = bit 0
    return np.array(bool_list)


######################
# DATASET PROCESSING #
######################


def read_data(file_path, data_source):
    """ Reads in data to array from a file_path, taking into account a wide variety of source file formats
    from different devices.

    Args:
        file_path : location of file (string)
        data_source : device used to record data: 'osa', 'osc' (includes autocorrelators and streak cams), 'esa', 'ccd', 'cary'
    Outputs:
        - data: data[:,0] = x axis, data[:,1] = y axis. Units are always SI.
    """
    # Determine which OSA the trace came from
    with open(file_path, 'r') as f:
        first_line = f.readline()

    if data_source == 'osa':
        # For Ando AQ6317B when saving files to a floppy disk
        if first_line[-5] == 'T':
            data = np.genfromtxt(file_path, delimiter=',', skip_header=3, skip_footer=18)
        # For Thorlabs FTIR
        elif 'Thorlabs FTS' in first_line:
            data = np.genfromtxt(file_path, delimiter=';', skip_header=82, skip_footer=1)
        # For all other experimental data (assuming using mqlab grab facility)
        else:
            data = np.loadtxt(file_path)

    elif data_source == 'osc':
        data = np.loadtxt(file_path)

    elif data_source == 'esa':
        data = np.loadtxt(file_path)

    elif data_source == 'ccd':
        pass

    elif data_source == 'cary':  # Cary spectrophotometer
        # First find the end-point (further rows simply detail the device settings)
        with open(file_path, 'r') as f:
            all_lines = f.readlines()
            for i, line in enumerate(all_lines):
                if line == '\n':
                    end_rows_to_skip = len(all_lines) - i
                    break

        all_data = np.genfromtxt(file_path, skip_header=2, skip_footer=end_rows_to_skip, delimiter=',')
        # Ignore the baselines and just use transmission data
        data = np.column_stack([all_data[:, 4], all_data[:, 5]])
        # Ignore noise
        data[:, 1][data[:, 1]<0] = 0
    else:
        raise ValueError('Data source not recognised.')

    return data


# Define unit dictionary
unit_dict = {
    -24: 'y',     # yocto
    -21: 'z',     # zepto
    -18: 'a',     # atto
    -15: 'f',     # femto
    -12: 'p',     # pico
    -9: 'n',      # nano
    -6: r'$\mu$',  # micro
    -3: 'm',      # mili
    -2: 'c',      # centi
    -1: 'd',      # deci
    0: '',        # NONE
    3: 'k',       # kilo
    6: 'M',       # mega
    9: 'G',       # giga
    12: 'T',      # tera
    15: 'P',      # peta
    18: 'E',      # exa
    21: 'Z',      # zetta
    24: 'Y',      # yotta
}


def unit_dict_return_exp(target_prefix):
    """ Return exponential multiplier for a given label.

    Args:
        target_prefix (str): prefix of interest e.g. 'M'
    Examples:
        >>> unit_dict_return_exp('M')
        6
    """
    for exp, prefix in unit_dict.items():
        if prefix == target_prefix:
            return exp


def eng_prefix(x, force_use_of_n_instead_of_u=False):
    """ Given a floating-point quantity, returns mantissa as the nearest engineering-exponented mantissa value and the corresponding prefix.

    Args:
        x : array of values
        force_use_of_n_instead_of_u : for forcing wavelengths to be displayed in nm. Set False unless you explicitly want this.
    Returns:
        (array of x values divided by the multiplier corresponding to string value of the prefix, prefix label as string)
    """
    # Legacy function to allow argument to be the data source label (i.e. for 'osa' use nm scale)
    if (force_use_of_n_instead_of_u is True) or (force_use_of_n_instead_of_u == 'osa'):
        force_use_of_n_instead_of_u = True
    else:
        force_use_of_n_instead_of_u = False

    # If passed an array, use near the half point to evaluate the prefix
    if np.size(x) > 1:
        evaluation_value = abs(x[int(0.6 * np.size(x))])
    else:
        evaluation_value = abs(x)

    # Catch zero input
    if evaluation_value == 0:
        return 0.0, ''

    # Get exponent for the single value
    exp = np.floor(np.log10(evaluation_value))

    engr_exp = int(exp - (exp % 3))  # Round exponent down to nearest multiple of 3
    mantissa = x / (10**engr_exp)

    if force_use_of_n_instead_of_u:
        if exp == -6:
            engr_exp = -9
            mantissa = mantissa * 1e3

    mantissa = np.round(mantissa, 12)  # Round to 12 decimal places (thus discounting any spurious negligible decimal places due to floating point precision)
    return mantissa, unit_dict[engr_exp]


def sorted_interpolated_univariate_spline(x, y):
    """ Return a spline object given two equal length arrays which are not necessarily monotonically increasing. """
    # TODO: try to speed this up? Perhaps just use an if statement to see if the list is the wrong-way round?
    # Combine lists into list of tuples
    points = zip(x, y)
    # Sort list of tuples by x-value
    points = sorted(points, key=lambda point: point[0])
    # Split list of tuples into two list of x values any y values
    x1, y1 = zip(*points)
    return InterpolatedUnivariateSpline(x1, y1)


def smooth(x, window_len=10, window='hanning'):
    """ Smooth the data using a window with requested size.
    This method is based on the convolution of a scaled window with the signal.
    The signal is prepared by introducing reflected copies of the signal (with the window size) in both ends so that transient parts
    are minimized in the begining and end part of the output signal.

    Args:
        x : the input signal
        window_len: the dimension of the smoothing window
        window: the type of window from 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'
          flat window will produce a moving average smoothing.
    Returns:
        array : the smoothed signal
    See also:
        numpy.hanning, numpy.hamming, numpy.bartlett, numpy.blackman, numpy.convolve, scipy.signal.lfilter
    References:
        http://wiki.scipy.org/Cookbook/SignalSmooth
    """
    window_len = int(window_len)
    if x.ndim != 1:
        raise ValueError("Smooth only accepts 1 dimension arrays.")
    if x.size < window_len:
        raise ValueError("Input vector needs to be bigger than window size.")
    if window_len < 3:
        return x
    if window not in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
        raise ValueError("Window can only be one of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'")
    ss = np.r_[2 * x[0] - x[window_len:1:-1], x, 2 * x[-1] - x[-1:-window_len:-1]]
    if window == 'flat':  # moving average
        w = np.ones(window_len, 'd')
    else:
        w = eval('sp.' + window + '(window_len)')
    y = np.convolve(w / w.sum(), ss, mode='same')
    return y[window_len - 1: -window_len + 1]


def normalise(data, subtract_base=True, subtract=None, noisy_base=False, scale='lin', return_y_shift=False):
    """ Normalise data to a 0 to 1 scale.

    Args:
        data (array) : 1D array of data values
        subtract (float): if given, manually subtract this value from the data (overrides subtract_base and noisy_base args)
        subtract_base (bool): if True, take minimum value in data as baseline and subtract this off
        noisy_base (bool): if True, the baseline value is estimated by averaging bottom 5% of data, then subtracted before normalisation
        scale (str): 'log' or 'lin'
        return_y_shift (bool) : if True, the shift in log scale is returned as well as the normalised data (not possible for lin scales as this would be meaningless)
    """
    y = np.asarray(data)

    if scale is 'log':
        y = 10**(y / 10)

    if subtract is None:
        if subtract_base:
            if noisy_base:
                y_base = np.mean(y[y < (0.05 * (y.max() - y.min()) + y.min())])
                y -= y_base
            else:
                y = y - y.min()
    else:
        y = y / y.max()
        y = y - subtract

    y_normalised = y / y.max()

    if scale is 'log':
        y_normalised = 10 * np.log10(y_normalised)
        y_shift = y_normalised.max() - data.max()

    if return_y_shift:
        return y_normalised, y_shift
    else:
        return y_normalised


def centre_on_zero(x, y, threshold=0.5, scale='lin', direction='inward', interpolate=False):
    """ Centre a dataset to zero, using the dataset_edges.

    Returns:
        tuple containing:
        - *array*: **x_centred**
        - *array*: **y** (same as original argument)
        - *float*: shift magnitude in x
    """
    x_centre = centre_of_dataset(x=x, y=y, threshold=threshold, scale=scale, direction=direction, interpolate=interpolate)
    x_centred = (x - x_centre)
    shift = x[0] - x_centred[0]
    return x_centred, y, shift


def find_dataset_edges(x, y, threshold=0.5, scale='lin', direction='inward', interpolate=False):
    """ Return edges of (x,y) dataset, based on a thresholding method.

    Args:
        x (array): x data values
        y (array): y data values
        threshold (float): factor of the peak value at which width is found (e.g. 0.5 = 3 dB width; 0.25 = 6 db width)
        scale (str): scale of y-axis, 'log' or 'lin'. Note: x-axis is always assumed to have linear scale.
        direction (str): search direction for intersection between threshold and data; 'outward' from peak or 'inward' from exterior data boundaties
        interpolate (bool) : the accuracy of this function is limited by data density. To improve this, set True, and a spline fitting and root finding method will be performed (~ 5x slower though).
    Returns:
        tuple containing:
        - *float*: lower edge
        - *float*: upper edge
    References:
        Adapted from Ando AQ6317B Manual, p5-181, http://denethor.wlu.ca/pc474/manuals/AQ6317B_R0101.pdf
    """
    if ((threshold > 1) or (threshold < 0)):
        raise ValueError('Threshold is a factor of the peak value and must be in range 0 to 1.')

    # Linearise data (if in log scale)
    if scale == 'log':
        y = 1e-3 * 10**(y / 10)
    # Normalise data, to make it work for data in the y-axis in the range 0.3 to 0.5, say
    y = normalise(y)

    # Find index of data peak
    ipeak = np.argmax(y)
    if interpolate:
        spl = sorted_interpolated_univariate_spline(x, y - threshold)
        roots = spl.roots()
        if 'out' in direction:
            roots_offset_from_peak = roots - x[ipeak]
            x1 = x[ipeak] - min(abs(roots_offset_from_peak[roots_offset_from_peak < 0]))  # first root to LHS of peak
            x2 = x[ipeak] + min(roots_offset_from_peak[roots_offset_from_peak > 0])       # first root to RHS of peak
        elif 'in' in direction:
            x1 = roots[0]
            x2 = roots[-1]
    else:
        threshold_value = y[ipeak] * threshold
        if 'out' in direction:
            upper_irange = np.where((y <= threshold_value) & (x > x[ipeak]))  # range of indices where intensity < half-peak, above peak wl
            lower_irange = np.where((y <= threshold_value) & (x < x[ipeak]))  # range of indices where intensity < half-peak, below peak wl
            x2 = x[upper_irange].min()
            x1 = x[lower_irange].max()
        elif 'in' in direction:
            iis = (y >= threshold_value)
            x2 = x[iis].max()
            x1 = x[iis].min()
        else:
            raise ValueError('Direction not recognised; must be "inward" or "outward".')
    return x1, x2


def width_of_dataset(x, y, threshold=0.5, scale='lin', direction='inward', interpolate=False):
    """ Calculate width based on a given threshold, i.e. full width at some % of max.

    Args:
        x (array) : x data values
        y (array) : y data values
        threshold (float): factor of the peak value at which width is found (e.g. 0.5 = 3 dB width; 0.25 = 6 db width)
        scale (str): scale of y-axis, 'log' or 'lin'. Note: x-axis is always assumed to have linear scale.
        direction (str): search direction for intersection between threshold and data; 'outward' from peak or 'inward' from exterior data boundaties
        interpolate (bool): the accuracy of this function is limited by data density. To improve this, set True, and a spline fitting and root finding method will be performed (~ 5x slower though).
    """
    x1, x2 = find_dataset_edges(x=x, y=y, threshold=threshold, scale=scale, direction=direction, interpolate=interpolate)
    return x2 - x1


def centre_of_dataset(x, y, threshold=0.5, scale='lin', direction='inward', interpolate=False):
    """ Calculate centre of dataset based on a given threshold.

    It finds edges at threshold then averages them.

    Args:
        x (array) : x data values
        y (array) : y data values
        threshold (float): factor of the peak value at which width is found (e.g. 0.5 = 3 dB width; 0.25 = 6 db width)
        scale (str): scale of y-axis, 'log' or 'lin'. Note: x-axis is always assumed to have linear scale.
        direction (str): search direction for intersection between threshold and data; 'outward' from peak or 'inward' from exterior data boundaties
        interpolate : the accuracy of this function is limited by data density. To improve this, set True, and a spline fitting and root finding method will be performed (~ 5x slower though).
    """
    x1, x2 = find_dataset_edges(x=x, y=y, threshold=threshold, scale=scale, direction=direction, interpolate=interpolate)
    return (x1 + x2) / 2


def peak_detect(y, delta, x=None):
    """ Find local maxima in y.

    Args:
        y (array): intensity data in which to look for peaks
        delta (float): a point is considered a maximum peak if it has the maximal value, and was preceded (to the left) by a value lower by DELTA.
        x (array, optional): correspond x-axis
    Returns:
        tuple containing:
        - *array*: indices of peaks / the x-values of peaks if x arg was passed
        - *array* : y values of peaks
    References:
        Converted from MATLAB script at http://billauer.co.il/peakdet.html.
    """
    maxtab = []
    mintab = []

    if x is None:
        x = np.arange(len(y))

    y = np.asarray(y)
    mn, mx = np.Inf, -np.Inf
    mnpos, mxpos = np.NaN, np.NaN
    lookformax = True

    for i in np.arange(len(y)):
        this = y[i]
        if this > mx:
            mx = this
            mxpos = x[i]
        if this < mn:
            mn = this
            mnpos = x[i]

        if lookformax:
            if this < mx - delta:
                maxtab.append((mxpos, mx))
                mn = this
                mnpos = x[i]
                lookformax = False
        else:
            if this > mn + delta:
                mintab.append((mnpos, mn))
                mx = this
                mxpos = x[i]
                lookformax = True
    return np.array(maxtab)  # , np.array(mintab). For now, only retun the PEAKS, not troughs


###########
# FITTING #
###########

def gaussian(x, amplitude, width, x_offset, y_offset):
    """ Gaussian Function.

    Args:
        x : x-axis
        amplitude : peak value
        width : s.d.
        x_offset : x-axis offset
        y_offset : y-axis offset
    """
    return amplitude * np.exp(-(x - x_offset)**2 / (2 * width**2)) + y_offset


def sech2(x, amplitude, width, x_offset, y_offset):
    """ Sech^2 Function.

    Args:
        x : x-axis
        amplitude : peak value
        width : width parameter. If this is for a pulse intensity profile, (FWHM duration = 1.76*this parameter)
        x_offset : x-axis offset
        y_offset : y-axis offset
    """
    return amplitude * np.cosh((x - x_offset) / width)**-2 + y_offset


def fit(x, y, fit_type, p0=0, sigma=None):
    """ Performs a fit (distribution specified by type) to data in (x,y). Returns the fit coefficients and covariance matrix """
    if not p0:  # Estimate fitting parameters for p0 [only works for sech2 and gaussian fits]
        p0_peak = max(y)
        p0_width = width_of_dataset(x, y)
        p0_x_offset = x[np.argmax(y)]
        p0_y_offset = 0.5
        p0 = [p0_peak, p0_width, p0_x_offset, p0_y_offset]

    if isinstance(fit_type, basestring):  # If fit_type is a string
        if 'poly' in fit_type:
            coeff = np.polyfit(x, y, fit_type.split('-')[-1])
            pcov = 0  # No covariance matrix computed
        elif 'sech2' in fit_type: coeff, pcov = curve_fit(sech2, x, y, p0, sigma)
        elif 'gaussian' in fit_type: coeff, pcov = curve_fit(gaussian, x, y, p0, sigma)
    else:
        coeff, pcov = curve_fit(fit_type, x, y, p0, sigma)  # Return co-effs for fit and covariance matrix
    return coeff, pcov


def fitted(x, y, fit_type, p0=None, sigma=None):
    """ Performs a fit to data in (x,y) via the FIT function and returns fitted data.

    Args:
        x (array): x values
        y (array): y values
        fit_type (str): fitting function name OR 'sech2'/'gaussian' to use a standard pulse shape OR 'poly-#' where # indicates order of polynomial
        p0 (array): tuple of seed fitting parameters, leave blank to 'guess' them
        sigma (array): uncertainties in the y data, used as weights in the least-squares problem i.e. minimising np.sum( ((f(xdata, coefs) - ydata) / sigma)^2 )
    Returns:
        x_fit, y_fit : x & y data for the fit with 10,000 points
        coeff : fit coefficients
        pcov : covariance matrix
    """
    if fit_type == 'sech':
        print('Assuming that the sech pulse intensity is used -> a sech2 profile is being used.')
        fit_type = 'sech2'  # Legacy compatibility

    # Perform fitting
    coeff, pcov = fit(x, y, fit_type, p0, sigma)

    # Populate new dense arrays with the fitted function (for plotting accurately)
    x_fit = np.linspace(min(x), max(x), 1e4)

    if isinstance(fit_type, basestring):  # If fit_type is a string
        if 'poly' in fit_type:
            p = np.poly1d(coeff)
            y_fit = p(x_fit)
        elif 'sech2' in fit_type: y_fit = sech2(x_fit, *coeff)
        elif 'gaussian' in fit_type: y_fit = gaussian(x_fit, *coeff)
    else:
        y_fit = fit_type(x_fit, *coeff)

    return x_fit, y_fit, coeff, pcov


########################
#   MISC CODING TOOLS  #
########################

class empty_object(object):
    """ An empty class which is useful for coding in an OOP style. """
    pass


def pickle_object(source_object, target_file_path):
    """ Save an object to disk at location: target_file_path.
    No file extension is defined, but .p is a good choice.
    """
    Pickle.dump(source_object, open(target_file_path, "wb"))


def unpickle_object(file_name):
    """ Returns a previously pickled object from file_name. """
    return Pickle.load(open(file_name, "rb"))
