#!/usr/bin/env python3

import os, sys, subprocess
import argparse
import subprocess
import threading
import timeit
from random import random, randint
import numpy as np
from configobj import ConfigObj
from cvguipy import cvconfig

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="create combination of datasets (sqlite(s)) with a range of configuration")
    parser.add_argument('inputVideo', help= "input video filename")
    parser.add_argument('-d', '--database-file', dest='databaseFile', help="Name of the databaseFile. If this file is not existsed, program will run trajextract.py and cvplayer.py.")
    parser.add_argument('-o', '--homography-file', dest='homography', required = True, help= "Name of the homography file for cvplayer.")
    parser.add_argument('-r', '--configuration-file', dest='range_cfg', help= "the configuration-file contain the range of configuration")
    parser.add_argument('-m', '--mask-File', dest='maskFilename', help="Name of the mask-File for trajextract")
    args = parser.parse_args()

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
        databaseFile=args.databaseFile
        
    # timer
    start = timeit.default_timer()
     
    config_files = "cfg_files/Cfg_ID_"
    sqlite_files = "sql_files/Sqlite_ID_"
    os.mkdir('cfg_files')
    os.mkdir('sql_files')
    thread_cfgtolist.join();
    combination = cfg_list.get_total_combination()

    # create all combnation of cfg files and cp databaseFile
    process = []
    for ID in range(0,combination):
        cfg_name = config_files + str(ID) + '.cfg'
        sql_name = sqlite_files + str(ID) + '.sqlite'
        
        open(cfg_name,'w').close()
        config = ConfigObj(cfg_name)
        cfg_list.write_config(ID,config)
        if ID == 0:
            # create one tracking_feature_only sqlite
            print("creating the first tracking only database template.")
            if args.maskFilename is not None:
                command = ['trajextract.py',args.inputVideo, '-d', sql_name, '-t', cfg_name, '-o', args.homography, '-m', args.maskFilename, '--tf']
            else:
                command = ['trajextract.py',args.inputVideo, '-d', sql_name, '-t', cfg_name, '-o', args.homography, '--tf']
            p = subprocess.Popen(command)
            p.wait()
            tf_dbfile = sql_name
        else :
            # duplicate the tracking_feature_only sqlite for every ID
            command = ['cp',tf_dbfile,sql_name]
            process.append(subprocess.Popen(command))
    cvconfig.wait_all_subproccess(process);

    # run trajextract(grouping feature) on all sqlites that contain only tracking feature
    process = []
    for ID in range(0,combination):
        cfg_name = config_files +str(ID)+'.cfg'
        sql_name = sqlite_files +str(ID)+'.sqlite'
        command = ['trajextract.py', args.inputVideo, '-o', args.homography, '-t',cfg_name, '-d', sql_name, '--gf']
        process.append(subprocess.Popen(command))
    cvconfig.wait_all_subproccess(process);
    
    stop = timeit.default_timer()
    print("cfg_edit has successful create "+ str(combination) +" of data sets in " + str(stop - start))
    
    decision = input('Continue searching for the best configuration? [Y/N]\n')
    if decision == "Y" or decision == "y":
        algorithm = input('Which algorithm do you want to use for searching? (Genetic: G, BruteForce: B, To Exit: Q)\n Enter (Q) to exit \n')
        while algorithm not in ['B', 'b', 'G', 'g', 'Q', 'q']:
            print("invalid input......")
            algorithm = input('Which algorithm do you want to use for searching? (Genetic: G, BruteForce: B)\n Enter (Q) to exit \n')
        if algorithm in ['B', 'b']:
            command = ['calibBruteforceSearch.py', '-d', databaseFile, '-o', args.homography, '-md', '10', '-f', '0', '-l', str(combination-1)];
            process = subprocess.Popen(command)
            process.wait()
        elif algorithm in ['G', 'g']:
            print("Now...enter require parameter for genetic algorithm")
            population = input('Population size: ')
            num_parent = input('Selection size: ')
            accuracy = input('Accuracy (Number of generation to stop if no improvement): ')
            command = ['calibGeneticSearch.py', '-d', args.databaseFile, '-o', args.homography, '-a', accuracy, '-p', population, '-np', num_parent]
            process = subprocess.Popen(command)
            process.wait()
            
            
