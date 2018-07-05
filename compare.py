#!/usr/bin/env python

import os, sys, subprocess
import argparse
import subprocess
from multiprocessing import Process, Lock, Queue
import timeit
from time import sleep
import psutil
from numpy import loadtxt
from numpy.linalg import inv
import matplotlib.pyplot as plt
from trafficintelligence import moving
from cvguipy import trajstorage, cvgenetic

""" compare all precreated sqlite (by cfg_combination.py) with annotated version using brute force """

def computeMOT(i, lock, printlock, motalist, IDlist) :
    obj = trajstorage.CVsqlite(sqlite_files+str(i)+".sqlite")
    obj.loadObjects()
    
    motp, mota, mt, mme, fpt, gt = moving.computeClearMOT(cdb.annotations, obj.objects, args.matchDistance, firstFrame, lastFrame)
    lock.acquire()
    IDlist.put(i)
    motalist.put(mota)
    obj.close()
    lock.release()
    
    printlock.acquire()
    if args.PrintMOTA:
        print("Done ID ----- ", i, "With MOTA:", mota)
    else:
        print("Done ID ----- ", i)
    printlock.release()
    
if __name__ == '__main__' :
    parser = argparse.ArgumentParser(description="compare all sqlites that are created by cfg_combination.py to the Annotated version to find the ID of the best configuration")
    parser.add_argument('-d', '--database-file', dest ='databaseFile', help ="Name of the databaseFile.", required = True)
    parser.add_argument('-o', '--homography-file', dest ='homography', help = "Name of the homography file.", required = True)
    parser.add_argument('-f', '--First-ID', dest ='firstID', help = "the first ID of the range of ID", required = True, type = int)
    parser.add_argument('-l', '--Last-ID', dest ='lastID', help = "the last ID of the range of ID", required = True, type = int)
    parser.add_argument('-md', '--matching-distance', dest='matchDistance', help = "matchDistance", default = 10, type = float)
    parser.add_argument('-mota', '--print-MOTA', dest='PrintMOTA', action = 'store_true', help = "Print MOTA for each ID.")
    parser.add_argument('-ram', '--RAM-monitor', dest='RAMMonitor', help = "parameter for ram_monitor", default = 50, type = float)
    parser.add_argument('-bm', '--block-monitor', dest='BlockMonitor', action = 'store_true', help = "Block RamMonitor")
    args = parser.parse_args()
    dbfile = args.databaseFile;
    homography = loadtxt(args.homography)
    sqlite_files = "sql_files/Sqlite_ID_"
    
    start = timeit.default_timer()
    
    cdb = trajstorage.CVsqlite(dbfile)
    cdb.open()
    cdb.getLatestAnnotation()
    cdb.createBoundingBoxTable(cdb.latestannotations, inv(homography))
    cdb.loadAnnotaion()
    for a in cdb.annotations:
        a.computeCentroidTrajectory(homography)
    print("Latest Annotaions in "+dbfile+": ", cdb.latestannotations)
    # for row in cdb.boundingbox:
    #     print(row)
    cdb.frameNumbers = cdb.getFrameList()
    firstFrame = cdb.frameNumbers[0]
    lastFrame = cdb.frameNumbers[-1]
    
    foundmota = Queue()
    IDs = Queue()
    processes = []
    lock = Lock()
    printlock = Lock()
    # printlock.acquire()
    # TODO NOTE - this is a workaround until we can find a better way to monitor RAM usage
    for i in range(args.firstID,args.lastID + 1):
        while (not args.BlockMonitor) and psutil.virtual_memory()[2] > args.RAMMonitor:
            # print(psutil.virtual_memory()[2])
            sleep(2)
        print("Analyzing ID ", i)
        p = Process(target = computeMOT, args = (i, lock, printlock, foundmota, IDs,))
        processes.append(p)
        p.start()
        if (not args.BlockMonitor) and i%20 == 0 and i != 0:
            # print(psutil.virtual_memory()[2])
            sleep(5)
        if (not args.BlockMonitor) and psutil.virtual_memory()[2] > 20:
            sleep(1)
    # printlock.release()
    for p in processes:
        p.join()
        
    # transform queue to lists
    foundmota = cvgenetic.Queue_to_list(foundmota)
    IDs = cvgenetic.Queue_to_list(IDs)
    
    Best_mota = max(foundmota)
    Best_ID = IDs[foundmota.index(Best_mota)]
    print("Best multiple object tracking accuracy (MOTA)", Best_mota)
    print("ID:", Best_ID)
    stop = timeit.default_timer()
    print(str(stop-start) + "s")
    
    # use matplot to print calculated mota with its ids
    plt.plot(foundmota ,IDs ,'bo')
    plt.plot(Best_mota, Best_ID, 'ro')
    plt.axis([-1, 1, -1, args.lastID+1])
    plt.xlabel('mota')
    plt.ylabel('ID')
    
    plt.title(b'Best MOTA: '+str(Best_mota) +'\nwith ID: '+str(Best_ID))
    plt.show()
    
    cdb.close()
