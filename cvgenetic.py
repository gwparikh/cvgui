#!/usr/bin/python
from random import randint
    
class Population(object):
    def __init__(self, size):
        self.size = size
        self.individuals = []
        
    def add(self, newindividual):
        if len(self.individuals) < self.size:
            self.individuals.append(newindividual)
        else:
            least = self.get_least_index()
            if self.individuals[least][1] < newindividual[1]:
                self.individuals[least] = newindividual
            
    def get_least_index(self):
        least = 0
        for i in range(len(self.individuals)):
            if self.individuals[i][1] < self.individuals[least][1]:
                least = i;
        return least
    
    # return a list contains two individuals (best and the second best)
    def get_two_best(self):
        if self.individuals[0][1] > self.individuals[1][1]:
            best_two = [self.individuals[0], self.individuals[1]]
        else:
            best_two = [self.individuals[1], self.individuals[0]]
        for individual in self.individuals:
            if individual[1] > best_two[0][1]:
                best_two[0] = individual
            elif individual[1] > best_two[1][1]:
                best_two[1] = individual
        return best_two

class CVGenetic(object):
    def __init__(self, population_size, DataList, CalculateFitness, accuracy = 10):
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
        
    def select(self):
        best_two = self.population.get_two_best()
        if self.best == best_two[0][0]:
            self.timer += 1
        else:
            self.best = best_two[0][0]
            self.timer = 0
        return best_two[0][0], best_two[1][0]
    
    def crossover(self, parent1, parent2):
        return self.DataList.crossover(parent1, parent2, randint(0, self.DataList.length()))
        
    def mutation(self, offspring):
        return self.DataList.mutation(offspring)
        
    def run(self):
        self.timer = 0
        while True:
            best, second_best = self.select()
            offspring1, offspring2 = self.crossover(best, second_best)
            offspring1 = self.mutation(offspring1)
            offspring2 = self.mutation(offspring2)
            fitness1 = self.CalculateFitness(offspring1)
            fitness2 = self.CalculateFitness(offspring2)
            if fitness1 > fitness2:
                newindividual = (offspring1, fitness1)
            else:
                newindividual = (offspring2, fitness2)
            self.population.add(newindividual)
            if self.timer == self.accuracy:
                break
            
            
            
            
            
            
