#!/usr/bin/env python
"""
Statstical analysis of the presynaptic terminal.

Common usage contains the following steps:

1) Setup pickles: Make pickles that contain data from all individual 
segmentation & analysis pickles:

  - Make catalog files for each tomogram in ../catalog/
  - cd to this directory, then in ipython (or similar) execute:
      > import work
      > from work import *
      > work.main(individual=True, save=True)

  This should create few pickle files in this directory (tethers.pkl, 
  sv.pkl, ...)

2) Create profile: not required, but advantage keeps profile-specific history
 
  - Create ipython profile for your project: 
      $ ipython profile create <project_name>
  - Create startup file for this profile, it enough to have:
      import work
      work.main()
      from work import *

3) Analysis

  - Start ipython (qtconsole is optional, profile only if created):
      $ ipython qtconsole  --profile=project_name --pylab=qt
  - In ipython (not needed if profile used):
      > import work
      > work.main()
      > from work import *
  - Run individual analysis commands (from SV distribution section and below)

  - If work.py is edited during an ipython session:
      > reload(work)
      > from work import *


# Author: Vladan Lucic (Max Planck Institute for Biochemistry)
# $Id: presynaptic_stats.py 1101 2014-12-29 11:07:41Z vladan $
"""

__version__ = "$Revision: 1101 $"


import sys
import os
import logging
import itertools
from copy import copy, deepcopy
import pickle

import numpy 
import scipy 
import scipy.stats
try:
    import matplotlib.pyplot as plt
except ImportError:
    pass

import pyto
from pyto.analysis.groups import Groups
from pyto.analysis.observations import Observations

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s %(module)s.%(funcName)s():%(lineno)d %(message)s',
    datefmt='%d %b %Y %H:%M:%S')


##############################################################
#
# Parameters (need to be edited)
#
##############################################################

###########################################################
#
# Categories, identifiers and file names 
#

# experiment categories to be used (prints and plots according to this order)
categories = ['ko_1', 'wt_1', 'ko_2', 'wt_2']

# experiment identifiers
identifiers = [
    'ko_1_1', 'ko_1_3', 'ko_1_6',
    'wt_1_1', 'wt_1_2',
    'ko_2_1', 'ko_2_2', 'ko_2_5',
    'wt_2_3', 'wt_2_4']

# select identifiers to remove
identifiers_discard = ['ko_1_3' ] 

# set identifiers
identifiers = [ident for ident in identifiers 
               if ident not in identifiers_discard]
#identifiers = None

# reference category
reference = {'ko_1' : 'wt_1'
             'wt_1' : 'wt_1',
             'ko_2' : 'wt_2',
             'wt_2' : 'wt_2'}

# catalog directory
catalog_directory = '../catalogs'

# catalogs file name pattern (can be a list of patterns) 
catalog_pattern = r'[^_].*\.py$'   # extension 'py', doesn't start with '_'

# names of properties defined in catalogs (that define data files)
tethers_name = 'tethers_file'
connectors_name = 'connectors_file'
sv_name = 'sv_file'
sv_membrane_name = 'sv_membrane_file'
sv_lumen_name = 'sv_lumen_file'
layers_name = 'layers_file'
clusters_name = 'cluster_file'   

# names of pyto.analysis.Connections, Vesicles and Layers pickle files that
# are generated and further analyzed by this script
sv_pkl = 'sv.pkl'
tethers_pkl = 'tether.pkl'
connectors_pkl = 'conn.pkl'
layers_pkl = 'layer.pkl'
clusters_pkl = 'cluster.pkl'

###########################################################
#
# Parameters
#

# vesicle radius bins (small, medium, large), svs are medium
vesicle_radius_bins = [0, 10, 30, 3000]

# distance bins for layers
distance_bins = [0, 45, 75, 150, 250]
layer_distance_bins = [10, 45, 75, 150, 250]
distance_bin_references = {
             'proximal' : 'proximal',
             'intermediate' : 'proximal',
             'distal_1' : 'proximal',
             'distal_2' : 'proximal',
             'all' : 'all'}
reference.update(distance_bin_references)
distance_bin_names = ['proximal', 'intermediate', 'distal_1', 'distal_2']
#distance_bin_num = ['0-45', '45-75', '75-150', '150-250']
distance_bins_label = 'Distance to the AZ [nm]'

# tether and connector length bins
rough_length_bins = [0, 5, 10, 20, 40]
rough_length_bin_names = ['<5', '5-9', '10-19', '20-40']
fine_length_bins = [0, 5, 10, 15, 20, 25, 30, 35, 40]
fine_length_bin_names = ['<5', '5-9', '10-14', '15-19', '20-24', 
                         '25-29', '30-34', '35-40']
tether_length_bins = [0, 5, 500]
tether_length_bin_names = ['short', 'long']

# connected_bins = [0,1,100]
teth_bins_label = ['non-tethered', 'tethered']
conn_bins_label = ['non-connected', 'connected']

# number of connector bins
n_conn_bins = [0,1,3,100]
n_conn_bin_names = ['0', '1-2', '>2']
n_conn_bins_label = 'N connectors'
reference.update(
    {'0' : '0',
     '1-2' : '0',
     '>2' : '0'})

# RRP definition by the number of tethers
rrp_ntether_bins = [0, 3, 300]
rrp_ntether_bin_names = ['non-rrp', 'rrp']

# connected and tethered
reference.update(
    {'near_conn_sv' : 'near_conn_sv',
     'near_non_conn_sv' : 'near_conn_sv',
     'near_teth_sv' : 'near_teth_sv',
     'near_non_teth_sv' : 'near_teth_sv',
     'tethered' : 'tethered',
     'non_tethered' : 'tethered',
     'connected' : 'connected',
     'non_connected' : 'connected',
     't c' : 't c',
     'nt c' : 't c',
     't nc' : 't c',
     'nt nc' : 't c',
     't_c' : 't_c',
     'nt_c' : 't_c',
     't_nc' : 't_c',
     'nt_nc' : 't_c',
     'rrp' : 'rrp',
     'non_rrp' : 'rrp'})

# radius
radius_bins = numpy.arange(10,30,0.5)
radius_bin_names = [str(low) + '-' + str(up) for low, up 
                    in zip(radius_bins[:-1], radius_bins[1:])]


###########################################################
#
# Printing
#

# print format
print_format = {

    # data
    'nSegments' : '   %5d ',
    'surfaceDensityContacts_1' : '   %7.4f ',
    'surfaceDensityContacts_2' : '   %7.4f ',

    # stats
    'mean' : '    %5.2f ',
    'std' : '    %5.2f ',
    'sem' : '    %5.2f ',
    'diff_bin_mean' : '   %6.3f ',
    'n' : '    %5d ',
    'testValue' : '   %7.4f ',
    'confidence' : '  %7.4f ',
    'fraction' : '    %5.3f ',
    'count' : '    %5d ',
    't_value' : '    %5.2f ',
    't' : '    %5.2f ',
    'h' : '    %5.2f ',
    'u' : '    %5.2f ',
    't_bin_value' : '    %5.2f ',
    't_bin' : '    %5.2f ',
    'chi_square' : '    %5.2f ',
    'chi_sq_bin' : '    %5.2f ',
    'confid_bin' : '  %7.4f '
    }

###########################################################
#
# Plotting
#
# Note: These parameters are used directly in the plotting functions of
# this module, they are not passed as function arguments.
#

# determines if data is plotted
plot_ = True 

# legend
legend = False

# data color
color = {
    'wt_1' : 'black',
    'ko_1' : 'grey',
    'wt_2' : 'tan',
    'ko_2' : 'orange'
    }

# edge color
ecolor={}

# category labels
category_label = {
    'ko_1' : 'KO type 1',
    'wt_1' : 'WT for KO 1',
    'ko_2' : 'KO type 2',
    'wt_2' : 'WT for KO 2',
    'near_conn_sv' : 'connected',
    'near_non_conn_sv' : 'non-connected',
    'near_teth_sv' : 'tethered',
    'near_non_teth_sv' : 'non-tethered',
    'near_conn_sv' : 'connected',
    'near_non_conn_sv' : 'non-connected',
    'non_connected' : 'non-connected',
    'connected' : 'connected',
    'non_tethered' : 'non-tethered',
    'tethered' : 'tethered',
    'proximal' : '0-45',
    'intermediate' : '45-75', 
    'distal_1' : '75-150',
    'distal_2' : '150-250',
    't_c' : 'teth conn',
    't_nc' : 'teth non-conn',
    'nt_c' : 'non-teth conn',
    'nt_nc' : 'non-teth non-conn',
    'rrp' : 'RRP',
    'non_rrp' : 'non-RRP'
    }

# data alpha
alpha = {
    'ko_1' : 1,
    'wt_1' : 1,
    'ko_2' : 1,
    'wt_2' : 1
    }

# markers
marker =  {
    'ko_1' : 'o',
    'wt_1' : '*',
    'ko_2' : 'x',
    'wt_2' : 'v'
    }

# list of default markers
markers_default = ['o', 'v', 's', '*', '^', 'H', '<', 'D', '>']

# for presentations
#matplotlib.rcParams['font.size'] = 18

# markersize
marker_size = 7

# line width
line_width = {
    'mean' : 4
    }

# line width
default_line_width = 2

# thick line width
thick_line_width = 4

# line style
default_line_style = '-'

# bar arrangement
bar_arrange = 'uniform'    # all bars in a row, single bar space between groups
bar_arrange = 'grouped'    # each group takes the same space 

# flag indicating if one-sided yerr
one_side_yerr = True

# confidence format 
confidence_plot_format = "%5.3f"

# confidence font size
confidence_plot_font_size = 7

# confidence levels for 1, 2, 3, ... stars
confidence_stars = [0.05, 0.01, 0.001]


##############################################################
#
# Functions (edit only if you know what you're doing)
#
##############################################################

##############################################################
#
# Higher level functions 
#

def analyze_occupancy(
    layer, bins, bin_names, pixel_size, groups=None, identifiers=identifiers,
    test=None, reference=None, ddof=1, out=sys.stdout, 
    outNames=None, title='', yerr='sem', confidence='stars', y_label=None):
    """
    Statistical analysis of sv occupancy divided in bins according to the 
    distance to the AZ.

    Arguments:
      - layer: (Layers) layer data structure
      - bins: (list) distance bins
      - bin_names: (list) names of distance bins, has to correspond to bins
      - groups: list of group names
      - test: statistical inference test type
      - reference: specifies reference data
      - ddof: differential degrees of freedom used for std
      - out: output stream for printing data and results
      - outNames: list of statistical properties that are printed
      - title: title
      - yerr: name of the statistical property used for y error bars
      - confidence: determines how confidence is plotted
      - y_label: y axis label (default 'occupancy')
    """

    # Note: perhaps should be moved to pyto.alanysis.Layers

    # rearange data by bins
    layer_bin = layer.rebin(bins=bins, pixel=pixel_size, categories=groups)

    # make a separate Groups object for each bin
    layer_list = layer_bin.splitIndexed()

    # convert to Groups where group names are distance bins and identifiers
    # are trwetment names
    converted = pyto.analysis.Groups.joinExperimentsList(
        groups=groups, identifiers=identifiers,
        list=layer_list, listNames=bin_names, name='occupancy')

    # do statistics and plot
    result = stats(
        data=converted, name='occupancy', join=None, groups=bin_names, 
        identifiers=groups, test=test, reference=reference, ddof=ddof, 
        out=out, outNames=outNames, title=title, yerr=yerr, 
        label='experiment', confidence=confidence, y_label=y_label)

    return result

