"""Reusable genetic algorithm for evolving browser test sequences and payloads."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from typing import Any, Generic, TypeVar


T = TypeVar("T")


class GeneticAlgorithm(Generic[T]):
    def __init__(
        self,
        initializer: Callable[[random.Random], T],
        fitness: Callable[[T], float],
        crossover: Callable[[T, T, random.Random], T],
        mutate: Callable[[T, random.Random], T],
        *,
        population_size: int = 30,
        generations: int = 20,
        mutation_rate: float = 0.15,
        elitism: int = 2,
        seed: int = 0,
    ) -> None:
        if population_size < 2 or generations < 1:
            raise ValueError("population_size and generations must be positive.")
        if not 0 <= mutation_rate <= 1:
            raise ValueError("mutation_rate must be between 0 and 1.")
        self.initializer = initializer
        self.fitness = fitness
        self.crossover = crossover
        self.mutate = mutate
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.elitism = max(0, elitism)
        self.seed = seed
        self.random = random.Random(seed)

    def run(self) -> dict[str, Any]:
        population = [self.initializer(self.random) for _ in range(self.population_size)]
        initial_scores = [self.fitness(individual) for individual in population]
        history = [{"generation": 0, "best": max(initial_scores),
                    "mean": sum(initial_scores) / len(initial_scores)}]

        for generation in range(1, self.generations + 1):
            ranked = sorted(
                population,
                key=lambda individual: self.fitness(individual),
                reverse=True,
            )
            elite_count = min(self.elitism, len(ranked))
            next_population = ranked[:elite_count]

            while len(next_population) < self.population_size:
                tournament = self.random.sample(ranked, k=min(4, len(ranked)))
                parent_a = max(tournament, key=self.fitness)
                tournament = self.random.sample(ranked, k=min(4, len(ranked)))
                parent_b = max(tournament, key=self.fitness)
                child = self.crossover(parent_a, parent_b, self.random)
                if self.random.random() < self.mutation_rate:
                    child = self.mutate(child, self.random)
                next_population.append(child)

            population = next_population
            scores = [self.fitness(individual) for individual in population]
            history.append({
                "generation": generation,
                "best": max(scores),
                "mean": sum(scores) / len(scores),
            })

        scores = [self.fitness(individual) for individual in population]
        best_index = max(range(len(population)), key=scores.__getitem__)
        return {
            "best": population[best_index],
            "best_fitness": scores[best_index],
            "initial_best": max(initial_scores),
            "initial_mean": sum(initial_scores) / len(initial_scores),
            "fitness_history": history,
            "seed": self.seed,
            "config": {
                "population_size": self.population_size,
                "generations": self.generations,
                "mutation_rate": self.mutation_rate,
                "elitism": self.elitism,
            },
        }
