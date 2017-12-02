#!/usr/bin/python

import os, sys, subprocess
import argparse
import mtoutils
import subprocess
import trajstorage, storage
import moving
from numpy import loadtxt
from numpy.linalg import inv
import matplotlib.pyplot as plt
import storage

if __name__ == '__main__' :
    parser = argparse.ArgumentParser(usage='%(prog)s [options] filename')
    parser.add_argument('-d', '--database-file', dest ='databaseFile', help ="Name of the databaseFile.", required = True)
    parser.add_argument('-o', '--homography-file', dest ='homography', help = "Name of the homography file.", required = True)
    parser.add_argument('-f', '--First-ID', dest ='firstID', help = "the first ID of the range of ID", required = True, type = int)
    parser.add_argument('-l', '--Last-ID', dest ='lastID', help = "the last ID of the range of ID", required = True, type = int)
    parser.add_argument('-m', '--matching-distance', dest='matchDistance', help = "matchDistance", required = True, type = float)
    parser.add_argument('-mota', '--print-MOTA', dest='PrintMOTA', action = 'store_true', help = "Print MOTA for each ID.")
    args = parser.parse_args()
    dbfile = args.databaseFile;
    homography = loadtxt(args.homography)
    sqlite_files = "sql_files/Sqlite_ID_"
    
    cdb = trajstorage.CVsqlite(dbfile)
    cdb.open()
    cdb.getLatestAnnotation()
    cdb.createBoundingBoxTable(cdb.latestannotations, inv(homography))
    cdb.loadAnnotaion()
    for a in cdb.annotations:
        a.computeCentroidTrajectory(homography)
    print "Latest Annotaions in "+dbfile+": ", cdb.latestannotations
    # for row in cdb.boundingbox:
    #     print row
    cdb.frameNumbers = cdb.getFrameList()
    firstFrame = cdb.frameNumbers[0]
    lastFrame = cdb.frameNumbers[-1]
    foundmota = 0
    ID = args.firstID
    
    # matplot
    x = []
    y = []
    
    for i in range(args.firstID,args.lastID + 1):
        
        print "Analyzing ID ", i
        obj = trajstorage.CVsqlite(sqlite_files+str(i)+".sqlite")
        obj.loadObjects()
        
        motp, mota, mt, mme, fpt, gt = moving.computeClearMOT(cdb.annotations, obj.objects, args.matchDistance, firstFrame, lastFrame)
        y.append(i)
        x.append(mota)
        if foundmota < mota:
            foundmota = mota
            ID = i
        obj.close()
        
        if args.PrintMOTA:
            print "MOTA: ", mota
        # print "MOTP: ", motp
        # print 'MOTP: {}'.format(motp)
        # print 'MOTA: {}'.format(mota)
        # print 'Number of missed objects.frames: {}'.format(mt)
        # print 'Number of mismatches: {}'.format(mme)
        # print 'Number of false alarms.frames: {}'.format(fpt)
    
    print "Best multiple object tracking accuracy (MOTA)", foundmota
    print "ID:", ID
    
    
    # matplot
    plt.plot(x,y,'ro')
    plt.axis([-1, 1, 0, 100])
    plt.show()
    
    
    # objects = storage.loadTrajectoriesFromSqlite(dbfile, 'object')
    # motp, mota, mt, mme, fpt, gt = moving.computeClearMOT(cdb.annotations, objects, 10, 0, 900)
    #
    # print 'MOTP: {}'.format(motp)
    # print 'MOTA: {}'.format(mota)
    # print 'Number of missed objects.frames: {}'.format(mt)
    # print 'Number of mismatches: {}'.format(mme)
    # print 'Number of false alarms.frames: {}'.format(fpt)
    
    
    cdb.close()
