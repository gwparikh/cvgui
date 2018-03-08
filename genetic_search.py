#!/usr/bin/python

import os, sys, subprocess
import argparse
import subprocess
import threading
import timeit
from multiprocessing import Queue, Lock
from configobj import ConfigObj
from numpy import loadtxt
from numpy.linalg import inv
import matplotlib.pyplot as plt
import moving
from cvguipy import trajstorage, cvgenetic, cvconfig

""" This script uses genetic algorithm to search for the best configuration (precreated sqlites are not needed)"""
# TODO NOTE - This can be merge into genetic_compare with an option to create sqlite_files and cfg_files before running computeMOT
# Most part of this script is same as genetic_compare.py. (considering this is an extension of genetic_compare.py)

# class for genetic algorithm
class GeneticCompare(object):
    def __init__(self, motalist, IDlist, cfg_list, lock):
        self.motalist = motalist
        self.IDlist = IDlist
        self.cfg_list = cfg_list
        self.lock = lock
    
    # This is used for calculte fitness of individual in genetic algorithn.
    # It is modified to create sqlite and cfg file before tuning computeClearMOT.
    # NOTE errors show up when loading two same ID 
    def computeMOT(self, i):
        
        # create sqlite and cfg file with id i
        cfg_name = config_files +str(i)+'.cfg'
        sql_name = sqlite_files +str(i)+'.sqlite'
        open(cfg_name,'w').close()
        config = ConfigObj(cfg_name)
        cfg_list.write_config(i ,config)
        command = ['cp', 'tracking_only.sqlite', sql_name]
        process = subprocess.Popen(command)
        process.wait()
        command = ['trajextract.py', args.inputVideo, '-o', args.homography, '-t', cfg_name, '-d', sql_name, '--gf']
        # suppress output of grouping extraction
        devnull = open(os.devnull, 'wb')
        process = subprocess.Popen(command, stdout = devnull)
        process.wait()
        
        obj = trajstorage.CVsqlite(sql_name)
        print "loading", i
        obj.loadObjects()
        motp, mota, mt, mme, fpt, gt = moving.computeClearMOT(cdb.annotations, obj.objects, args.matchDistance, firstFrame, lastFrame)
        
        self.lock.acquire()
        self.IDlist.put(i)
        self.motalist.put(mota)
        obj.close()
        if args.PrintMOTA:
            print "ID", i, " : ", mota
        self.lock.release()
            
        return mota
        
if __name__ == '__main__' :
    parser = argparse.ArgumentParser(description="compare all sqlites that are created by cfg_combination.py to the Annotated version to find the ID of the best configuration")
    parser.add_argument('inputVideo', help= "input video filename")
    parser.add_argument('-t', '--configuration-file', dest='range_cfg', help= "the configuration-file contain the range of configuration")
    parser.add_argument('-m', '--mask-File', dest='maskFilename', help="Name of the mask-File for trajextract")
    parser.add_argument('-d', '--database-file', dest ='databaseFile', help ="Name of the databaseFile.")
    parser.add_argument('-o', '--homography-file', dest ='homography', help = "Name of the homography file.", required = True)
    parser.add_argument('-md', '--matching-distance', dest='matchDistance', help = "matchDistance", default = 10, type = float)
    parser.add_argument('-a', '--accuracy', dest = 'accuracy', help = "accuracy parameter for genetic algorithm", type = int)
    parser.add_argument('-p', '--population', dest = 'population', help = "population parameter for genetic algorithm", required = True, type = int)
    parser.add_argument('-np', '--num-of-parents', dest = 'num_of_parents', help = "Number of parents that are selected each generation", type = int)
    parser.add_argument('-mota', '--print-MOTA', dest='PrintMOTA', action = 'store_true', help = "Print MOTA for each ID.")
    args = parser.parse_args()
    
    os.mkdir('cfg_files')
    os.mkdir('sql_files')
    sqlite_files = "sql_files/Sqlite_ID_"
    config_files = "cfg_files/Cfg_ID_"
    
    # ------------------initialize annotated version if not existed ---------- #
    # inputVideo check
    if not os.path.exists(args.inputVideo):
        print("Input video {} does not exist! Exiting...".format(args.inputVideo))
        sys.exit(1)

    # configuration file check
    if args.range_cfg is None:
        config = ConfigObj('range.cfg')
    else:
        config = ConfigObj(args.range_cfg)

    # get configuration and put them to a List
    cfg_list = cvconfig.CVConfigList()
    thread_cfgtolist = threading.Thread(target = cvconfig.config_to_list, args = (cfg_list, config))
    thread_cfgtolist.start();
    # check if dbfile name is entered
    if args.databaseFile is None:
        print("Database-file is not entered, running trajextract and cvplayer.")
        if not os.path.exists(args.homography):
            print("Homography file does not exist! Exiting...")
            sys.exit(1)
        else:
            videofile=args.inputVideo
            if 'avi' in videofile:
                if args.maskFilename is not None:
                    command = ['trajextract.py',args.inputVideo,'-m', args.maskFilename,'-o', args.homography]
                else:
                    command = ['trajextract.py',args.inputVideo,'-o', args.homography]
                process = subprocess.Popen(command)
                process.wait()
                databaseFile = videofile.replace('avi','sqlite')
                command = ['cvplayer.py',args.inputVideo,'-d',databaseFile,'-o',args.homography]
                process = subprocess.Popen(command)
                process.wait()
            else:
                print("Input video {} is not 'avi' type. Exiting...".format(args.inputVideo))
                sys.exit(1)
    else:
        databaseFile = args.databaseFile
    thread_cfgtolist.join()
    # ------------------Done initialization for annotation-------------------- #
    
    # create first tracking only database template.
    print("creating the first tracking only database template.")
    if args.maskFilename is not None:
        command = ['trajextract.py',args.inputVideo, '-d', 'tracking_only.sqlite', '-t', 'tracking.cfg', '-o', args.homography, '-m', args.maskFilename, '--tf']
    else:
        command = ['trajextract.py',args.inputVideo, '-d', sql_name, '-t', cfg_name, '-o', args.homography, '--tf']
    process = subprocess.Popen(command)
    process.wait()
    # ----start using genetic algorithm to search for best configuration-------#
    start = timeit.default_timer()
    
    dbfile = databaseFile;
    homography = loadtxt(args.homography)
    
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
    
    foundmota = Queue()
    IDs = Queue()
    lock = Lock()
    
    Comp = GeneticCompare(foundmota, IDs, cfg_list, lock)
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
    print "Best multiple object tracking accuracy (MOTA)", Best_mota
    print "ID:", Best_ID
    stop = timeit.default_timer()
    print str(stop-start) + "s"
    os.remove('tracking_only.sqlite')
    # ------------------------------Done searching----------------------------#
    # use matplot to plot a graph of all calculated IDs along with thier mota
    plt.plot(foundmota ,IDs ,'bo')
    plt.plot(Best_mota, Best_ID, 'ro')
    plt.axis([-1, 1, -1, cfg_list.get_total_combination()])
    plt.xlabel('mota')
    plt.ylabel('ID')
    
    plt.title(b'Best MOTA: '+str(Best_mota) +'\nwith ID: '+str(Best_ID))
    plt.show()
    
    cdb.close()
