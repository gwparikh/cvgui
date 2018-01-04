#!/usr/bin/python

from random import randint
    
class population(object):
    def __init__(self, size, CalculateFitness):
        self.size = size
        self.CalculateFitness = CalculateFitness;
        individuals = []
    def add(self, individual):
        if len(individuals) < size:
            newindivudal = (individual, CalculateFitness(individual))
            individuals.append(individual)
        else:
            individuals[self.get_least] = individual
            
    
    def get_least(self):
        
    def get_two_best(self):

class CVGenetic(object):
    def __init__(self, population_size, DataList, CalculateFitness):
        self.CalculateFitness = CalculateFitness
        population = []
        self.size = size
        
    def selection(self):
        
    def crossover(self):
        
    def mutation(self):
        
