#!/usr/bin/env python

import os, sys, argparse
import numpy as np
from tabulate import tabulate
import moving
from cvguipy import cvgui, trajstorage

# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A script to compute CLEAR MOT tracking performance metrics.")
    parser.add_argument('databaseFilename', nargs='+', help="Name(s) of the database file(s) containing trajectories to evaluate.")
    parser.add_argument('-o', '--homography-file', dest='homography', help="Name of the homography file.", required = True)
    parser.add_argument('-a', '--annotation-file', dest='annotationFile', help="Name of the database file containing annotations.", required=True)
    parser.add_argument('-t', '--annotation-table', dest='annotationTable', help="Name of the table in the annotation database. If not specified, the latest table is used.")
    parser.add_argument('-m', '--matching-distance', dest='matchDistance', type=float, default=10, help="Matching distance for computing tracking performance.")
    args = parser.parse_args()
    
    # open the annotation database and load the homography
    adb = trajstorage.CVsqlite(args.annotationFile)
    hom = np.loadtxt(args.homography)
    
    # NOTE This method of inverting the homography leaves out the conversion
    # from homogeneous coordinates (i.e. dividing by w), but it matches 
    # TrafficIntelligence. It works, but should look into it sometime.
    invHom = np.linalg.inv(hom)
    
    if args.annotationTable is None:
        # if no table name specified, get the latest annotations in the database
        adb.getLatestAnnotation()
        annotationTable = adb.latestannotations
    else:
        # if they did give a table name, make sure it exists
        annotationTable = args.annotationTable
        if not adb.hasTable(annotationTable):
            print("Table '{}' does not exist! Exiting!".format(annotationTable))
            sys.exit(1)
    
    # build the bounding box table for the annotations and load them, computing
    # the centroid trajectory too
    print("Using annotations in table {} ...".format(annotationTable))
    adb.createBoundingBoxTable(annotationTable, invHom)
    adb.loadAnnotations()
    for a in adb.annotations:
        a.computeCentroidTrajectory(hom)
    
    # get the first and last frame numbers of the annotations
    frameNums = adb.getFrameList()
    firstFrame = frameNums[0]
    lastFrame = frameNums[-1]
    
    # loop over the databases and compute performance
    clearMOT = []
    for dbf in args.databaseFilename:
        # open the database and load the trajectories
        print("Loading objects from database {} ...".format(dbf))
        db = trajstorage.CVsqlite(dbf)
        db.loadObjects()
        
        # compute CLEAR MOT metrics
        motp, mota, mt, mme, fpt, gt = moving.computeClearMOT(adb.annotations, db.objects, args.matchDistance, firstFrame, lastFrame)
        
        # store results in a list of lists
        clearMOT.append([dbf, mota, motp, mt, mme, fpt, gt])
    
    # print the results in a table
    heads = ['File',
             'Accuracy',
             'Precision',
             'Missed GT Frames',
             'Mismatches',
             'False Alarm Frames',
             'GT Frames']
    print
    print(tabulate(clearMOT, headers=heads, tablefmt='grid'))
    
    # TODO do we want to plot the results? or is the table enough?
    
    sys.exit(0)
