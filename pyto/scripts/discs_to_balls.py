#!/usr/bin/env python
"""
Reads a labels file containing discs and writes another labels file with the
discs extending to balls having same centers and radii as the discs.

This script may be placed anywhere in the directory tree.

ToDo:
  - see about excentricity

$Id: discs_to_balls.py 1130 2015-05-04 10:52:10Z vladan $
Author: Vladan Lucic (Max Planck Institute for Biochemistry) 
"""
__version__ = "$Revision: 1130 $"

import os
import os.path
import time
import logging

import numpy
import scipy
import scipy.ndimage as ndimage

import pyto
import pyto.scripts.common as common

# import tomo_info
tomo_info = common.__import__(name='tomo_info', path='..')

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s',
                    datefmt='%d %b %Y %H:%M:%S')



##############################################################
#
# Parameters
#
##############################################################

############################################################
#
# Image (grayscale) file. Used only to read image size (shape). Should be in 
# em or mrc format.
#

# name of the image file
if tomo_info is not None: image_file_name = tomo_info.image_file_name
#image_file_name = "../3d/tomo.em"

#####################################################
#
# Labels file containing discs. If the file is in em or mrc format shape, data
# type, byte order and array order are not needed (should be set to None). If
# these variables are specified they will override the values given in em or
# mrc headers.

# name of the input (discs) file 
discs_file_name = "discs.dat"    

# name of the output (balls) file 
balls_file_name = "balls.dat"    

# file dimensions
shape = None   # shape given in header of the disc file (if em
               # or mrc), or in the tomo (grayscale image) header   
#shape = (100, 120, 90) # shape given here

# file data type (e.g. 'int8', 'int16', 'int32', 'float16', 'float64') 
data_type = 'int8'

# file byte order ('<' for little-endian, '>' for big-endian)
byte_order = '<'

# file array order ('FORTRAN' for x-axis fastest, 'C' for z-axis fastest)
array_order = 'FORTRAN'

#########################################
#
# Calculation related parameters
#

# ids of all segments  
if tomo_info is not None: all_ids = tomo_info.all_ids
#all_ids = [2,3,6]       # individual ids
#all_ids = range(2,64)  # range of ids
#all_ids = None         # all segments are to be used

# ids of all discs (all formats given for all_ids can be used)
if tomo_info is not None: vesicle_ids = tomo_info.vesicle_ids
#vesicle_ids = [3,6]

# id or the region surrounding discs
if tomo_info is not None: surround_id = tomo_info.segmentation_region
#surround_id = 2

# first covert balls to discs
balls_to_discs = False

# principal axis of the discs
disc_axis = -1    # along z-axis, discs in x-y plane

# normal vector of the plane that cuts the shpere
normal_vector = [0, 0, 1]  # along z-axis

# angle that denotes how much of the ball is cut by the planes (in radians)
theta = None            # the ball is not cut
#theta = numpy.pi/6   # 30 deg
#theta = numpy.pi/2   # 90 deg, a half ball is cut by each plane 

# increase radii of all discs by this ammount
enlarge_radii = 0.5

# check if all discs exist, have exactly one connected part and don't overlap
check_discs = True


################################################################
#
# Work
#
################################################################

###############################################################
#
# Functions
#

def extract_discs(balls):
    """
    Extracts discs from balls. 
    """

    # find insets for all balls
    all_insets = ndimage.find_objects(input=balls.data)

    # make a disk out of each balls
    for ves_id in vesicle_ids:

        # check if the current ball exists
        if all_insets[ves_id-1] is None:
            logging.warning("Ball with id %d does not exist. Continuing." \
                                % ves_id)
            continue
        
        # find volume slices along disc_axis
        curr_slices = None
        max_slice_sum = 0
        curr_sl = all_insets[ves_id-1][disc_axis]
        for ind in range(curr_sl.start, curr_sl.stop):

            # count elements of the current ball in the current slice
            curr_slices = list(all_insets[ves_id-1])
            curr_slices[disc_axis] = slice(ind, ind+1) 
            curr_slice_sum = (balls.data[curr_slices]==ves_id).sum()

            # remove elements of the 'smaller' slice
            if curr_slice_sum > max_slice_sum:

                # current slice is maximal
                if max_slice_sum > 0:
                    max_inset = balls.data[max_slices]
                    max_inset[max_inset==ves_id] = 0
                max_slice_sum = curr_slice_sum
                max_slices = curr_slices
                
            else:

                # current slice is not maximal
                curr_inset = balls.data[curr_slices]
                curr_inset[curr_inset==ves_id] = 0

################################################################
#
# Main function
#

def main():
    """
    Main function
    """

    # read image and vesicles
    image = common.read_image(file_name=image_file_name)
    new_shape = common.find_shape(file_name=image_file_name, shape=shape,
                       suggest_shape=image.data.shape)
    # read input file
    discs = pyto.segmentation.Ball.read(
        file=discs_file_name, ids=all_ids, byteOrder=byte_order, 
        dataType=data_type, arrayOrder=array_order, shape=new_shape)

    # make discs
    if balls_to_discs:
        extract_discs(balls=discs)
    
    # check
    if check_discs:
        topo = pyto.segmentation.Topology(segments=discs, ids=vesicle_ids)
        n_connected = topo.getHomologyRank(dim=0)[vesicle_ids]
        if not (n_connected == 1).all():
            many = topo.ids[numpy.nonzero(n_connected[topo.ids]>1)[0]]
            if len(many) > 0:
                logging.warning(
                    "The following discs are disconnected: " + str(many))
            zero = topo.ids[numpy.nonzero(n_connected[topo.ids]<1)[0]]
            if len(zero) > 0:
                logging.warning(
                    "The following discs do not exist: " + str(zero))

    # convert discs to balls
    balls = discs.extendDiscs(
        ids=vesicle_ids, axis=disc_axis, cut=normal_vector, theta=theta, 
        enlarge=enlarge_radii, external=surround_id, check=check_discs)

    # write balls file
    balls.write(file=balls_file_name)


# run if standalone
if __name__ == '__main__':
    main()
