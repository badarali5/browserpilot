"""Reproducible Milestone 4 synthetic benchmark."""

from __future__ import annotations

import random

from genetic_algorithm import GeneticAlgorithm
from search_algorithms import astar, bfs
from ui_state_graph import UIStateGraph


def make_grid(seed: int = 1729) -> UIStateGraph:
    graph = UIStateGraph()
    randomizer = random.Random(seed)
    observations = [
        {"title": f"State {index}", "url": f"/state/{index}", "visible_text": str(index)}
        for index in range(30)
    ]
    for observation in observations:
        graph.add_state(observation)
    graph.initial_states = [next(iter(graph.states))]

    ids = list(graph.states)
    for index, source in enumerate(ids):
        for offset in (1, 2, 5):
            target_index = index + offset
            if target_index < len(ids):
                target = ids[target_index]
                graph.add_transition(
                    source,
                    {"tool": "navigate", "arguments": {"url": f"/state/{target_index}"}},
                    target,
                    float(randomizer.randint(1, 8)),
                )
    return graph


def benchmark(seed: int = 1729) -> dict[str, object]:
    graph = make_grid(seed)
    target = list(graph.states)[-1]

    def goal(state):
        return state.state_id == target

    bfs_result = bfs(graph, goal)
    graph.visited.clear()
    astar_result = astar(
        graph,
        goal,
        heuristic=lambda state: 0.0,
    )

    def initializer(randomizer):
        return [randomizer.randint(0, 29) for _ in range(20)]

    def fitness(sequence):
        covered = set(sequence)
        return len(covered) + (0.25 if target in covered else 0)

    def crossover(left, right, randomizer):
        point = randomizer.randint(1, len(left) - 1)
        return left[:point] + right[point:]

    def mutate(sequence, randomizer):
        copy = sequence[:]
        copy[randomizer.randrange(len(copy))] = randomizer.randint(0, 29)
        return copy

    ga = GeneticAlgorithm(
        initializer, fitness, crossover, mutate,
        population_size=30, generations=20, mutation_rate=0.15,
        elitism=2, seed=seed,
    )
    ga_result = ga.run()
    return {
        "seed": seed,
        "synthetic_graph_states": len(graph.states),
        "bfs": bfs_result,
        "a_star": astar_result,
        "ga": {
            "initial_best": ga_result["initial_best"],
            "best_fitness": ga_result["best_fitness"],
            "fitness_history": ga_result["fitness_history"],
            "config": ga_result["config"],
        },
    }


if __name__ == "__main__":
    import json
    print(json.dumps(benchmark(), indent=2, sort_keys=True))
