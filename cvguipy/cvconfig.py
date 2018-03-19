import os, sys, subprocess
import argparse
import subprocess
import threading
import timeit
from random import random, randint
import numpy as np
from configobj import ConfigObj

class CVConfigList(object):
    def __init__(self):
        self.range = []
        self.name = None
        self.next = None
    
    def insert_range (self,initial,end,step):
        self.range = np.arange(float(initial), float(end) + float(step) / 2, float(step))
    
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
    # TODO NOTE - implement advance crossover technique
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
    # TODO NOTE - implement dynamic mutation rate
    def mutation(self, offspringID, MutationRate):
        length = len(self.range)
        # TODO NOTE - maybe change mutation pattern
        if self.next != None:
            if length > 1:
                while random() < MutationRate:
                    if (offspringID % self.get_total_combination()) / self.next.get_total_combination() < length-1:
                        offspringID += self.next.get_total_combination()
                while random() < MutationRate:
                    if (offspringID % self.get_total_combination()) / self.next.get_total_combination() > 0:
                        offspringID -= self.next.get_total_combination()
            return self.next.mutation(offspringID, MutationRate)
        else:
            if length > 1:
                while random() < MutationRate:
                    if offspringID % self.get_total_combination() < length-1:
                        offspringID += self.next.get_total_combination()
                while random() < MutationRate:
                    if offspringID % self.get_total_combination() > 0:
                        offspringID -= self.next.get_total_combination()
            return offspringID
    # generate a randome individual
    def RandomIndividual(self):
        return randint(0,self.get_total_combination()-1)
        
def wait_all_subproccess(p_list):
    for p in p_list:
        p.wait();

# create list of configurations
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
