#!/usr/bin/python
from random import randint
import threading
import timeit
    
def join_all_threads(threads):
    for t in threads:
        t.join()
        
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
            
    def existed(self, i):
        for individual in self.individuals:
            if individual[0] == i:
                return True
        return False

class CVGenetic(object):
    def __init__(self, population_size, DataList, CalculateFitness, accuracy = 5, MutationRate = 0.2):
        print "Initializing Genetic Calculator"
        start = timeit.default_timer()
        self.population = Population(population_size)
        self.DataList = DataList
        self.accuracy = accuracy
        self.best = float("-inf")
        self.CalculateFitness = CalculateFitness
        self.store = dict()
        newindividuals = []
        threads = []
        for i in range(population_size):
            t = threading.Thread(target = self.create_newindividual, args = (DataList.RandomIndividual(), newindividuals))
            t.start()
            threads.append(t)
        join_all_threads(threads)
        for individual in newindividuals:
            self.population.add(individual)
        self.timer = 0
        self.MutationRate = MutationRate
        stop = timeit.default_timer()
        print str(stop - start)+"s"
        
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
    
    def crossover_t(self, parent1, parent2, offsprings):
        offspring1, offspring2 = self.crossover(parent1, parent2)
        offsprings.append(offspring1)
        offsprings.append(offspring2)
        
    def mutation(self, offspring):
        return self.DataList.mutation(offspring, self.MutationRate)
    
    def mutation_t(self, offspring, results):
        results.append(self.mutation(offspring))
    
    def create_newindividual(self, offspring, newindividuals):
        fitness = self.get_fitness(offspring)
        newindividual = (offspring, fitness)
        newindividuals.append(newindividual)

    def get_fitness(self, individual):
        try:
            return self.store[individual];
        except KeyError:
            self.store[individual] = self.CalculateFitness(individual)
            return self.store[individual]
        
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
                fitness = self.get_fitness(offspring)
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
    
    def run_thread(self, N = 2):
        if N < 2:
            print "number_parents(N) must be greater or equal to 2"
            sys.exit(1)
        self.timer = 0
        generation = 0
        while True:
            print "Generation:", generation
            start = timeit.default_timer()
            # selection
            bests = self.select(N)
            # crossover
            offsprings = []
            threads = []
            for i in range(len(bests)):
                for j in range(i+1, len(bests)):
                    t = threading.Thread(target = self.crossover_t, args = (bests[i][0], bests[j][0], offsprings))
                    t.start()
                    threads.append(t)
            join_all_threads(threads)
            # mutation
            mutated_offsprings = []
            threads = []
            for offspring in offsprings:
                t = threading.Thread(target = self.mutation_t, args = (offspring, mutated_offsprings))
                t.start()
                threads.append(t)
            join_all_threads(threads)
            # create new individual
            newindividuals = []
            threads = []
            for mutated in mutated_offsprings:
                t = threading.Thread(target = self.create_newindividual, args = (mutated, newindividuals))
                t.start()
                threads.append(t)
            join_all_threads(threads)
            # add the best to population
            print newindividuals
            best_new = newindividuals[0]
            for individual in newindividuals:
                if individual[1] > best_new[1]:
                    best_new = individual
            self.population.add(best_new)
            if self.timer == self.accuracy:
                break
            generation += 1
            stop = timeit.default_timer()
            print str(stop-start)+"s"
            
