#!/usr/bin/env python3
import os, sys, subprocess
import argparse
import subprocess
import threading
import timeit
from configobj import ConfigObj
from cvguipy import cvconfig

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="compare two configuration files")
    parser.add_argument('config1', help= "configuration file name")
    parser.add_argument('config2', help= "configuration file name")
    args = parser.parse_args()

    # inputVideo check
    if not os.path.exists(args.config1):
        print("{} does not exist! Exiting...".format(args.config1))
        sys.exit(1)
        
    if not os.path.exists(args.config2):
        print("{} does not exist! Exiting...".format(args.config2))
        sys.exit(1)

    config1 = ConfigObj(args.config1)
    config2 = ConfigObj(args.config2)
    threads = []
    
    # get configuration and put them to a List
    cfg_list1 = cvconfig.CVConfigList()
    threads.append(threading.Thread(target = cvconfig.config_to_list, args = (cfg_list1, config1)))
    cfg_list2 = cvconfig.CVConfigList()
    threads.append(threading.Thread(target = cvconfig.config_to_list, args = (cfg_list2, config2)))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    
    while cfg_list1.name is not None and cfg_list2.name is not None:
        if cfg_list1.name != cfg_list2.name:
            print("Not Cosistent Configuration...Exiting...")
            sys.exit(1)
        if cfg_list1.range[0] != cfg_list2.range[0]:
            print("{}: {} | {}".format(cfg_list1.name, cfg_list1.range, cfg_list2.range))
        cfg_list1 = cfg_list1.next
        cfg_list2 = cfg_list2.next
