import os, sys, subprocess
import argparse
import subprocess
import threading
import timeit
from random import random, randint
import numpy as np
from configobj import ConfigObj

# TODO NOTE - load only the useful configuration
class CVConfigList(object):
    def __init__(self):
        self.range = []
        self.name = None
        self.next = None
        self.root = None
    
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
            config[self.name] = self.range[int(ID/self.next.get_total_combination())];
            self.next.write_config(ID%self.next.get_total_combination(),config);
        else:
            config.write();

    #print the content in the cfg_list.(not used)
    def print_content(self):
        print(self.name,self.range)
        if self.next != None:
            self.next.print_content();
    
    def length(self):
        if self.next != None:
            return 1 + self.next.length()
        return 1
    
# ------------------------------------------------------------------------------
# methods for genetic algorithm

    # crossover two parentids and produce two offsping ids
    # NOTE - single crossover may have low performance if using the list as the crossover dimension
    def crossover(self, ID1, ID2, crossoverpoint):
        if self.next != None:
            if crossoverpoint != 0:
                self.next.crossover(ID1 ,ID2, crossoverpoint-1)
            total_combination = self.get_total_combination()
            newID1 = ID1 - (ID1 % total_combination) + (ID2 % total_combination)
            newID2 = ID2 - (ID2 % total_combination) + (ID1 % total_combination)
            return newID1, newID2
        return ID1, ID2
    
    # NOTE - curent workaround to increase single point crossover performace
    def crossover_dimension(self):
        ptr = self
        dimension = [0, 0]
        level = 0
        index = 0
        while ptr != None:
            level += 1
            if len(self.range) > 1:
                dimension[index] = level
                if index == 0:
                    index += 1
            ptr = ptr.next
        return (dimension[0], dimension[1])
    
    # 50% uniform crossover
    def crossover(self, ID1, ID2):
        if self == None:
            return ID1, ID2
        tc = self.get_total_combination() * len(self.range)
        while self.name != None:
            tc /= len(self.range)
            if random() > 0.5:
                newID1 = ID1 - (ID1 % tc) + (ID2 % tc)
                newID2 = ID2 - (ID2 % tc) + (ID1 % tc)
                ID1 = newID1
                ID2 = newID2
            self = self.next
        return ID1, ID2
                
    # mutation of a offspringid
    # TODO NOTE - implement dynamic mutation rate
    def mutation(self, offspringID, MutationRate):
        # TODO NOTE - maybe change mutation pattern
        if self.name == None:
            return offspringID
        length = len(self.range)
        if length > 1:
            tc = self.get_total_combination()
            mutate_value = tc / length
            if random() > 0.5:
                while random() < MutationRate:
                    if (offspringID % tc) / mutate_value < length-1:
                        offspringID += mutate_value
            else:
                while random() < MutationRate:
                    if (offspringID % tc) / mutate_value > 0:
                        offspringID -= mutate_value
        if self.next == None:
            return offspringID
        return self.next.mutation(offspringID, MutationRate)
        
    # generate a randome individual
    def RandomIndividual(self):
        return randint(0,self.get_total_combination()-1)
    
# End of methods for genetic algorithm
# ------------------------------------------------------------------------------
def wait_all_subproccess(p_list):
    for p in p_list:
        p.wait()

# create list of configurations
def config_to_list(cfglist, config):
    if cfglist.name is not None:
        print("cfg_list already contians something.")
        return -1
    p = cfglist
    p.root = p
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
        p.next.root = p.root
        p = p.next
    return 0
