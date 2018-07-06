#!/usr/bin/python3 
from random import randint
from threading import Thread
from multiprocessing import Process, Queue, Manager
import timeit
from sys import exit
"""
Classes and methods for multiprocessing genetic algorithm.
To use this tool, the target data stucture class should contains 3 methods which are RandomIndividual(), crossover() and mutation().
The fitness score must be numeric.
If individual is a class object, the class need to have two additional methods (__hash__ and __eq__).
"""
# wait for all threads in a thread list
def join_all_threads(threads):
    for t in threads:
        t.join()

# wait for all processes in a process list
def join_all_processes(processes):
    for p in processes:
        p.join()

# change queue into a list
def Queue_to_list(queue):
    # put 'None' at the end of the queue
    queue.put(None)
    l = []
    # iterator stops when meet 'None'
    for item in iter(queue.get, None):
        l.append(item)
    return l
        
# Population class that is composed to CVGenetic class
class Population(object):
    def __init__(self, size):
        self.size = size
        self.individuals = []
        self.sorted = False
    # add new individual to population
    def add(self, newindividual):
        if len(self.individuals) < self.size:
            self.individuals.append(newindividual)
            self.sorted = False
        else:
            least = self.get_least_index()
            if self.individuals[self.size-1][1] < newindividual[1]:
                self.individuals[self.size-1] = newindividual
            self.sorted = False
    
    # Get the index of individual with least fitness
    def get_least_index(self):
        if not self.sorted:
            self.sort()
        return len(self.individuals) - 1
    
    # Get N best fitness individual from population
    def get_best(self, N):
        if not self.sorted:
            self.sort()
        return self.individuals[:N]
    
    # sort individuals according to thier fitness
    def sort(self):
        if not self.sorted:
            self.individuals.sort(key = lambda t: t[1], reverse = True)
            self.sorted = True
            
    # Check existance of individual (Not used)
    def existed(self, i):
        for individual in self.individuals:
            if individual[0] == i:
                return True
        return False

# TODO - Make a new class GeneticConfig and pass it into initialization of CVGenetic.
class CVGenetic(object):
    def __init__(self, population_size, DataList, CalculateFitness, accuracy = 5, MutationRate = 0.2, output = True, CrossOverDimension = None):
        print("Initializing Genetic Calculator")
        # Config
        if CrossOverDimension is None:
            self.CrossOverDimension = (0, DataList.length())
        else:
            self.CrossOverDimension = CrossOverDimension
        start = timeit.default_timer()
        self.population = Population(population_size)
        self.DataList = DataList
        self.accuracy = accuracy
        self.best = float("-inf")
        self.CalculateFitness = CalculateFitness
        self.output = output
        # Config End
        manager = Manager()
        self.store = manager.dict()
        newindividuals = Queue()
        processes = []
        # initilize population with random individual
        for i in range(population_size):
            p = Process(target = self.create_newindividual, args = (DataList.RandomIndividual(), newindividuals))
            p.start()
            processes.append(p)
        join_all_processes(processes)
        newindividuals = Queue_to_list(newindividuals)
        for individual in newindividuals:
            self.population.add(individual)
        self.timer = 0
        self.MutationRate = MutationRate
        stop = timeit.default_timer()
        if self.output:
            print(str(stop - start)+"s")
            print(self.store)
        
    def select(self, N):
        bests = self.population.get_best(N)
        if self.best == bests[0][0]:
            self.timer += 1
        else:
            self.best = bests[0][0]
            self.timer = 0
        if self.output:
            print(self.best)
        return bests
    # wait for all processes in a process list
    def crossover(self, parent1, parent2):
        # Dimension = self.DataList.crossover_dimension()
        # return self.DataList.crossover(parent1, parent2, randint(Dimension[0], Dimension[1]))
        return self.DataList.crossover(parent1, parent2)
    
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
        newindividuals.put(newindividual)

    # calculate the fitness of the individual
    # when there is a duplicated processes maintain one and kill the rest
    def get_fitness(self, individual):
        try:
            if (self.store[individual]):
                exit(0)
        except KeyError:
            try:
                self.store[individual] = self.CalculateFitness(individual)
                return self.store[individual]
            except KeyError:
                exit(0)
                    
    # NOTE - this is slow, run_thread() is recommanded
    def run(self, N = 2):
        if N < 2:
            print("number_parents(N) must be greater or equal to 2")
            sys.exit(1)
        self.timer = 0
        generation = 0
        while True:
            if self.output:
                print("Generation:", generation)
            # selection
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
            if self.output:
                print(newindividuals)
            for individual in newindividuals:
                if individual[1] > best_new[1]:
                    best_new = individual
            self.population.add(best_new)
            if self.timer == self.accuracy:
                break
            generation += 1

    # run it and the best ID will be store in self.best
    def run_thread(self, N = 3):
        if N < 2:
            print("number_parents(N) must be greater or equal to 2")
            sys.exit(1)
        if N > self.population.size:
            print("number_parents(N) can't be greater than population")
        self.timer = 0
        generation = 0
        while True:
            if self.output:
                print("Generation:", generation)
            start = timeit.default_timer()
            # selection
            bests = self.select(N)
            # crossover
            offsprings = []
            threads = []
            for i in range(len(bests)):
                for j in range(i+1, len(bests)):
                    t = Thread(target = self.crossover_t, args = (bests[i][0], bests[j][0], offsprings))
                    t.start()
                    threads.append(t)
            join_all_threads(threads)
            # mutation
            mutated_offsprings = []
            threads = []
            for offspring in offsprings:
                t = Thread(target = self.mutation_t, args = (offspring, mutated_offsprings))
                t.start()
                threads.append(t)
            join_all_threads(threads)
            # create new individual
            newindividuals = Queue()
            processes = []
            for mutated in mutated_offsprings:
                p = Process(target = self.create_newindividual, args = (mutated, newindividuals))
                p.start()
                processes.append(p)
            join_all_processes(processes)
            newindividuals = Queue_to_list(newindividuals)
            if self.output:
                print(newindividuals)
            # add the best to population
            # print(newindividuals)
            if len(newindividuals) is not 0:
                for individual in newindividuals:
                    self.population.add(individual)
                    # if individual[1] > best_new[1]:
                    #     best_new = individual
                # self.population.add(best_new)
            if self.timer == self.accuracy:
                break
            generation += 1
            stop = timeit.default_timer()
            if self.output:
                print(str(stop-start)+"s")
            
