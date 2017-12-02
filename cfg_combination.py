#!/usr/bin/python

import numpy as np
import os, sys, subprocess
import argparse
import mtoutils
from configobj import ConfigObj
import subprocess

# TODO :instead of creating all the configuration files, use pipe to tranfer the configuration to trajextract
class CVConfigList:
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
        if self != None:
            return 1 + length(self.next)
        return 0

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
    parser = argparse.ArgumentParser(usage='%(prog)s [options] filename')
    parser.add_argument('inputVideo', help= "video file name")
    parser.add_argument('-d', '--database-file', dest='databaseFile', help="Name of the databaseFile. If this file is not existsed, program will run trajextract.py and cvplayer.py.")
    parser.add_argument('-o', '--homography-file', dest='homography', help= "Name of the homography file for cvplayer.")
    parser.add_argument('-t', '--configuration-file', dest='range_cfg', help= "the configuration-file contain the range of configuration")

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
    config_to_list(cfg_list, config)

    combination = cfg_list.get_total_combination()

    # check if dbfile name is entered
    if args.databaseFile is None:
        print("Database-file is not entered, running trajextract and cvplayer.")
        if (args.homography is None) or (not os.path.exists(args.homography)):
            print("Homography file does not exist! Exiting...")
            sys.exit(1)
        else:
            videofile=args.inputVideo
            if 'avi' in videofile:
                command = ['trajextract.py',args.inputVideo]
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
            command = ['trajextract.py',args.inputVideo,'-d',sql_name,'-t',cfg_name,'-o',args.homography,'--tf']
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
