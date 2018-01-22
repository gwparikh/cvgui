#!/usr/bin/python
from random import randint
import threading
    
class Population(object):
    def __init__(self, size):
        self.size = size
        self.individuals = []
        self.sorted = False
        
    def add(self, newindividual):
        if len(self.individuals) < self.size:
            self.individuals.append(newindividual)
            self.sorted = False
        else:
            least = self.get_least_index()
            if self.individuals[self.size-1][1] < newindividual[1]:
                self.individuals[self.size-1] = newindividual
            self.sorted = False
            
    def get_least_index(self):
        if not self.sorted:
            self.sort()
        return len(self.individuals) - 1
    
    def get_best(self, N):
        if not self.sorted:
            self.sort()
        return self.individuals[:N]
    
    def sort(self):
        if not self.sorted:
            self.individuals.sort(key = lambda t: t[1], reverse = True)
            self.sorted = True

class CVGenetic(object):
    def __init__(self, population_size, DataList, CalculateFitness, accuracy = 10, MutationRate = 0.2):
        print "Initializing Genetic Calculator"
        self.population = Population(population_size)
        self.DataList = DataList
        self.accuracy = accuracy
        self.best = float("-inf")
        self.CalculateFitness = CalculateFitness
        for i in range(population_size):
            individual = DataList.RandomIndividual()
            fitness = CalculateFitness(individual)
            if self.best < fitness:
                self.best = fitness
            newindividual = (individual, fitness)
            self.population.add(newindividual)
        self.timer = 0
        self.MutationRate = MutationRate

    def select(self, N):
        bests = self.population.get_best(N)
        if self.best == bests[0][0]:
            self.timer += 1
        else:
            self.best = bests[0][0]
            self.timer = 0
        print self.best
        return bests
        
    def crossover(self, parent1, parent2):
        return self.DataList.crossover(parent1, parent2, randint(0, self.DataList.length()))
        
    def mutation(self, offspring):
        return self.DataList.mutation(offspring, MutationRate)
    
    # TODO use threads to run crossover, mutation, CalculateFitness
    def run(self, N = 2):
        if N < 2:
            print "number_parents(N) must be greater or equal to 2"
            sys.exit(1)
        self.timer = 0
        generation = 0
        while True:
            print "Generation:", generation
            bests = self.select(N)
            offsprings = []
            newindividuals = []
            for i in range(len(bests)):
                for j in range(i+1, len(bests)):
                    offspring1, offspring2 = self.crossover(bests[i][0], bests[j][0])
                    offsprings.append(offspring1)
                    offsprings.append(offspring2)
            for offspring in offsprings:
                offspring = self.mutation(offspring)
                fitness = self.CalculateFitness(offspring)
                newindividual = (offspring, fitness)
                newindividuals.append(newindividual)
            best_new = newindividuals[0]
            print newindividuals
            for individual in newindividuals:
                if individual[1] > best_new[1]:
                    best_new = individual
            self.population.add(best_new)
            if self.timer == self.accuracy:
                break
            generation += 1
            
            
