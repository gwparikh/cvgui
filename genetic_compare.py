#!/usr/bin/env python3

import os, sys, subprocess
import argparse
import subprocess
import timeit
from multiprocessing import Queue, Lock
from configobj import ConfigObj
from numpy import loadtxt
from numpy.linalg import inv
import matplotlib.pyplot as plt
from trafficintelligence import moving
from cvguipy import trajstorage, cvgenetic

"""compare all precreated sqlite (by cfg_combination.py) with annotated version using genetic algorithm"""
# class for genetic algorithm
class GeneticCompare(object):
    def __init__(self, motalist, IDlist, lock):
        self.motalist = motalist
        self.IDlist = IDlist
        self.lock = lock
        
    # This is used for calculte fitness of individual in genetic algorithm
    def computeMOT(self, i):
        obj = trajstorage.CVsqlite(sqlite_files+str(i)+".sqlite")
        obj.loadObjects()
        motp, mota, mt, mme, fpt, gt = moving.computeClearMOT(cdb.annotations, obj.objects, args.matchDistance, firstFrame, lastFrame)
        self.lock.acquire()
        self.IDlist.put(i)
        self.motalist.put(mota)
        obj.close()
        if args.PrintMOTA:
            print("ID", i, " : ", mota)
        self.lock.release()
        return mota
        
if __name__ == '__main__' :
    parser = argparse.ArgumentParser(description="compare all sqlites that are created by cfg_combination.py to the Annotated version to find the ID of the best configuration")
    parser.add_argument('-d', '--database-file', dest ='databaseFile', help ="Name of the databaseFile.", required = True)
    parser.add_argument('-o', '--homography-file', dest ='homography', help = "Name of the homography file.", required = True)
    parser.add_argument('-md', '--matching-distance', dest='matchDistance', help = "matchDistance", default = 10, type = float)
    parser.add_argument('-a', '--accuracy', dest = 'accuracy', help = "accuracy parameter for genetic algorithm", type = int)
    parser.add_argument('-p', '--population', dest = 'population', help = "population parameter for genetic algorithm", required = True, type = int)
    parser.add_argument('-np', '--num-of-parents', dest = 'num_of_parents', help = "Number of parents that are selected each generation", type = int)
    parser.add_argument('-mota', '--print-MOTA', dest='PrintMOTA', action = 'store_true', help = "Print MOTA for each ID.")
    args = parser.parse_args()
    
    start = timeit.default_timer()
    
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
    print("Latest Annotaions in "+dbfile+": ", cdb.latestannotations)
    # for row in cdb.boundingbox:
    #     print(row)
    cdb.frameNumbers = cdb.getFrameList()
    firstFrame = cdb.frameNumbers[0]
    lastFrame = cdb.frameNumbers[-1]
    
    # put calculated itmes into a Queue
    foundmota = Queue()
    IDs = Queue()
    lock = Lock()
    
    Comp = GeneticCompare(foundmota, IDs, lock)
    config = ConfigObj('range.cfg')
    cfg_list = cfgcomb.CVConfigList()
    cfgcomb.config_to_list(cfg_list, config)
    if args.accuracy != None:
        GeneticCal = cvgenetic.CVGenetic(args.population, cfg_list, Comp.computeMOT, args.accuracy)
    else:
        GeneticCal = cvgenetic.CVGenetic(args.population, cfg_list, Comp.computeMOT)
    if args.num_of_parents != None:
        GeneticCal.run_thread(args.num_of_parents)
    else:
        GeneticCal.run_thread()
    
    # tranform queues to lists
    foundmota = cvgenetic.Queue_to_list(foundmota)
    IDs = cvgenetic.Queue_to_list(IDs)

    Best_mota = max(foundmota)
    Best_ID = IDs[foundmota.index(Best_mota)]
    print("Best multiple object tracking accuracy (MOTA)", Best_mota)
    print("ID:", Best_ID)
    
    stop = timeit.default_timer()
    print(str(stop-start) + "s")
    
    # matplot
    plt.plot(foundmota ,IDs ,'bo')
    plt.plot(Best_mota, Best_ID, 'ro')
    plt.axis([-1, 1, -1, cfg_list.get_total_combination()])
    plt.xlabel('mota')
    plt.ylabel('ID')
    
    plt.title(b'Best MOTA: '+str(Best_mota) +'\nwith ID: '+str(Best_ID))
    plt.show()
    
    cdb.close()