def stats_list(
    data, dataNames, name, join='join', bins=None, fraction=1, groups=None, 
    identifiers=None, test=None, reference=None, ddof=1, out=sys.stdout, 
    label=None, outNames=None, plot_=True, yerr='sem', confidence='stars',
    title='', x_label=None, y_label=None):
    """
    Statistical analysis of data specified as a list of Groups objects.

    First, the data from idividual observations of each group are joined. In 
    this way each group (of arg data) becomes one observation and the elements
    of data list become groups. 

    Arguments:
      - data: (list of Groups) list of data structures
      - dataNames: (list of strs) names corrensponfing to elements of arg data, 
      have to be in the same order as the data
      - name: name of the analyzed property
      - join: 'join' to join experiments, otherwise None
      - bins: (list) bins for making histogram
      - fraction: bin index for which the fraction is calculated
      - groups: list of group names
      - identifiers: list of identifiers
      - test: statistical inference test type
      - reference: specifies reference data
      - ddof: differential degrees of freedom used for std
      - out: output stream for printing data and results
      - outNames: list of statistical properties that are printed
      - yerr: name of the statistical property used for y error bars
      - plot_: flag indicating if the result are to be plotted
      - label: determines which color, alpha, ... is used, can be 'group' to 
      label by group or 'experiment' to label by experiment
      - confidence: determines how confidence is plotted
      - x_label: x axis label
      - y_label: y axis label, if not specified arg name used instead 
      - title: title
    """

    # make one groups object by joining observations
    together = Groups.joinExperimentsList(
        list=data, listNames=dataNames, name=name, mode=join,
        groups=groups, identifiers=identifiers)

    # do stats 
    result = stats(
        data=together, name=name, join=None, bins=bins, fraction=fraction, 
        groups=dataNames, identifiers=groups, test=test, reference=reference, 
        ddof=ddof, out=out, outNames=outNames, yerr=yerr, label='experiment', 
        confidence=confidence, title=title, x_label=x_label, y_label=y_label)

    return result

def stats_list_pair(
    data, dataNames, name, groups=None, identifiers=None, 
    test='t_rel', reference=None,  out=sys.stdout, yerr='sem', ddof=1, 
    outNames=None, plot_=True,label=None, confidence='stars',
    title='', x_label=None, y_label=None):
    """
    Statistical analysis of paired data specified as a list of Groups objects. 

    Unlike in stats_list(), the data has to be paired so that all Groups
    objects (elements of arg data) have to have the same group names, and the 
    same identifiers.

    First, the means of the data (arg name) from all idividual observations of 
    each group are calculated. In this way each group (of arg data) becomes one
    observation and the elements of data list become groups. 

    Arguments:
      - data: (list of Groups) list of data structures
      - dataNames: (list of strs) names corrensponfing to elements of arg data, 
      have to be in the same order as the elements of data
      - name: name of the analyzed property
      - groups: list of group names
      - identifiers: list of identifiers
      - test: statistical inference test type (default 't_rel')
      - reference: specifies reference data
      - ddof: differential degrees of freedom used for std
      - out: output stream for printing data and results
      - outNames: list of statistical properties that are printed
      - yerr: name of the statistical property used for y error bars
      - plot_: flag indicating if the result are to be plotted
      - label: determines which color, alpha, ... is used, can be 'group' to 
      label by group or 'experiment' to label by experiment
      - confidence: determines how confidence is plotted
      - x_label: x axis label
      - y_label: y axis label, if not specified arg name used instead 
      - title: title
    """

    # make one groups object by joining observations
    together = Groups.joinExperimentsList(
        list=data, listNames=dataNames, name=name, mode='mean', 
        removeEmpty=False)

    # do stats 
    result = stats(
        data=together, name=name, join='pair', 
        groups=dataNames, identifiers=groups, test=test, reference=reference, 
        ddof=ddof, out=out, outNames=outNames, yerr=yerr, label='experiment', 
        confidence=confidence, title=title, x_label=x_label, y_label=y_label)

    return result

def stats(data, name, bins=None, bin_names=None, fraction=None, join=None, 
          groups=None, identifiers=None, test=None, reference=None, ddof=1, 
          out=sys.stdout, label=None, outNames=None, plot_=True, plot_name=None,
          yerr='sem', confidence='stars', title='', x_label=None, y_label=None):
    """
    Does statistical analysis of data specified by args data and name, prints
    and plots the results as a bar chart.

    In case arg bins is specified, data (arg name) of all observations 
    belonging to one group are first joined (arg join) and then converted to a
    histogram according to arg bins (property name 'histogram'). Also 
    calculated are probabilities for each histogram bin (property name 
    'probability') and the probability for bin indexed by arg fraction is
    saved separately as property 'fraction'. For example, fraction of connected
    vesicles is obtained for name='n_connection', bins=[0,1,100], fraction=1.

    In case arg join is None a value is printed and a bar is plotted for each 
    experiment. This value is either the value of the specified property if 
    scalar, or a mean of the property values if indexed.

    If arg join is 'join', the values of the specified property are pooled 
    accross all experiments belonging to one group, and the mean is 
    printed and plotted. 

    If arg join is 'mean', the mean of experiment means for each group 
    (indexed properties only) is printed and plotted. 

    If arg join is None and the data is indexed, both significance between 
    groups and between experiments are calculated.

    If specified, args groups and identifiers specify the order of groups
    and experiments on the x axis. 

    Arg plot_name specifies which statistical property to plot. If it is not 
    specified the property to plot is determined in the following way: if arg
    bins are not given 'mean' is plotted, otherwise if bin_names is specified
    'histogram' is plotted and if not 'fraction'. Therefore, most often 
    arg plot_name should not be given. Notable exception is for a histogram
    when instead of numer of occurences a probability (fraction) of occurences
    needs to be plotted, in which case 'fraction' should be specified.

    Arguments:
      - data: (Groups or Observations) data structure
      - bins: (list) bins for making histogram
      - fraction: bin index for which the fraction is calculated
      - name: name of the analyzed property
      - join: 'join' to join experiments, otherwise None
      - groups: list of group names
      - identifiers: list of identifiers
      - test: statistical inference test type
      - reference: specifies reference data
      - ddof: differential degrees of freedom used for std
      - out: output stream for printing data and results
      - outNames: list of statistical properties that are printed
      - yerr: name of the statistical property used for y error bars
      - plot_: flag indicating if the result are to be plotted
      - plot_name: name of the calculated property to plot
      - label: determines which color, alpha, ... is used, can be 'group' to 
      label by group or 'experiment' to label by experiment
      - confidence: determines how confidence is plotted
      - x_label: x axis label
      - y_label: y axis label, if not specified arg name used instead 
      - title: title

    ToDo: include stats_x in stats
    """

    # prepare for plotting
    if plot_:
        plt.figure()

    # makes sure elements of bin_names are different from those of 
    # category_label (appends space(s) to make bin_names different)
    if bin_names is not None:
        fixed_bin_names = []
        for bin_nam in bin_names:
            while(bin_nam in category_label):
                bin_nam = bin_nam + ' '
            fixed_bin_names.append(bin_nam)
        bin_names = fixed_bin_names

    # determine which property to plot
    if plot_name is None:
        if bins is None:
            plot_name = 'mean'
        else:
            if bin_names is None:
                plot_name = 'fraction'
            else:
                plot_name='histogram'

    # figure out if indexed
    indexed = name in data.values()[0].indexed

    if isinstance(data, Groups):
        if not indexed:

            # not indexed
            if join is None:
                
                # groups, scalar property, no joining
                data.printStats(
                    out=out, names=[name], groups=groups, 
                    identifiers=identifiers, format_=print_format, title=title)
                if plot_:
                    plot_stats(
                        stats=data, name=name, groups=groups, 
                        identifiers=identifiers, yerr=None, confidence=None)

            elif join == 'join':

                # groups, scalar property, join
                stats = data.joinAndStats(
                    name=name, mode=join, groups=groups, 
                    identifiers=identifiers, test=test, reference=reference, 
                    ddof=ddof, out=out, outNames=outNames,
                    format_=print_format, title=title)
                if plot_:
                    plot_stats(stats=stats, name=plot_name, 
                               yerr=yerr, confidence=confidence)

            else:
                raise ValueError(
                    "For Groups data and non-indexed (scalar) property "
                    + "argument join can be None or 'join'.")

        else:

            # indexed
            if (join is None) or (join == 'pair'):

                # stats between groups and  between observations
                if groups is None:
                    groups = data.keys()

                # between experiments
                exp_ref = {}
                for categ in groups:
                    exp_ref[categ] = reference
                if join is None:
                    exp_test = test
                elif join == 'pair':
                    exp_test = None
                stats = data.doStats(
                    name=name, bins=bins, fraction=fraction, groups=groups, 
                    test=exp_test, between='experiments', 
                    reference=exp_ref, ddof=ddof, identifiers=identifiers,
                    format_=print_format, out=None)

                # between groups
                if data.isTransposable() and (len(groups)>0):
                    group_ref = {}
                    for ident in data[groups[0]].identifiers:
                        group_ref[ident] = reference
                    try:
                        stats_x = data.doStats(
                            name=name, bins=bins, fraction=fraction, 
                            groups=groups, identifiers=identifiers, test=test, 
                            between='groups', reference=group_ref, ddof=ddof,
                            format_=print_format, out=None)
    # ToDo: include stats_x in stats
                        names_x = ['testValue', 'confidence']
                    except KeyError:
                        stats_x = None
                        names_x = None
                else:
                    stats_x = None
                    names_x = None

                # print and plot
                stats.printStats(
                    out=out, groups=groups, identifiers=identifiers, 
                    format_=print_format, title=title, 
                    other=stats_x, otherNames=names_x)
                if plot_:
                    plot_stats(
                        stats=stats, name=plot_name, groups=groups, 
                        identifiers=identifiers, yerr=yerr, label=label,
                        confidence=confidence, stats_between=stats_x)

            elif (join == 'join') or (join == 'mean'):

                # groups, indexed property, join or mean
                stats = data.joinAndStats(
                    name=name, bins=bins, fraction=fraction, mode=join, 
                    test=test, reference=reference, groups=groups, 
                    identifiers=identifiers,
                    ddof=ddof, out=out, format_=print_format, title=title)

                if ((plot_name is not 'histogram') 
                    and (plot_name is not 'probability')):

                    # just plot
                    if plot_:
                        plot_stats(
                            stats=stats, name=plot_name, identifiers=groups, 
                            yerr=yerr, confidence=confidence)

                else:
                    
                    # split histogram and plot
                    stats_split = stats.splitIndexed()
                    histo_groups = Groups()
                    histo_groups.fromList(groups=stats_split, names=bin_names)

                    if plot_:
                        plot_stats(
                            stats=histo_groups, name=plot_name, 
                            groups=bin_names, identifiers=groups, yerr=yerr, 
                            confidence=confidence, label='experiment')
                    stats = histo_groups

            else:
                raise ValueError(
                    "For Groups data and indexed property "
                    + "argument join can be None, 'join', or 'mean'.")

    elif isinstance(data, list):    

        # list of groups
        raise ValueError("Please use stats_list() instead.")
    
    else:
        raise ValueError("Argument data has to be an instance of Groups "  
                         + "or a list of Groups objects.")

    # finish plotting
    if plot_:
        plt.title(title)
        if y_label is None:
            y_label = name
        plt.ylabel(y_label)
        if x_label is not None:
            plt.xlabel(x_label)
        if legend:
            plt.legend()
        plt.show()

    if indexed or (join is not None):
        return stats

