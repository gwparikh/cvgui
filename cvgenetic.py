#!/usr/bin/python

from random import randint
    
class Population(object):
    def __init__(self, size):
        self.size = size
        individuals = []
        
    def add(self, newindividual):
        if len(individuals) < size:
            individuals.append(individual)
        else:
            least = self.get_least_index()
            if individuals[least][1] < newindividual[1]:
                individuals[least] = newindividual
            
    def get_least_index(self):
        least = 0
        for i in range(len(individuals)):
            if individuals[i][1] < individuals[least][1]:
                least = i;
        return least
    
    # return a list contains two individuals (best and the second best)
    def get_two_best(self):
        if individuals[0][1] > individuals[1][1]:
            best_two = [individuals[0], individuals[1]]
        else:
            best_two = [individuals[1], individuals[0]]
        for individual in individuals:
            if individual[1] > best_two[0][1]:
                best_two[0] = individual
            elif individual[1] > best_two[1][1]:
                best_two[1] = individual
        return best_two

class CVGenetic(object):
    def __init__(self, population_size, DataList, CalculateFitness, accuracy = 10):
        population = Population(population_size)
        self.DataList = DataList
        self.accuracy = accuracy
        self.CalculateFitness = CalculateFitness
        timer = 0
        best = None
        
    def select(self):
        best_two = population.get_two_best()
        if best == best_two[0][0]:
            timer += 1
        else:
            best = best_two[0][0]
            timer = 0
        return best_two[0][0], best_two[1][0]
    
    def crossover(self, parent1, parent2):
        return DataList.crossover(parent1, parent2)
        
    def mutation(self, offspring):
        return DataList.mutation(offspring)
        
    def run(self):
        timer = 0
        while True:
            best, second_best = self.select()
            offspring1, offspring2 = self.crossover(best, second_best)
            offspring1 = self.mutation(offspring1)
            offspring2 = self.mutation(offspring2)
            fitness1 = CalculateFitness(offspring1)
            fitness2 = CalculateFitness(offspring2)
            if fitness1 > fitness2:
                newindividual = (offspring1, fitness1)
            else:
                newindividual = (offspring2, fitness2)
            population.add(newindividual)
            if timer == accuracy:
                break
        return best
            
            
            
            
            
            
