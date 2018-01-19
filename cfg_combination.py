#!/usr/bin/python

import numpy as np
import os, sys, subprocess
import argparse
import mtoutils
from configobj import ConfigObj
import subprocess
import threading
from random import random, randint


# TODO :instead of creating all the configuration files, use pipe to tranfer the configuration to trajextract
class CVConfigList(object):
    def __init__(self):
        self.range = []
        self.name = None
        self.next = None
    
    def insert_range (self,initial,end,step):
        self.range = np.arange(float(initial), float (end)+ float(step) / 2, float (step))
    
    def insert_value (self,value):
        self.range.append(value)
    
    def get_total_combination(self):
        if self.name == None:
            return 1
        return len(self.range) * self.next.get_total_combination()
    
    def write_config(self, ID, config):
        if self.name != None:
            config[self.name] = self.range[(ID/self.next.get_total_combination())];
            self.next.write_config(ID%self.next.get_total_combination(),config);
        else:
            config.write();

    #print the content in the cfg_list.(not used)
    def print_content(self):
        print self.name,self.range
        if self.next != None:
            self.next.print_content();
    
    def length(self):
        if self.next != None:
            return 1 + self.next.length()
        return 1
    
    # methods for genetic algorithm
    # crossover two parentids and produce two offsping ids
    def crossover(self, ID1, ID2, crossoverpoint):
        if self.next != None:
            if crossoverpoint != 0:
                self.next.crossover(ID1 ,ID2, crossoverpoint-1)
            total_combination = self.get_total_combination()
            newID1 = ID1 - (ID1 % total_combination) + (ID2 % total_combination)
            newID2 = ID2 - (ID2 % total_combination) + (ID1 % total_combination)
            return newID1, newID2
        return ID1, ID2
        
        
    # mutation of a offspringid
    def mutation(self, offspringID):
        length = len(self.range)
        if self.next != None:
            if length > 1:
                if random() < 0.1:
                    if (offspringID % self.get_total_combination()) / self.next.get_total_combination() < length-1:
                        offspringID += self.next.get_total_combination()
                elif random() < 0.1:
                    if (offspringID % self.get_total_combination()) / self.next.get_total_combination() > 0:
                        offspringID -= self.next.get_total_combination()
            return self.next.mutation(offspringID)
        else:
            if length > 1:
                if random() < 0.1:
                    if offspringID % self.get_total_combination() < length-1:
                        offspringID += self.next.get_total_combination()
                elif random() < 0.1:
                    if offspringID % self.get_total_combination() > 0:
                        offspringID -= self.next.get_total_combination()
            return offspringID
    
    def RandomIndividual(self):
        return randint(0,self.get_total_combination()-1)
        
def wait_all_subproccess (p_list):
    for p in p_list:
        p.wait();
        
def config_to_list(cfglist, config):
    p = cfglist
    for cfg in config:
        value = config[cfg];
        range_cfg = value.split()
        p.name = cfg
        if len(range_cfg) == 1 :
            p.insert_value(range_cfg[0])
        elif len(range_cfg) == 3:
            p.insert_range(range_cfg[0], range_cfg[1], range_cfg[2])
        elif len(range_cfg) == 2:
            p.insert_range(range_cfg[0], range_cfg[1], 1.0)
        p.next = CVConfigList()
        p = p.next

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="create combination of datasets (sqlite(s)) with a range of configuration")
    parser.add_argument('inputVideo', help= "input video filename")
    parser.add_argument('-d', '--database-file', dest='databaseFile', help="Name of the databaseFile. If this file is not existsed, program will run trajextract.py and cvplayer.py.")
    parser.add_argument('-o', '--homography-file', dest='homography', required = True, help= "Name of the homography file for cvplayer.")
    parser.add_argument('-t', '--configuration-file', dest='range_cfg', help= "the configuration-file contain the range of configuration")
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
    cfg_list = CVConfigList()
    thread_cfgtolist = threading.Thread(target = config_to_list, args = (cfg_list, config))
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
                command = ['trajextract.py',args.inputVideo,'-m',args.maskFilename]
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

    config_files = "cfg_files/Cfg_ID_"
    sqlite_files = "sql_files/Sqlite_ID_"
    os.mkdir('cfg_files')
    os.mkdir('sql_files')
    thread_cfgtolist.join();
    combination = cfg_list.get_total_combination()

    # create all combnation of cfg files and cp databaseFile
    process = []
    for ID in range(0,combination):
        cfg_name = config_files +str(ID)+'.cfg'
        sql_name = sqlite_files +str(ID)+'.sqlite'
        
        open(cfg_name,'w').close()
        config = ConfigObj(cfg_name)
        cfg_list.write_config(ID,config)
        if ID == 0:
            print("creating the first tracking only database template.")
            command = ['trajextract.py',args.inputVideo,'-d',sql_name,'-t',cfg_name,'-o',args.homography,'-m',args.maskFilename,'--tf']
            p = subprocess.Popen(command)
            p.wait()
            tf_dbfile = sql_name
        else :
            command = ['cp',tf_dbfile,sql_name]
            process.append(subprocess.Popen(command))


    wait_all_subproccess(process);

    # run trajextract with all combination of cunfigurations
    process = []
    for ID in range(0,combination):
        cfg_name = config_files +str(ID)+'.cfg'
        sql_name = sqlite_files +str(ID)+'.sqlite'
        command = ['trajextract.py',args.inputVideo,'-t',cfg_name,'-d',sql_name,'--gf']
        process.append(subprocess.Popen(command))

    wait_all_subproccess(process);

    print "cfg_edit has successful create "+ str(combination) +" of data sets"
    decision = raw_input('Do you want to compare all combination of data sets to ground truth(Annotaion)? [Y/N]\n')
    if decision == "Y" or decision == "y":
        command = ['compare.py','-d',databaseFile,'-o',args.homography,'-m','10','-f','0','-l',str(combination-1)];
        process = subprocess.Popen(command)
        process.wait()