def count_histogram(
    data, name='ids', dataNames=None, groups=None, identifiers=None, test=None,
    reference=None, out=sys.stdout, outNames=None, plot_=True, label=None, 
    plot_name='fraction', confidence='stars', title='', x_label=None, 
    y_label=None):
    """
    Analyses and plots the number of data items specified by arg name.

    If (arg) data is a list of Groups objects, makes a histogram of the number 
    of items for each group, so a histogram is calculated for each group. Bins 
    of one histogram corespond to Groups objects specified by (arg) data. The
    histograms are then compared statistically.

    Data from all experiemnts of a group are combined.

    If (arg) data is a Groups object, makes a histogram of the number 
    of items for each experiment identifier. It is expected that all groups 
    have the same identifiers. Bins of one histogram corespond to groups of the
    Groups objects specified by (arg) data. The histograms are then compared 
    statistically. 

    Arguments:
      - data: (list of Groups) list of data structures
      - name: name of the analyzed property
      - dataNames: (list of strs) names corrensponfing to elements of arg data, 
      have to be in the same order as the elements of data
      - groups: list of group names
      - identifiers: list of identifiers
      - test: statistical inference test type 
      - reference: specifies reference data
      - out: output stream for printing data and results
      - outNames: list of statistical properties that are printed
      - plot_: flag indicating if the result are to be plotted
      - plot_name: determines which values are plotted, can be 'count' for the
      number of elements in each bin, or 'fraction' for the fraction of 
      elements in respect to all bins belonging to the same histogram.
      - label: determines which color, alpha, ... is used, can be 'group' to 
      label by group or 'experiment' to label by experiment
      - confidence: determines how confidence is plotted
      - x_label: x axis label
      - y_label: y axis label, if not specified arg name used instead 
      - title: title
    """

    # make Groups object if data is a list
    if isinstance(data, list):

        # join list 
        class_ = data[0].__class__
        groups_data = class_.joinExperimentsList(
            list=data, name=name, listNames=dataNames,  mode='join',
            groups=groups, identifiers=identifiers)

        # do stats
        stats = groups_data.countHistogram(
            name=name, test=test, reference=reference, 
            groups=dataNames, identifiers=groups,
            out=out, outNames=outNames, format_=print_format, title=title)

        # adjust group and identifiers
        loc_groups = dataNames
        loc_identifiers = groups

    elif isinstance(data, Groups):

        # check
        if not data.isTransposable():
            raise ValueError(
                "Argument data has to be transposable, that is each group "
                + "has to contain the same experiment identifiers.")

        # do stats
        stats = data.countHistogram(
            name=name, groups=None, identifiers=groups, test=test, 
            reference=reference, out=out, outNames=outNames, 
            format_=print_format, title=title)

    else:
        raise ValueError("Argument data has to be a Groups instance or a list"
                         + " of Groups instances.")

    # plot
    if plot_:

        # prepare for plotting
        plt.figure()

        # plot
        plot_stats(
            stats=stats, name=plot_name, yerr=None, groups=loc_groups, 
            identifiers=loc_identifiers, label=label, confidence=confidence)

        # finish plotting
        plt.title(title)
        if y_label is None:
            y_label = name
        plt.ylabel(y_label)
        if x_label is not None:
            plt.xlabel(x_label)
        if legend:
            plt.legend()
        plt.show()

    return stats

def correlation(
    xData, xName, yName, yData=None, test=None, regress=True, 
    reference=reference, groups=None, identifiers=None, join=None, 
    out=sys.stdout, format_=print_format, title='', x_label=None, y_label=None):
    """
    Correlates two properties and plots them as a 2d scatter graph.

    In case arg join is None a value is printed and a bar is plotted for each 
    experiment. This value is either the value of the specified property if 
    scalar, or a mean of the property values if indexed.

    If arg join is 'join', the values of the specified property are pooled 
    accross all experiments belonging to one group, and the mean is 
    printed and plotted. 

    If arg join is 'mean', the mean of experiment means for each group 
    (indexed properties only) is printed and plotted. 

    Arguments:
      - xData, yData: (Groups or Observations) structures containing data
      - xName, yName: names of the correlated properties
      - test: correlation test type
      - regress: flag indicating if regression (best fit) line is calculated
      - reference: 
      - groups: list of group names
      - identifiers: list of identifiers
      - join: None to correlate data from each experiment separately, or 'join'
      to join experiments belonging to the same group  
      - out: output stream for printing data and results
      - title: title
      - x_label, y_label: x and y axis labels, if not specified args xName 
      and yName are used instead 
    """

    # combine data if needed
    if yData is not None:
        data = deepcopy(xData)
        data.addData(source=yData, names=[yName])
    else:
        data = xData

    # set regression paramets
    if regress:
        fit = ['aRegress', 'bRegress']
    else:
        fit = None

    # start plotting
    if plot_:
        fig = plt.figure()

    if isinstance(data, Groups):
        
        # do correlation and print
        corr = data.doCorrelation(
            xName=xName, yName=yName, test=test, regress=regress, 
            reference=reference, mode=join, groups=groups,
            identifiers=identifiers, out=out, format_=format_, 
            title=title)

        # plot
        if plot_:
            plot_2d(x_data=corr, x_name='xData', y_name='yData', groups=None,
                    identifiers=groups, graph_type='scatter', fit=fit)

    elif isinstance(data, Observations):

        # do correlation and print
        corr = data.doCorrelation(
            xName=xName, yName=yName, test=test,  regress=regress, 
            reference=reference, mode=join, out=out, 
            identifiers=identifiers, format_=format_, title=title)

        # plot
        if plot_:
            plot_2d(x_data=corr, x_name='xData', y_name='yData', 
                    identifiers=identifiers, graph_type='scatter', fit=fit)

    else:
        raise ValueError("Argument data has to be an instance of " 
                         + "pyto.analysis.Groups or Observations.")

    # finish plotting
    if plot_:
        plt.title(title)
        if x_label is None:
            x_label = xName
        plt.xlabel(x_label)
        if y_label is None:
            y_label = yName
        plt.ylabel(y_label)
        if legend:
            plt.legend()
        plt.show()

    return corr

##############################################################
#
# Plot functions 
#

def plot_layers(
    data, yName='occupancy', xName='distance_nm', yerr=None, groups=None, 
    identifiers=None, mode='all', ddof=1, graphType='line', 
    x_label='Distance to the AZ [nm]', y_label='Vesicle occupancy', title=''):
    """
    Plots values of an indexed property specified by arg yName vs. another
    indexed property specified by arg xName as a line plot. Makes separate
    plots for each group of the arg groups.

    Plots sv occupancy by layer for if Layers object is given as arg data and 
    the default values of args xName and yName are used.

    If mode is 'all' or 'all&mean' data from all observations (experiments) of
    one group is plotted on one figure. If mode is 'all&mean' the group mean is 
    also plotted. If mode is 'mean' all group means are plotted together.

    Arguments:
      - data: (Groups or Observations) data structure
      - xName, yName: name of the plotted properties
      - yerr: property used for y-error
      - groups: list of group names
      - identifiers: list of identifiers
      - mode: 'all', 'mean' or 'all&mean'
      - ddof = difference degrees of freedom used for std
      - graphType: 'line' for line-graph or 'scatter' for a scatter-graph
      - x_label, y_label: labels for x and y axes
      - title: title (used only if mode is 'mean')
    """

    # plot ot not
    if not plot_:
        return

    # if data is Groups, print a separate figure for each group
    if isinstance(data, Groups):
        if groups is None:
            groups = data.keys()

        if (mode == 'all') or (mode == 'all&mean'): 

            # a separate figure for each group
            for group_name in groups:
                plot_layers_one(
                    data=data[group_name], yName=yName, xName=xName, yerr=yerr,
                    identifiers=identifiers, mode=mode, graphType=graphType,
                    x_label=x_label, y_label=y_label)
                title = category_label.get(group_name, group_name)
                plt.title(title)

        elif mode == 'mean':

            # calculate means, add distance_nm and plot (one graph)
            stats = data.joinAndStats(
                name=yName, mode='byIndex', groups=groups, 
                identifiers=identifiers, ddof=ddof, out=None, title=title)
            for group_name in groups:
                dist = data[group_name].getValue(
                    property=xName, identifier=data[group_name].identifiers[0])
                stats.setValue(property=xName, value=dist, 
                               identifier=group_name)
            plot_layers_one(
                data=stats, yName='mean', xName=xName, yerr=yerr, 
                identifiers=None, mode=mode, graphType=graphType, ddof=ddof,
                x_label=x_label, y_label=y_label)

    elif isinstance(data, Observations):

        # Observations: plot one graph
        plot_layers_one(
            data=data, yName=yName, xName=xName, yerr=yerr, 
            identifiers=identifiers, mode=mode, graphType=graphType, ddof=ddof,
            x_label=x_label, y_label=y_label)

    else:
        raise ValueError("Argument 'data' has to be either pyto.analysis.Groups"
                         + " or Observations.") 

def plot_layers_one(
    data, yName='occupancy', xName='distance_nm', yerr=None, identifiers=None, 
    mode='all', ddof=1, graphType='line', x_label='Distance to the AZ', 
    y_label='Vesicle occupancy', title=''):
    """
    Plots values of an indexed property specified by arg yName vs. another
    indexed property specified by arg xName as a line plot. 
    
    Only one group can be specified as arg data. Data for all observations 
    (experiments) of that group are plotted on one graph. 

    Arguments:
      - data: (Observations) data structure
      - xName, yName: name of the plotted properties
      - yerr: property used for y-error
      - groups: list of group names
      - identifiers: list of identifiers
      - mode: 'all', 'mean' or 'all&mean'
      - ddof = difference degrees of freedom used for std
      - graphType: 'line' for line-graph or 'scatter' for a scatter-graph
      - x_label, y_label: labels for x and y axes
      - title: title
    """
    # from here on plotting an Observations object
    fig = plt.figure()

    # set identifiers
    if identifiers is None:
        identifiers = data.identifiers
    identifiers = [ident for ident in identifiers if ident in data.identifiers]

    # plot data for each experiment
    for ident in identifiers:

        # plot data for the current experiment 
        line = plot_2d(x_data=data, x_name=xName, y_name=yName, yerr=yerr, 
                       identifiers=[ident], graph_type=graphType)

    # calculate and plot mean
    if mode == 'all&mean':
        exp = data.doStatsByIndex(
            name=yName, identifiers=identifiers, identifier='mean', ddof=ddof)
        if len(identifiers) > 0:
            #exp_dist = data.getExperiment(identifier=identifiers[0])

            # set x axis values
            x_values = data.getValue(identifier=identifiers[0], name=xName)
            if len(x_values) > len(exp.mean):
                x_values = x_values[:len(exp.mean)]
            exp.__setattr__(xName, x_values) 
            exp.properties.add(xName)
            exp.indexed.add(xName)

            # plot
            line = plot_2d(
                x_data=exp, x_name=xName, y_data=exp, y_name='mean', 
                yerr=yerr, graph_type=graphType, line_width_='thick')

    # finish plotting
    plt.title(title)
    plt.ylabel(y_label)
    plt.xlabel(x_label)
    ends = plt.axis()
    plt.axis([0, 250, 0, 0.3])
    if legend:
        plt.legend()
    plt.show()

def plot_histogram(data, name, bins, groups=None, identifiers=None, 
                   facecolor=None, edgecolor=None, x_label=None, title=None):
    """
    Plots data as a histogram.

    If more than one group is given (arg groups), data from all groups are 
    combined. Also data from all experiments are combined.

    Arguments:
      - data: (Groups or Observations) data
      - name: property name
      - bins: histogram bins
      - groups: list of group names, None for all groups
      - identifiers: experiment identifier names, None for all identifiers 
      - facecolor: histogram facecolor
      - edgecolor: histogram edgecolor
      - x_label: x axis label
      - title: title
    """

    # combine data
    if isinstance(data, Groups):
        obs = data.joinExperiments(name=name, mode='join', groups=groups,
                                   identifiers=identifiers)
    elif isinstance(data, Observations):
        obs = data
    exp = obs.joinExperiments(name=name, mode='join')
    combined_data = getattr(exp, name)

    # color
    if facecolor is None:
        if (groups is not None): 
            if len(groups)==1:
                facecolor = color.get(groups[0], None)
        else:
            if isinstance(groups, str):
                facecolor = color.get(groups, None)

    # plot
    plt.hist(combined_data, bins=bins, facecolor=facecolor, edgecolor=edgecolor)

    # finish plot
    if title is not None:
         plt.title(title)
    if x_label is None:
        x_label = name
    plt.xlabel(x_label)
    plt.show()

def plot_stats(stats, name, groups=None, identifiers=None, yerr='sem', 
               confidence='stars', stats_between=None, label=None):
    """
    Does main part of plotting property (arg) name of (arg) stats, in the
    form of a bar chart. 

    If specified, args groups and identifiers specify the order of groups
    and experiments on the x axis. 

    Plots on the current figure.     

    Arguments:
      - stats: (Groups, or Observations) object
      containing data
      - name: property name
      - groups: list of group names, None for all groups
      - identifiers: experiment identifier names, None for all identifiers 
      - stats_between: (Groups) Needs to contain confidence between 
      (experiments of) different groups having the same identifiers  
      - label: determines which color, alpha, ... is used, can be 'group' to 
      label by group or 'experiment' to label by experiment
    """

    # stats type
    if isinstance(stats, Groups):
        stats_type = 'groups'
    elif isinstance(stats, Observations):
        stats_type = 'observations'
        stats_obs = stats
        stats = Groups()
        stats[''] = stats_obs
    else:
        raise ValueError(
            "Argument stats has to be an instance of Groups or Observations.")

    # find rough range of y-axis values (to plot cinfidence)
    y_values = [group.getValue(identifier=ident, property=name)
                for group in stats.values()
                for ident in group.identifiers]
    if (y_values is not None) and (len(y_values) > 0):
        rough_y_min = min(y_values)
        rough_y_max = max(y_values)
    else:
        rough_y_min = 0
        rough_y_max = 1
    rough_y_range = rough_y_max - min(rough_y_min, 0)

    # set bar width if needed
    if bar_arrange == 'uniform':
        bar_width = 0.2
        left = -2 * bar_width
    elif bar_arrange == 'grouped':
        max_identifs = max(len(group.identifiers) for group in stats.values())
        bar_width = numpy.floor(80 / max_identifs) / 100
    else:
        raise ValueError("bar_arrange has to be 'uniform' or 'grouped'.")

    # set group order
    if groups is None:
        group_names = stats.keys() 
    else:
        group_names = groups

    # loop over groups
    y_min = 0
    y_max = 0
    group_left = []
    label_done = False
    for group_nam, group_ind in zip(group_names, range(len(group_names))):
        group = stats[group_nam]

        # set experiment order
        if identifiers is None:
            loc_identifs = group.identifiers
        elif isinstance(identifiers, list):
            loc_identifs = [ident for ident in identifiers 
                            if ident in group.identifiers]
        elif isinstance(identifiers, dict):
            loc_identifs = identifiers[group_nam]

        # move bar position
        if bar_arrange == 'uniform':
            left += bar_width
            group_left.append(left + bar_width)

        # loop over experiments
        for ident, exp_ind in zip(loc_identifs, range(len(loc_identifs))):

            # label
            if label is None:
                if stats_type == 'groups':
                    label_code = group_nam
                elif stats_type == 'observations':
                    label_code = ident
            elif label == 'group':
                label_code = group_nam
            elif label == 'experiment':
                label_code = ident

            # adjust alpha 
            loc_alpha = alpha.get(label_code, 1)

            # y values and y error
            value = group.getValue(identifier=ident, property=name)
            if ((yerr is not None) and (yerr in group.properties) 
                and (loc_alpha == 1)):
                yerr_num = group.getValue(identifier=ident, property=yerr)
                yerr_one = yerr_num
                y_max = max(y_max, value+yerr_num)
                if one_side_yerr:
                    yerr_num = ([0], [yerr_num])
            else:
                yerr_num = None
                yerr_one = 0
                y_max = max(y_max, value)
            y_min = min(y_min, value)

            # plot
            if bar_arrange == 'uniform':
                left += bar_width
            elif bar_arrange == 'grouped':
                left = group_ind + exp_ind * bar_width
            if label_done:
                bar = plt.bar(
                    left=left, height=value, yerr=yerr_num, width=bar_width, 
                    color=color[label_code], ecolor=color[label_code],
                    alpha=loc_alpha)[0]
            else:
                bar = plt.bar(
                    left=left, height=value, yerr=yerr_num, width=bar_width, 
                    label=category_label.get(label_code, ''), 
                    color=color[label_code], ecolor=color[label_code],
                    alpha=loc_alpha)[0]

            #
            plt.errorbar(left+bar_width/2, value,yerr=yerr_num,
                         ecolor=ecolor.get(label_code, 'k'), label='_nolegend_')
            
            # confidence within group
            if (confidence is not None) and ('confidence' in group.properties):

                # get confidence
                confid_num = group.getValue(identifier=ident, 
                                            property='confidence')
                # workaround for problem in Observations.getValue()
                if (isinstance(confid_num, (list, numpy.ndarray)) 
                    and len(confid_num) == 1):
                    confid_num = confid_num[0]
                if confidence == 'number':
                    confid = confidence_plot_format % confid_num
                    conf_size = confidence_plot_font_size
                elif confidence == 'stars':
                    confid = '*' * get_confidence_stars(
                        confid_num, limits=confidence_stars)
                    conf_size = 1.5 * confidence_plot_font_size

                # plot confidence
                x_confid = bar.get_x() + bar.get_width()/2.
                y_confid = 0.02 * rough_y_range + bar.get_height() + yerr_one
                ref_ident = group.getValue(identifier=ident,   
                                           property='reference')
                ref_color = color.get(ref_ident, label_code) 
                plt.text(x_confid, y_confid, confid, ha='center', va='bottom',
                         size=conf_size, color=ref_color)

            # confidence between groups
            if ((stats_type == 'groups') and (confidence is not None) 
                and (stats_between is not None) 
                and ('confidence' in stats_between[group_nam].properties)):
                other_group = stats_between[group_nam]

                # check
                other_ref = other_group.getValue(identifier=ident, 
                                                 property='reference')
                if other_ref != ident:
                    logging.warning(
                        "Confidence between groups calculated between " \
                            + "experiments with different identifiers: " \
                            + ident + " and " + other_ref + ".")

                # get confidence
                confid_num = other_group.getValue(identifier=ident, 
                                                  property='confidence')
                if confidence == 'number':
                    confid = confidence_plot_format % confid_num
                    conf_size = confidence_plot_font_size
                elif confidence == 'stars':
                    confid = '*' * get_confidence_stars(
                        confid_num, limits=confidence_stars)
                    conf_size = 1.5 * confidence_plot_font_size

                # plot
                x_confid = bar.get_x() + bar.get_width()/2.
                y_confid = 0.04 * rough_y_range + bar.get_height() + yerr_one
                ref_color = color[ident]
                plt.text(x_confid, y_confid, confid, ha='center', va='bottom',
                         size=conf_size, color=ref_color)

        # set flag that prevents adding further labels to legend
        label_done = True

    # adjust axes
    axis_limits = list(plt.axis())
    plt.axis([axis_limits[0]-bar_width, max(axis_limits[1], 4), 
              y_min, 1.1*y_max])
    if bar_arrange == 'uniform':
        group_left.append(left)
        x_tick_pos = [
            group_left[ind] + 
            (group_left[ind+1] - group_left[ind] - bar_width) / 2. 
            for ind in range(len(group_left) - 1)]
    elif bar_arrange == 'grouped':
        x_tick_pos = numpy.arange(len(group_names)) + bar_width*(exp_ind+1)/2.
    group_labels = [category_label.get(g_name, g_name) 
                    for g_name in group_names]
    plt.xticks(x_tick_pos, group_labels)

def plot_2d(x_data, x_name='x_data', y_data=None, y_name='y_data', yerr=None,
            groups=None, identifiers=None, graph_type='scatter', 
            line_width_=None, fit=None):
    """
    Min part for plottings a 2d graph.

    If specified, args groups and identifiers specify the order of groups
    and experiments on the x axis. 

    Plots on the current figure.     

    Arguments:
      - x_data, y_data: data objects, have to be instances of Groups, 
      Observations or Experiment and they both have to be instances of the 
      same class
      - x_name, y_name: names of properties of x_data and y_data that are 
      plotted on x and y axis  
    """

    # y data
    if y_data is None:
        y_data = x_data

    # determine data type and set group order
    if (isinstance(x_data, Groups) and isinstance(y_data, Groups)):
        data_type = 'groups'
        if groups is None:
            group_names = x_data.keys() 
        else:
            group_names = groups
    elif (isinstance(x_data, Observations) 
          and isinstance(y_data, Observations)):
        data_type = 'observations'
        group_names = ['']
    elif (isinstance(x_data, pyto.analysis.Experiment)
          and isinstance(y_data, pyto.analysis.Experiment)):
        data_type = 'experiment'
        group_names = ['']
    else:
        raise ValueError(
            "Arguments x_data and y_data have to be instances of Groups, "
            + "Observations or Experiment and they need to be instances "
            + "of the same class.")

    # line style and width
    if graph_type == 'scatter':
        loc_line_style = ''
        loc_marker = marker
    elif graph_type == 'line':
        loc_line_style = default_line_style
        loc_marker = ''
    if line_width_ is None:
        loc_line_width = default_line_width
    elif line_width_ == 'thick':
        loc_line_width = thick_line_width

    # loop over groups
    figure = None
    markers_default_copy = copy(markers_default)
    for group_nam, group_ind in zip(group_names, range(len(group_names))):

        # get data
        if data_type == 'groups':
            x_group = x_data[group_nam]
            y_group = y_data[group_nam]
        elif data_type == 'observations':
            x_group = x_data
            y_group = y_data
        elif data_type == 'experiment':
            x_group = Observations()
            x_group.addExperiment(experiment=x_data)
            y_group = Observations()
            y_group.addExperiment(experiment=y_data)

        # set experiment order
        if identifiers is None:
            loc_identifs = x_group.identifiers
        elif isinstance(identifiers, list):
            loc_identifs = [ident for ident in identifiers 
                            if ident in x_group.identifiers]
        elif isinstance(identifiers, dict):
            loc_identifs = identifiers[group_nam]

        # loop over experiments
        for ident, exp_ind in zip(loc_identifs, range(len(loc_identifs))):

            # values
            if (data_type == 'groups') or (data_type == 'observations'):
                x_value = x_group.getValue(identifier=ident, property=x_name)
                y_value = y_group.getValue(identifier=ident, property=y_name)
            elif data_type == 'experiment':
                x_ident = x_data.identifier
                x_value = x_group.getValue(identifier=x_ident, property=x_name)
                y_ident = y_data.identifier
                y_value = y_group.getValue(identifier=y_ident, property=y_name)

            # cut data to min length
            if len(x_value) != len(y_value):
                min_len = min(x_value, y_value)
                x_value = x_value[:min_len]
                x_value = y_value[:min_len]

            # adjust colors
            loc_alpha = alpha.get(ident, 1)
            if graph_type == 'scatter':
                loc_marker = marker.get(ident, None)
                if loc_marker is None:
                    loc_marker = markers_default_copy.pop(0)
            loc_color = color.get(ident, None)

            # plot data points
            label = (group_nam + ' ' + ident).strip()
            if loc_color is not None:
                figure = plt.plot(
                    x_value, y_value, linestyle=loc_line_style, color=loc_color,
                    linewidth=loc_line_width, marker=loc_marker, 
                    markersize=marker_size, alpha=loc_alpha, label=ident)
            else:
                figure = plt.plot(
                    x_value, y_value, linestyle=loc_line_style,
                    linewidth=loc_line_width, marker=loc_marker, 
                    markersize=marker_size, alpha=loc_alpha, label=ident)

            # plot eror bars
            if yerr is not None:
                yerr_value = y_group.getValue(identifier=ident, property=yerr)
                # arg color needed otherwise makes line with another color
                plt.errorbar(
                    x_value, y_value, yerr=yerr_value, 
                    color=loc_color, ecolor=loc_color, label='_nolegend_')

            # plot fit line
#            if fit is not None:
            if fit is not None:

                # data limits
                x_max = x_value.max()
                x_min = x_value.min()
                y_max = y_value.max()
                y_min = y_value.min()

                # fit line parameters
                a_reg = x_group.getValue(identifier=ident, property=fit[0])
                b_reg = y_group.getValue(identifier=ident, property=fit[1])

                # fit limits
                x_range = numpy.arange(x_min, x_max, (x_max - x_min) / 100.)
                poly = numpy.poly1d([a_reg, b_reg])
                y_range = numpy.polyval(poly, x_range)
                start = False
                x_fit = []
                y_fit = []
                for x, y in zip(x_range, y_range):
                    if (y >= y_min) and (y <= y_max):
                        x_fit.append(x)
                        y_fit.append(y)
                        start = True
                    else:
                        if start:
                            break
                # plot fit
                if loc_color is not None:
                    plt.plot(
                        x_fit, y_fit, linestyle=default_line_style, 
                        color=loc_color, linewidth=loc_line_width, marker='', 
                        alpha=loc_alpha)
                else:
                    plt.plot(
                        x_fit, y_fit, linestyle=default_line_style,
                        linewidth=loc_line_width, marker='', alpha=loc_alpha)

    return figure

def get_confidence_stars(value, limits):
    """
    Returns number of stars for a given confidence level(s).
    """

    # more than one value
    if isinstance(value, (numpy.ndarray, list)):
        result = [get_confidence_stars(x, limits) for x in value]
        return result

    # one value
    result = 0
    for lim in limits:
        if value <= lim:
            result += 1
        else:
            break

    return result

##############################################################
#
# Functions that calculate certain properites 
#

def getSpecialThreshold(cleft, segments, fraction, 
                       groups=None, identifiers=None):
    """
    Return threshold closest to the 

    Arguments:
      - cleft: (Groups)
    """

    # get groups
    if groups is None:
        groups = cleft.keys()

    # loop over groups
    fract_thresholds = {}
    fract_densities = {}
    for categ in groups:

        # loop over experiments (identifiers)
        categ_identifiers = cleft[categ].identifiers
        for identif in categ_identifiers:
 
            # skip identifiers that were not passed
            if identifiers is not None:
                if identif not in identifiers:
                    continue
 
            # get boundary and cleft ids
            bound_ids = cleft[categ].getValue(identifier=identif, 
                                             property='boundIds')
            cleft_ids = cleft[categ].getValue(identifier=identif, 
                                             property='cleftIds')

            # get mean boundary and cleft and fractional densities
            bound_densities = cleft[categ].getValue(
                identifier=identif, property='mean', ids=bound_ids)
            bound_volume = cleft[categ].getValue(
                identifier=identif, property='volume', ids=bound_ids)
            bound_density = numpy.dot(bound_densities, 
                                      bound_volume) / bound_volume.sum() 
            cleft_densities = cleft[categ].getValue(
                identifier=identif, property='mean', ids=cleft_ids)
            cleft_volume = cleft[categ].getValue(
                identifier=identif, property='volume', ids=cleft_ids)
            cleft_density = numpy.dot(cleft_densities, 
                                      cleft_volume) / cleft_volume.sum() 
            fract_density = bound_density + (cleft_density 
                                             - bound_density) * fraction
            
            # get closest threshold
            # ERROR thresholds badly formated in segments
            all_thresh = segments[categ].getValue(identifier=identif, 
                                                  property='thresh')
            index = numpy.abs(all_thresh - fract_density).argmin()
            thresh = all_thresh[index]
            thresh_str = "%6.3f" % thresh
            try:
                fract_thresholds[categ][identif] = thresh_str
                fract_densities[categ][identif] = (bound_density, 
                                                   cleft_density, fract_density)
            except KeyError:
                fract_thresholds[categ] = {}
                fract_thresholds[categ][identif] = thresh_str
                fract_densities[categ] = {}
                fract_densities[categ][identif] = (bound_density, 
                                                   cleft_density, fract_density)

    return fract_densities

def get_occupancy(segments, layers, groups, name):
    """
    Occupancy is added to the segments object

    Arguments:
      - segments: (connections)
      - layers: (CleftRegions)
      - groups
      - name: name of the added (occupancy) property
    """

    for categ in groups:
        for ident in segments[categ].identifiers:

            seg_vol = segments[categ].getValue(identifier=ident, 
                                               property='volume').sum()
            total_vol = layers[categ].getValue(identifier=ident, 
                                               property='volume')
            cleft_ids = layers[categ].getValue(identifier=ident, 
                                               property='cleftIds')
            cleft_vol = total_vol[cleft_ids-1].sum()
            occup = seg_vol / float(cleft_vol)
            segments[categ].setValue(identifier=ident, property=name, 
                                     value=occup)

def get_cleft_layer_differences(data, name, groups):
    """
    """

    def abs_diff43(x):
        return x[3] - x[2]
    def abs_diff65(x):
        return x[5] - x[4]

    # not good because apply mane the new property indexed
    #data.apply(funct=abs_diff43, args=[name], 
    #           name='diffNormalMean43', categories=groups)
    #data.apply(funct=abs_diff65, args=[name], 
    #           name='diffNormalMean65', categories=groups)

    for categ in groups:
        for ident in data[categ].identifiers:

            # 4 - 3
            val4 = data[categ].getValue(
                identifier=ident, property=name, ids=[4])[0]
            val3 = data[categ].getValue(
                identifier=ident, property=name, ids=[3])[0]
            diff43 = val4 - val3
            data[categ].setValue(
                identifier=ident, property='diffNormalMean43', value=diff43)

            # 6 - 5
            val6 = data[categ].getValue(
                identifier=ident, property=name, ids=[6])[0]
            val5 = data[categ].getValue(
                identifier=ident, property=name, ids=[5])[0]
            diff65 = val6 - val5
            data[categ].setValue(
                identifier=ident, property='diffNormalMean65', value=diff65)

def calculateVesicleProperties(data, layer=None, tether=None, categories=None):
    """
    Calculates additional vesicle related properties. 

    The properties calculated are:
      - 'n_vesicle'
      - 'az_surface_um' 
      - 'vesicle_per_area_um'
      - 'mean_tether_nm' (for non-tethered vesicles value set to numpy.nan) 
    """

    # calculate n vesicles per synapse
    data.getNVesicles(name='n_vesicle', categories=categories)

    # calculate az surface (defined as layer 1) in um
    if layer is not None:
        data.getNVesicles(
            layer=layer, name='az_surface_um', fixed=1, inverse=True,
            layer_name='surface_nm', layer_factor=1.e-6, categories=categories)

    # calculate N vesicles per unit az surface (defined as layer 1) in um
    if layer is not None:
        data.getNVesicles(
            layer=layer, name='vesicle_per_area_um', 
            layer_name='surface_nm', layer_factor=1.e-6, categories=categories)

    # calculate mean tether length for each sv
    if tether is not None:
        data.getMeanConnectionLength(conn=tether, name='mean_tether_nm', 
                                     categories=categories, value=numpy.nan)

def calculateTetherProperties(data, layer=None, categories=None):
    """
    Calculates additional vesicle related properties. 

    The properties calculated are:
      - 'n_tether'
      - 'tether_per_area_um'
    """

    # calculate n tethers per synapse (to be moved up before pickles are made)
    data.getN(name='n_tether', categories=categories)

    # calculate N tethers per unit az surface (defined as layer 1) in um
    if layer is not None:
        data.getN(
            layer=layer, name='tether_per_area_um', 
            layer_name='surface_nm', layer_factor=1.e-6, categories=categories)

def calculateConnectivityDistanceRatio(
        vesicles, initial, distances, name='n_tethered_ratio', categories=None):
    """
    """

    # calculate connectivity distances
    vesicles.getConnectivityDistance(
        initial=initial, name='conn_distance', distance=1,
        categories=categories)

    # shortcuts
    d0 = [distances[0], distances[0]]
    d1 = [distances[1], distances[1]]

    # find n vesicles at specified distances
    conndist_0_sv = vesicles.split(
        value=d0, name='conn_distance', categories=categories)[0]
    conndist_0_sv.getNVesicles(name='_n_conndist_0', categories=categories)
    vesicles.addData(
        source=conndist_0_sv, names={'_n_conndist_0':'_n_conndist_0'})
    conndist_1_sv = vesicles.split(
        value=d1, name='conn_distance', categories=categories)[0]
    conndist_1_sv.getNVesicles(name='_n_conndist_1', categories=categories)
    vesicles.addData(
        source=conndist_1_sv, names={'_n_conndist_1':'_n_conndist_1'})

    # calculate reatio
    vesicles.apply(
        funct=numpy.true_divide, args=['_n_conndist_1', '_n_conndist_0'], 
        name=name, categories=categories, indexed=False)

def str_attach(string, attach):
    """
    Inserts '_' followed by attach in front of the right-most '.' in string and 
    returns the resulting string.

    For example:
      str_attach(string='sv.new.pkl', attach='raw') -> 'sv.new_raw.pkl)
    """

    string_parts = list(string.rpartition('.'))
    string_parts.insert(-2, '_' + attach)
    res = ''.join(string_parts)

    return res


################################################################
#
# Main function (edit to add additional analysis files and plot (calculate)
# other properties)
#
###############################################################

def main(individual=False, save=False, analyze=False):
    """
    Arguments:
      - individual: if True read data for each tomo separately, otherwise 
      read from pickles containing partailly analyzed data
      - save: if True save pickles containing partailly analyzed data
      - analyze: do complete analysis
    """

    # make catalog and groups
    global catalog
    if __name__ == '__main__':
        try:
            curr_dir, base = os.path.split(os.path.abspath(__file__))
        except NameError:
            # needed for running from ipython
            curr_dir = os.getcwd()
    else:
        curr_dir = os.getcwd()
    cat_dir = os.path.normpath(os.path.join(curr_dir, catalog_directory))
    catalog = pyto.analysis.Catalog(
        catalog=catalog_pattern, dir=cat_dir, identifiers=identifiers)
    catalog.makeGroups(feature='treatment')
                                   
    # prepare for making or reading data pickles
    global sv, tether, conn, layer, clust
                                   
    ##########################################################
    #
    # Read individual tomo data, calculate few things and save this 
    # preprocessed data, or just read the preprocessed data 
    #

    if individual:

        # read sv data 
        sv_files = getattr(catalog, sv_name)
        sv_membrane_files = getattr(catalog, sv_membrane_name)
        sv_lumen_files = getattr(catalog, sv_lumen_name)
        logging.info("Reading sv")
        sv = pyto.analysis.Vesicles.read(
            files=sv_files, catalog=catalog, categories=categories, 
            membrane=sv_membrane_files, lumen=sv_lumen_files)

        # read tether data 
        tether_files = getattr(catalog, tethers_name)
        logging.info("Reading tethers")
        tether = pyto.analysis.Connections.read(
            files=tether_files, mode='connectors', catalog=catalog,
            categories=categories, order=sv)
                                   
        # read connector data 
        conn_files = getattr(catalog, connectors_name)
        logging.info("Reading connectors")
        conn = pyto.analysis.Connections.read(
            files=conn_files, mode='connectors', catalog=catalog,
            categories=categories, order=sv)

        # read layer data 
        layer_files = getattr(catalog, layers_name)
        logging.info("Reading layers")
        layer = pyto.analysis.Layers.read(files=layer_files, catalog=catalog,
                                          categories=categories, order=sv)

        # read cluster data 
        cluster_files = getattr(catalog, clusters_name)
        logging.info("Reading clusters")
        clust = pyto.analysis.Clusters.read(
            files=cluster_files, mode='connectivity', catalog=catalog,
            categories=categories, order=sv)
        hi_clust_bound = pyto.analysis.Clusters.read(
            files=cluster_files, mode='hierarchicalBoundaries', catalog=catalog,
            categories=categories, order=sv)
        hi_clust_conn = pyto.analysis.Clusters.read(
            files=cluster_files, mode='hierarchicalConnections', 
            catalog=catalog, categories=categories, order=sv)

        # pickle raw?

        # separate svs by size
        [small_sv, sv, big_sv] = sv.splitByRadius(radius=vesicle_radius_bins)

        # remove bad svs from tethers and connections
        tether.removeBoundaries(boundary=small_sv)
        tether.removeBoundaries(boundary=big_sv)
        conn.removeBoundaries(boundary=small_sv)
        conn.removeBoundaries(boundary=big_sv)

        # calculate number of tethers, connections and linked svs for each sv
        sv.getNTethers(tether=tether)
        sv.getNConnections(conn=conn)
        sv.addLinked(files=conn_files)
        sv.getNLinked()
        sv.getClusterSize(clusters=clust)

        # calculate number of items and max cluster fraction
        clust.findNItems()
        clust.findBoundFract()
        clust.findRedundancy()

        # pickle
        if save:
            pickle.dump(sv, open(sv_pkl, 'wb'), -1)
            pickle.dump(tether, open(tethers_pkl, 'wb'), -1)
            pickle.dump(conn, open(connectors_pkl, 'wb'), -1)
            pickle.dump(layer, open(layers_pkl, 'wb'), -1)
            pickle.dump(clust, open(clusters_pkl, 'wb'), -1)

    else:

        # unpickle
        sv = pickle.load(open(sv_pkl))
        tether = pickle.load(open(tethers_pkl))
        conn = pickle.load(open(connectors_pkl))
        layer = pickle.load(open(layers_pkl))
        clust = pickle.load(open(clusters_pkl))

        # keep only specified groups and identifiers
        for obj in [sv, tether, conn, layer, clust]:
            obj.keep(groups=categories, identifiers=identifiers, 
                     removeGroups=True)

    ##########################################################
    #
    # Separate data in various categories
    #

    # split svs by distance
    global bulk_sv, sv_bins, near_sv, inter_sv, dist_sv
    bulk_sv = sv.splitByDistance(distance=distance_bins[-1])
    sv_bins = sv.splitByDistance(distance=distance_bins)
    near_sv = sv_bins[0]
    inter_sv = sv_bins[1]
    dist_sv = sv.splitByDistance(distance=[distance_bins[2], 
                                           distance_bins[-1]])[0]

    # split layers by distance
    global layer_bin
    layer_bin = layer.rebin(bins=distance_bins, pixel=catalog.pixel_size)

    # extract svs that are near az, tethered, near+tethered, near-tethered 
    global teth_sv, non_teth_sv, near_teth_sv, near_non_teth_sv
    teth_sv, non_teth_sv = bulk_sv.extractTethered(other=True)
    near_teth_sv, near_non_teth_sv = near_sv.extractTethered(other=True)

    # extract connected and non-connected svs 
    global conn_sv, non_conn_sv, bulk_conn_sv, bulk_non_conn_sv
    global near_conn_sv, near_non_conn_sv, inter_conn_sv, inter_non_conn_sv
    conn_sv, non_conn_sv = sv.extractConnected(other=True)
    bulk_conn_sv, bulk_non_conn_sv = bulk_sv.extractConnected(other=True)
    near_conn_sv, near_non_conn_sv = near_sv.extractConnected(other=True)
    inter_conn_sv, inter_non_conn_sv = sv_bins[1].extractConnected(other=True)

    # extract by tethering and connectivity
    global near_teth_conn_sv, near_teth_non_conn_sv
    near_teth_conn_sv, near_teth_non_conn_sv = \
        near_teth_sv.extractConnected(other=True)    
    global near_non_teth_conn_sv, near_non_teth_non_conn_sv
    near_non_teth_conn_sv, near_non_teth_non_conn_sv = \
        near_non_teth_sv.extractConnected(other=True)    

    # calculate additional properties for different vesicle objects
    for xxx_sv in [near_sv, near_teth_sv, near_non_teth_sv, near_teth_conn_sv, 
                   near_non_teth_conn_sv, near_teth_non_conn_sv, 
                   near_non_teth_non_conn_sv,
                   teth_sv, non_teth_sv]:
        calculateVesicleProperties(data=xxx_sv, layer=layer, tether=tether,
                                   categories=categories)

    # calculate additional properties for different tether objects
    calculateTetherProperties(data=tether, layer=layer, categories=categories)

    # split near_sv and tether according to rrp (defined as >2 tethered)
    global sv_non_rrp, sv_rrp, tether_rrp, tether_non_rrp
    sv_non_rrp, sv_rrp = near_sv.split(
        name='n_tether', value=rrp_ntether_bins, categories=categories)
    tether_rrp = tether.extractByVesicles(
        vesicles=sv_rrp, categories=categories, other=False)
    tether_non_rrp = tether.extractByVesicles(
        vesicles=sv_non_rrp, categories=categories, other=False)
    calculateVesicleProperties(
        data=sv_rrp, layer=layer, tether=tether_rrp, categories=categories)
    calculateVesicleProperties(
        data=sv_non_rrp, layer=layer, tether=tether_non_rrp, 
        categories=categories)
    calculateTetherProperties(
        data=tether_rrp, layer=layer, categories=categories)
    calculateTetherProperties(
        data=tether_non_rrp, layer=layer, categories=categories)

    # split tethers according to their length
    global short_tether, long_tether
    short_tether, long_tether = tether.split(
        name='length_nm', value=tether_length_bins, categories=categories)
    calculateTetherProperties(
        data=short_tether, layer=layer, categories=categories)
    calculateTetherProperties(
        data=long_tether, layer=layer, categories=categories)

    # calculate n short and long tethers for proximal vesicles
    near_sv.getNConnections(conn=short_tether, name='n_short_tether', 
                            categories=categories)
    near_sv.getNConnections(conn=long_tether, name='n_long_tether', 
                            categories=categories)

    # stop here if no analysis
    if not analyze: return


    ###########################################################
    #
    # SV distribution
    #

    # plot individual vesicle occupancy 
    plot_layers(data=layer, mode='all', groups=categories, 
                identifiers=identifiers)

    # plot individual vesicle occupancy with means
    plot_layers(data=layer, mode='all&mean', 
                groups=categories, identifiers=identifiers)

    # plot individual vesicle occupancy with means
    plot_layers(data=layer, mode='mean', groups=categories, 
                identifiers=identifiers, title="Mean vesicle occupancy")

    # mean occupancy for all vesicles within 250 nm to the AZ
    analyze_occupancy(
        layer=layer, bins=[0, 250], bin_names=["all"], 
        pixel_size=catalog.pixel_size, groups=categories, 
        identifiers=identifiers, test='t', reference=reference, ddof=1, 
        out=sys.stdout, 
        outNames=None, yerr='sem', confidence='stars', 
        title='SV occupancy', y_label='Fraction of volume occupied by svs')

    # mean occupancy in distance bins
    analyze_occupancy(
        layer=layer, bins=distance_bins, bin_names=distance_bin_names, 
        pixel_size=catalog.pixel_size, groups=categories, 
        identifiers=identifiers, test='t', reference=reference, ddof=1, 
        out=sys.stdout, outNames=None, yerr='sem', confidence='stars', 
        title='SV occupancy', y_label='Fraction of volume occupied by svs')

    # min distance to the AZ, fine histogram for proximal svs
    stats(data=near_sv, name='minDistance_nm', bins=fine_length_bins, 
          bin_names=fine_length_bin_names, join='join', groups=categories, 
          identifiers=identifiers, test='chi2', reference=reference,
          x_label='Distance to the AZ [nm]', y_label='N vesicles',
          title='Histogram of min distance to the AZ of proximal svs')

    # Min distance to the AZ for near svs
    stats(data=near_sv, name='minDistance_nm', join='join', groups=categories, 
          identifiers=identifiers, test='t', reference=reference,
          ddof=1, out=sys.stdout, y_label='Mean [nm]',
          title='Min distance of proximal svs to the AZ')

    # min sv distance to the AZ dependence on connectivity
    stats_list(
        data=[near_conn_sv, near_non_conn_sv], 
        dataNames=['connected', 'non_connected'], name='minDistance_nm', 
        join='join', groups=categories, identifiers=identifiers, 
        test='t', reference=reference,  ddof=1, out=sys.stdout,
        title='Min distance of proximal svs to the AZ by connectivity',
        y_label='Mean min distance to the AZ [nm]')

    # min sv distance to the AZ dependence on tethering
    stats_list(
        data=[near_non_teth_sv, near_teth_sv], 
        dataNames=['non_tethered', 'tethered'], name='minDistance_nm', 
        join='join', groups=categories, identifiers=identifiers, 
        test='t', reference=reference,  ddof=1, out=sys.stdout,
        title='Min distance of proximal svs to the AZ by tethering',
        y_label='Mean min distance to the AZ [nm]')

    # ToDo: 
    #   - ratio of occupancies between intermediate and proximal 
    #   - ratio between min and max occupancies for each tomo

    ###########################################################
    # 
    # Analyze sv radii
    #

    # radius of bulk svs
    stats(data=bulk_sv, name='radius_nm', join='join', groups=categories,
          identifiers=identifiers, reference=reference, test='t', 
          y_label='Raduis [nm]', title='Vesicle radius')

    # sv radius dependence on distance to the AZ
    stats_list(
        data=sv_bins, dataNames=distance_bin_names, name='radius_nm',
        join='join', groups=categories, identifiers=identifiers, 
        reference=reference, test='t', y_label='Radius [nm]', 
        title='Vesicle radius dependence on distance to the AZ')

    # sv radius of proximal svs dependence on tethering
    stats_list(
        data=[near_non_teth_sv, near_teth_sv], 
        dataNames=['non_tethered', 'tethered'], 
        name='radius_nm', join='join', groups=categories, 
        identifiers=identifiers, reference=reference, test='t', 
        y_label='Radius [nm]', 
        title='Proximal sv radius dependence on tethering')

    # radius dependence on number of connectors
    stats_list(
        data=bulk_sv.split(value=[0,1,3,100], name='n_connection'),
        dataNames=['0', '1-2', '>2'], name='radius_nm', join='join', 
        groups=categories, identifiers=identifiers, reference=reference, 
        test='t', y_label='Radius [nm]', 
        title='Radius dependence on N connectors')

    # ananlyze dependence on both tethering and connectivity
    stats_list(
        data=[near_teth_conn_sv, near_teth_non_conn_sv, 
              near_non_teth_conn_sv, near_non_teth_non_conn_sv], 
        dataNames=['t c', 't nc', 'nt c', 'nt nc'], name='radius_nm', 
        join='join', groups=categories, identifiers=identifiers, 
        reference=reference, test='t', y_label='Radius [nm]', 
        title='Radius dependence on connectivity and tethering')

    # radius histogram of all groups together
    plot_histogram(
        data=bulk_sv, name='radius_nm', bins=radius_bins, groups=categories, 
        identifiers=identifiers, x_label='Radius [nm]',
        title='Vesicle radius histogram of all groups together')

    # radius histogram of one group
    plot_histogram(
        data=bulk_sv, name='radius_nm', bins=radius_bins, groups='ko_1',
        identifiers=identifiers, x_label='Radius [nm]', 
        title='Vesicle radius histogram of ko_1')


    ###########################################################
    #
    # Vesicle density analysis
    #

    # vesicle lumen density comparison between tethered vs non-tethered, paired
    stats_list_pair(
        data=[non_teth_sv, teth_sv], dataNames=['non_tethered', 'tethered'], 
        name='lumen_density', groups=categories, identifiers=identifiers,
        reference=reference, test='t_rel', label='experiment', 
        y_label='Lumenal density', 
        title='Lumenal density comparison between tethered and non-tethered')

    # vesicle lumen density comparison between proximal tethered vs 
    # non-tethered, paired
    stats_list_pair(
        data=[near_non_teth_sv, near_teth_sv], 
        dataNames=['non_tethered', 'tethered'], 
        name='lumen_density', groups=categories, identifiers=identifiers, 
        reference=reference, test='t_rel', label='experiment', 
        y_label='Lumenal density', 
        title=('Lumenal density comparison between proximal tethered and ' 
               + 'non-tethered'))

    # vesicle membrane density comparison between tethered vs non-tethered, 
    # paired
    stats_list_pair(
        data=[non_teth_sv, teth_sv], dataNames=['non_tethered', 'tethered'], 
        name='membrane_density', groups=categories, identifiers=identifiers, 
        reference=reference, test='t_rel', label='experiment', 
        y_label='Lumenal density', 
        title='Membrane density comparison between tethered and non-tethered')

    # vesicle lumen density comparison between connected vs non-connected, 
    # paired
    stats_list_pair(
        data=[non_conn_sv, conn_sv], dataNames=['non_connected', 'connected'], 
        name='lumen_density', groups=categories, identifiers=identifiers, 
        reference=reference, test='t_rel', label='experiment', 
        y_label='Lumenal density', 
        title='Lumenal density comparison between connected and non-connected')

    # vesicle membrane density comparison between connected vs non-connected, 
    # paired
    stats_list_pair(
        data=[non_teth_sv, teth_sv], dataNames=['non_connected', 'connected'], 
        name='membrane_density', groups=categories, identifiers=identifiers, 
        reference=reference, test='t_rel', label='experiment', 
        y_label='Lumenal density', 
        title='Membrane density comparison between connected and non-connected')

    # difference between lumenal and membrane density vs distance
    stats_list(
        data=sv_bins, dataNames=distance_bin_names, name='lum_mem_density_diff',
        join='join', groups=categories, identifiers=identifiers, 
        reference=reference, test='t', 
        y_label='Difference between lumenal and membrane density', 
        title='Lumenal - membrane density dependence on distance to the AZ')

    # difference between lumenal and membrane density dependence on 
    # connectivity, paired
    stats_list_pair(
        data=[non_conn_sv, conn_sv], dataNames=['non_connected', 'connected'], 
        name='lum_mem_density_diff', groups=categories, 
        identifiers=identifiers, reference=reference, test='t_rel', 
        label='experiment', 
        y_label='Difference between lumenal and membrane density', 
        title='Lumenal and membrane density dependence on connectivity')


    ###########################################################
    #
    # Vesicle clustering analysis
    #

    # fraction of total vesicles in a largest cluster
    stats(data=clust, name='fract_bound_max', join='join', groups=categories, 
          identifiers=identifiers, reference=reference, test='kruskal',
          y_label='Fraction of total vesicles', 
          title='Fraction of total vesicles in the largest cluster' )

    # histogram of sv cluster sizes 
    # to fix stats and x-labels
    stats(data=clust, name='n_bound_clust', join='join', bins=[1,2,5,50,3000], 
          bin_names=['1','2-4','5-49','50+'], groups=categories, 
          identifiers=identifiers, reference=reference, test='chi2',
          y_label='N clusters', title='Histogram of cluster sizes')

    # loops / connections per tomo
    stats(data=clust, name='redundancy_obs', join='join', groups=categories, 
          identifiers=identifiers, reference=reference, test='kruskal',
          y_label='N loops / N connectors', 
          title='Redundancy (loops per connector) per observation')

    # loops / links per tomo
    stats(data=clust, name='redundancy_links_obs', join='join',
          groups=categories, identifiers=identifiers, reference=reference, 
          test='kruskal', y_label='N loops / N links', 
          title='Redundancy (loops per link) per observation')

    ###########################################################
    #
    # Connectivity analysis of svs
    #
        
    # fraction of svs that are connected
    stats(data=bulk_sv, name='n_connection', join='join', bins=[0,1,100], 
          fraction=1, groups=categories, identifiers=identifiers, test='chi2', 
          reference=reference, y_label='Fraction of all vesicles',
          title='Fraction of vesicles that are connected')

    # fraction of svs that are connected per distance bins
    stats_list(
        data=sv_bins, dataNames=distance_bin_names,  groups=categories,
        identifiers=identifiers, name='n_connection', bins=[0,1,100],  
        join='join', test='chi2', reference=reference, 
        x_label=distance_bins_label, y_label='Fraction of svs',
        title='Fraction of connected svs')
        
    # n connections per sv 
    stats(data=bulk_sv, name='n_connection', join='join', groups=categories,
          identifiers=identifiers, reference=reference, test='kruskal', 
          y_label='N connectors', title='N connectors per vesicle')

    # n connections per connected sv 
    stats(
        data=bulk_conn_sv, name='n_connection', join='join', groups=categories,
        identifiers=identifiers, reference=reference, test='kruskal', 
        y_label='N connectors', title='N connectors per connected vesicle')

    # n connections per sv dependence on distance 
    stats_list(
        data=sv_bins, dataNames=distance_bin_names, name='n_connection', 
        join='join', groups=categories, identifiers=identifiers, 
        reference=reference, test='kruskal', y_label='N connectors', 
        title='N connectors per vesicle')

    # n connections per connected sv dependence on distance 
    stats_list(
        data=bulk_conn_sv.splitByDistance(distance_bins), 
        dataNames=distance_bin_names, name='n_connection', 
        join='join', groups=categories, identifiers=identifiers, 
        reference=reference, test='kruskal', y_label='N connectors', 
        title='N connectors per connected vesicle')

    # histogram of n connectors for connected svs
    stats(data=bulk_conn_sv, name='n_connection', bins=[1,2,3,100], 
          bin_names=['1', '2', '>2'], join='join', groups=categories, 
          identifiers=identifiers, test='chi2', reference=reference,
          y_label='N svs', 
          title='Histogram of number of connectors per connected sv')

    # fraction of svs that are linked per distance bins
    stats_list(
        data=sv_bins, dataNames=distance_bin_names,  groups=categories,
        identifiers=identifiers, name='n_linked', bins=[0,1,100],  join='join', 
        test='chi2', reference=reference, 
        x_label=distance_bins_label, y_label='Fraction of svs',
        title='Fraction of connected svs')
        
    # n links per sv dependence on distance 
    stats_list(
        data=sv_bins, dataNames=distance_bin_names, name='n_linked', 
        join='join', groups=categories, identifiers=identifiers, 
        reference=reference, test='kruskal', 
        y_label='N connectors', title='N connectors per vesicle')

    # fraction of near svs that are connected dependence on tethering
    stats_list(
        data=[near_teth_sv, near_non_teth_sv], 
        dataNames=['tethered', 'non_tethered'], name='n_connection', 
        join='join', bins=[0,1,100],  groups=categories, 
        identifiers=identifiers, test='chi2', reference=reference, 
        y_label='Fraction of vesicles that are connected',
        title='Proximal vesicles connectivity')

    # connector length
    # Q: Shouldn't length use t-test?
    stats(data=conn, name='length_nm', join='join', groups=categories, 
          identifiers=identifiers, test='kruskal', reference=reference,
          y_label='Length [nm]', title='Mean connector length')

    # connector length dependence on distance to the AZ
    # Not good because distance to the AZ not calculated in many experiments
    stats_list(
        data=conn.splitByDistance(distance=distance_bins), 
        dataNames=distance_bin_names, name='length_nm', join='join', 
        groups=categories, identifiers=identifiers, test='kruskal', 
        reference=reference, y_label='Length [nm]', 
        title='Mean connector length dependence on distance')

    # connector length of proximal svs
    stats(data=conn.extractByVesicles(vesicles=near_sv, 
                                        categories=categories)[0],
          name= 'length_nm', join='join', groups=categories, 
          identifiers=identifiers, test='kruskal', reference=reference, 
          y_label='Length [nm]', 
          title='Mean connector length of proximal vesicles')

    # connector length of proximal svs dependence on tethering
    stats_list(
        data=[conn.extractByVesicles(vesicles=near_non_teth_sv)[0],
              conn.extractByVesicles(vesicles=near_teth_sv)[0]],
        dataNames=['non_teth_sv', 'teth_sv'], name= 'length_nm', 
        join='join', groups=categories, identifiers=identifiers, test='kruskal',
        reference=reference, y_label='Length [nm]', 
        title='Mean connector length dependence on tethering')

    # connector length histogram
    stats(data=conn, name='length_nm', bins=rough_length_bins, 
          bin_names=rough_length_bin_names, join='join', groups=categories, 
          identifiers=identifiers, test='chi2', reference=reference,
          y_label='Number of connectors', x_label='Length [nm]', 
          title='Connectors length histogram')


    ###########################################################
    #
    # Tethering based analysis of svs
    #

    # fraction of near svs that are tethered
    stats(data=near_sv, name='n_tether', join='join', bins=[0,1,100], 
          fraction=1, groups=categories, identifiers=identifiers, test='chi2', 
          reference=reference, y_label='Fraction of all vesicles',
          title='Fraction of proximal vesicles that are tetehered')

    # n tethers per near sv
    stats(data=near_sv, name='n_tether', join='join', groups=categories, 
          identifiers=identifiers, reference=reference, test='kruskal', 
          title='N tethers per proximal sv', y_label='N tethers') 
    
    # n tethers per tethered sv 
    stats(data=near_teth_sv, name='n_tether', join='join', groups=categories, 
          identifiers=identifiers, reference=reference, test='kruskal', 
          title='N tethers per tethered proximal sv', y_label='N tethers') 
    
    # histogram of n tethers for near svs
    stats(data=near_sv, name='n_tether', bins=[0,1,3,100], 
          bin_names=['0', '1-2', '>2'], join='join', groups=categories, 
          identifiers=identifiers, test='chi2', reference=reference,
          x_label='N tethers', y_label='N svs', 
          title='Histogram of number of tethers per proximal sv')

    # histogram of n tethers for proximal tethered svs
    stats(data=near_teth_sv, name='n_tether', bins=[1,2,3,100], 
          bin_names=['0', '1-2', '>2'], join='join', groups=categories, 
          identifiers=identifiers, test='chi2', reference=reference,
          x_label='N tethers', y_label='N svs', 
          title='Histogram of number of tethers per proximal sv')

    # correlation between min sv distance to the AZ and n tethers
    correlation(
        xData=near_teth_sv, xName='minDistance_nm', yName='n_tether', 
        join='join', groups=categories, identifiers=identifiers, test='r', 
        x_label='Min distance to the AZ [nm]', y_label='N tethers', 
        title=('Proximal sv correlation between min distance and n tethers'))

    # mean tether length vs n tether (for each sv) correlation for tethered svs
    correlation(
        xData=near_teth_sv, yName='n_tether', xName='mean_tether_nm',
        groups=categories, identifiers=identifiers, join='join', test='r', 
        x_label='Mean tether length per vesicle [nm]', y_label='N tethers', 
        title='Correlation between mean tether length (per sv) and N tethers')

    # tether length
    # Q: Shouldn't length use t-test?
    stats(data=tether, name='length_nm', join='join', groups=categories, 
          identifiers=identifiers, test='kruskal', reference=reference,
          y_label='Length [nm]', title='Mean tether length')

    # tether length dependence on connectivity
    stats_list(
        data=[tether.extractByVesicles(vesicles=near_non_conn_sv,
                                       categories=categories)[0],
              tether.extractByVesicles(vesicles=near_conn_sv, 
                                       categories=categories)[0]],
        dataNames=['non_connected', 'connected'], name= 'length_nm', 
        join='join', groups=categories, identifiers=identifiers, test='kruskal',
        reference=reference, y_label='Length [nm]', 
        title='Mean tether length dependence on connectivity')

    # min tethered sv distance to the AZ dependence on connectivity
    stats_list(
        data=[near_teth_non_conn_sv, near_teth_conn_sv], 
        dataNames=['non_connected', 'connected'], name='minDistance_nm', 
        join='join', groups=categories, identifiers=identifiers, test='kruskal',
        reference=reference, y_label='Min distance [nm]', 
        title='Min tethered sv distance dependence on connectivity')

    # tether length histogram, show number of tethers
    stats(data=tether, name='length_nm', bins=rough_length_bins, 
          bin_names=rough_length_bin_names, join='join', groups=categories, 
          identifiers=identifiers, test='chi2', reference=reference,
          y_label='Number of tethers', x_label='Length [nm]', 
          title='Tether length histogram')

    # tether length histogram, show probability
    stats(data=tether, name='length_nm', bins=rough_length_bins, 
          bin_names=rough_length_bin_names, join='join', groups=categories, 
          identifiers=identifiers, test='chi2', reference=reference,
          plot_name='probability', y_label='Fraction of tethers', 
          x_label='Length [nm]', title='Tether length histogram')

    # mean tether length vs n tether (for each sv) correlation
    correlation(
        xData=near_teth_sv, yName='n_tether', xName='mean_tether_nm',
        groups=categories, identifiers=identifiers, join='join', test='r', 
        x_label='Mean tether length [nm]', y_label='N tethers', 
        title='Correlation between mean tether length (per sv) and N tethers')

    # correlation min sv distance to the AZ vs n tether, tethered svs
    correlation(
        xData=near_teth_sv, yName='n_tether', xName='minDistance_nm', 
        groups=categories, identifiers=identifiers, join='join', test='r', 
        x_label='Min sv distance [nm]', y_label='N tethers', 
        title='Correlation between sv distance and N tethers for tethered svs')

    ###########################################################
    #
    # Tethering and connectivity
    #

    # fraction of tethered and connected
    count_histogram(
        data=[near_teth_conn_sv, near_teth_non_conn_sv,
              near_non_teth_conn_sv, near_non_teth_non_conn_sv], 
        dataNames=['t_c', 't_nc', 'nt_c', 'nt_nc'], groups=categories, 
        identifiers=identifiers, test='chi2', reference=reference, 
        label='experiment', plot_name='fraction', y_label='Fraction', 
        title='Tethering and connectivity of proximal vesicles')

    # fraction of connected dependence on tethering
    stats_list(
        data=[near_teth_sv, near_non_teth_sv], 
        dataNames=['tethered', 'non_tethered'],  groups=categories,
        identifiers=identifiers, name='n_connection', bins=[0,1,100],  
        join='join', test='chi2', reference=reference, 
        y_label='Fraction of svs',
        title='Fraction of connected proximal svs dependence on tethering')

    # fraction of tethered dependence on connectivity
    stats_list(
        data=[near_conn_sv, near_non_conn_sv], 
        dataNames=['connected', 'non_connected'],  groups=categories,
        identifiers=identifiers, name='n_tether', bins=[0,1,100],  
        join='join', test='chi2', reference=reference, 
        y_label='Fraction of svs',
        title='Fraction of tethered proximal svs dependence on connectivity')

    # n connectors per proximal sv dependence on tethering
    stats_list(
        data=[near_teth_sv, near_non_teth_sv], 
        dataNames=['tethered', 'non_tethered'], name='n_connection', 
        join='join', groups=categories, identifiers=identifiers, 
        test='kruskal', reference=reference, y_label='N connectors',
        title='N connectors per proximal sv dependence on tethering')

    # n connectors per connected proximal sv dependence on tethering
    stats_list(
        data=[near_teth_conn_sv, near_non_teth_conn_sv], 
        dataNames=['tethered', 'non_tethered'], name='n_connection', 
        join='join', groups=categories, identifiers=identifiers, 
        test='kruskal', reference=reference, y_label='N connectors',
        title='N connectors per connected proximal sv dependence on tethering')

    # fraction of near svs that are tethered dependence on connectivity
    stats_list(
        data=[near_conn_sv, near_non_conn_sv], 
        dataNames=['connected', 'non_connected'], name='n_tether', join='join',
        bins=[0,1,100],  groups=categories, identifiers=identifiers, 
        test='chi2', reference=reference, 
        y_label='Fraction of vesicles that are tethered',
        title='Proximal vesicles tethering dependence on connectivity')

    # n tethers per sv dependence on connectivity
    stats_list(
        data=[near_conn_sv, near_non_conn_sv], 
        dataNames=['connected', 'non_connected'], name='n_tether', 
        join='join', groups=categories, identifiers=identifiers, 
        test='t', reference=reference, y_label='N tethers',
        title='N tethers per proximal svs dependece on connectivity')


    ###########################################################
    #
    # RRP analysis
    #
    # Note: RRP is defined by number of tethers, see rrp_ntether_bins
    # (usually >2)

    # fraction of near svs that are in RRP
    stats(data=near_sv, name='n_tether', join='join', bins=[0,3,100], 
          fraction=1, groups=categories, identifiers=identifiers, test='chi2', 
          reference=reference, y_label='Fraction of all vesicles',
          title='Fraction of proximal vesicles that are in RRP')

    # fraction of near tethered svs that are in RRP
    stats(data=near_teth_sv, name='n_tether', join='join', bins=[0,3,100], 
          fraction=1, groups=categories, identifiers=identifiers, test='chi2', 
          reference=reference, y_label='Fraction of all vesicles',
          title='Fraction of proximal tethered vesicles that are in RRP')

    # n tether per tethered sv
    stats_list(
        data=[sv_rrp, sv_non_rrp], dataNames=['rrp', 'non_rrp'], 
        name='n_tether', join='join', groups=categories, 
        identifiers=identifiers, test='kruskal', reference=reference, 
        y_label='N tethers', title='N tethers per vesicle')

    # tether length
    stats_list(
        data=[tether_rrp, tether_non_rrp], dataNames=['rrp', 'non_rrp'], 
        name='length_nm', join='join', groups=categories, 
        identifiers=identifiers, test='t', reference=reference, 
        y_label='Tether length [nm]', 
        title='Tether length for proximal vesicles')

    # fraction of rrp and non-rrp svs
    count_histogram(
        data=[sv_rrp, sv_non_rrp], dataNames=['rrp', 'non_rrp'], 
        groups=categories, identifiers=identifiers, 
        test='chi2', reference=reference, 
        label='experiment', plot_name='fraction', y_label='Fraction', 
        title='Fraction of proximal vesicles by number of tethers')

    # fraction connected
    stats_list(
        data=[sv_rrp, sv_non_rrp], dataNames=['rrp', 'non_rrp'], 
        name='n_connection', join='join', bins=[0,1,100],  
        groups=categories, identifiers=identifiers, test='chi2', 
        reference=reference, y_label='Fraction of vesicles that are connected',
        title='Proximal vesicles connectivity')

    # n connections per tethered sv
    stats_list(
        data=[sv_rrp, sv_non_rrp], dataNames=['rrp', 'non_rrp'], 
        name='n_connection', join='join', groups=categories, 
        identifiers=identifiers, test='kruskal', reference=reference, 
        y_label='N connectors',
        title='N connectors per proximal sv')

    # fraction of short and long tethers
    count_histogram(
        data=[short_tether, long_tether], 
        dataNames=['short_tether', 'long_tether'], 
        groups=categories, identifiers=identifiers, 
        test='chi2', reference=reference, 
        label='experiment', plot_name='fraction', y_label='Fraction', 
        title='Fraction of short and long tethers')

    # n short tethers per sv
    stats(
        data=near_sv, name='n_short_tether', join='join', groups=categories, 
        identifiers=identifiers, test='kruskal', reference=reference, 
        y_label='N tethers', title='N short tethers per proximal vesicle')

    # n long tethers per sv
    stats(
        data=near_sv, name='n_long_tether', join='join', groups=categories, 
        identifiers=identifiers, test='kruskal', reference=reference, 
        y_label='N tethers', title='N long tethers per proximal vesicle')

    # n short tethers per short tethered sv


    ###########################################################
    #
    # AZ analysis
    #
    # Note: AZ surface is defined as the layer 1  

    # surface of the AZ 
    stats(data=near_sv, name='az_surface_um', join='join', groups=categories, 
          identifiers=identifiers, test='t', reference=reference, 
          y_label=r'AZ area [${\mu}m^2$]', title='AZ surface area')

    # surface of the AZ, individual synapses 
    stats(data=near_sv, name='az_surface_um', join=None, groups=categories, 
          identifiers=identifiers, test='t', reference=reference, 
          y_label=r'AZ area [${\mu}m^2$]', title='AZ surface area')

    # N proximal svs per synapse
    stats(data=near_sv, name='n_vesicle', join='join', groups=categories, 
          identifiers=identifiers, test='t', reference=reference, 
          y_label='Number of vesicles',
          title='Number of proximal vesicles per synapse')

    # N proximal vesicles per unit (1 um^2) AZ surface 
    stats(data=near_sv, name='vesicle_per_area_um', join='join', 
          groups=categories, identifiers=identifiers, test='t', 
          reference=reference, y_label='Number of vesicles', 
          title=r'Number of proximal vesicles per unit ($1 {\mu}m^2$) AZ area')

    # N tethers per synapse
    stats(data=tether, name='n_tether', join='join', groups=categories, 
          identifiers=identifiers, test='t', reference=reference, 
          y_label='Number of tethers',  title='Number of tethers per synapse')

    # N tethers per unit AZ area (um)
    stats(data=tether, name='tether_per_area_um', join='join', 
          groups=categories, identifiers=identifiers, test='t', 
          reference=reference, y_label='Number of tethers', 
          title=r'Number of tethers per unit ($1 {\mu}m^2$) AZ area')

    # N tethered and non-tethered proximal svs per synapse
    stats_list(
        data=[near_non_teth_sv, near_teth_sv], 
        dataNames=['non_tethered', 'tethered'], 
        name='n_vesicle', join='join', groups=categories, 
        identifiers=identifiers, test='t', reference=reference, 
        y_label='Number of vesicles',
        title=('N tethered and non-tethered proximal vesicles per synapse'))

    # N tethered and non-tethered proximal svs per unit (1 um^2) AZ area
    stats_list(
        data=[near_non_teth_sv, near_teth_sv], 
        dataNames=['non_tethered', 'tethered'], 
        name='vesicle_per_area_um', join='join', groups=categories, 
        identifiers=identifiers, test='t', reference=reference, 
        y_label='Number of vesicles',
        title=('N tethered and non-tethered proximal vesicles per '
               + r'unit ($1 {\mu}m^2$) AZ area'))

    # N tethered /connected proximal svs per synapse
    stats_list(
        data=[near_teth_conn_sv, near_teth_non_conn_sv,
              near_non_teth_conn_sv, near_non_teth_non_conn_sv], 
        dataNames=['t_c', 't_nc', 'nt_c', 'nt_nc'], 
        name='n_vesicle', join='join', groups=categories, 
        identifiers=identifiers, test='t', reference=reference, 
        y_label='Number of vesicles',
        title='N tethered / connected proximal vesicles per synapse')

    # N tethered /connected proximal svs per unit (1 um^2) AZ area
    stats_list(
        data=[near_teth_conn_sv, near_teth_non_conn_sv,
              near_non_teth_conn_sv, near_non_teth_non_conn_sv], 
        dataNames=['t_c', 't_nc', 'nt_c', 'nt_nc'], name='vesicle_per_area_um', 
        join='join', groups=categories, identifiers=identifiers, test='t', 
        reference=reference, y_label='Number of vesicles',
        title=('N tethered / connected proximal vesicles per '
               + r'unit ($1 {\mu}m^2$) AZ area'))

    # N rrp and non-rrp svs per synapse
    stats_list(
        data=[sv_rrp, sv_non_rrp], dataNames=['rrp', 'non_rrp'], 
        name='n_vesicle', join='join', groups=categories, 
        identifiers=identifiers, test='t', reference=reference, 
        y_label='Number of vesicles',
        title=('N vesicles per synapse, dependence on RRP'))

    # N rrp and non-rrp proximal svs per unit (1 um^2) AZ area
    stats_list(
        data=[sv_rrp, sv_non_rrp], dataNames=['rrp', 'non_rrp'], 
        name='vesicle_per_area_um', join='join', groups=categories, 
        identifiers=identifiers, test='t', reference=reference, 
        y_label='Number of vesicles',
        title=('N proximal vesicles per unit ($1 {\mu}m^2$) AZ area,'
               + ' dependence on RRP'))

    # correlation between number of proximal vesicles and the AZ surface
    correlation(
        xData=near_sv, xName='az_surface_um', yData=near_sv, yName='n_vesicle', 
        test='r', groups=categories, identifiers=identifiers, join='join', 
        x_label='AZ surface area [${\mu}m^2$]', y_label='N vesicles',
        title='Correlation between N proximal vesicles and AZ surface')

    # correlation between number of tethered vesicles and the AZ surface
    correlation(
        xData=near_sv, xName='az_surface_um', yData=near_teth_sv, 
        yName='n_vesicle', test='r', groups=categories, 
        identifiers=identifiers, join='join', 
        x_label='AZ surface area [${\mu}m^2$]', y_label='N vesicles',
        title='Correlation between N tethered vesicles and AZ surface')


    ###########################################################
    #
    # Numbers of analyzed
    #

    # number of synapses
    [(categ, len(bulk_sv[categ].identifiers)) for categ in categories]

    # number of bulk svs (within 250 nm)
    [(categ, len(pyto.util.nested.flatten(bulk_sv[categ].ids))) \
         for categ in categories]

    # number of tethers
    [(categ, len(pyto.util.nested.flatten(tether[categ].ids))) \
         for categ in categories]

    # number of connections in bulk
    [(categ, len(pyto.util.nested.flatten(conn[categ].ids))) \
         for categ in categories]



# run if standalone
if __name__ == '__main__':
    main()
