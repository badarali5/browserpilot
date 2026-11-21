import random

from algorithms.csp_solver import CSPSolver
from algorithms.genetic_algorithm import GeneticAlgorithm
from algorithms.search_algorithms import astar, bfs
from algorithms.ui_state_graph import UIStateGraph


def make_search_graph():
    graph = UIStateGraph()
    states = [
        {"title": "Start", "url": "/start", "visible_text": "Start"},
        {"title": "A", "url": "/a", "visible_text": "A"},
        {"title": "B", "url": "/b", "visible_text": "B"},
        {"title": "Goal", "url": "/goal", "visible_text": "Submit complete"},
    ]
    ids = [graph.add_state(state) for state in states]
    graph.initial_states = [ids[0]]
    graph.add_transition(ids[0], {"tool": "navigate", "arguments": {"url": "/a"}}, ids[1], 1)
    graph.add_transition(ids[0], {"tool": "navigate", "arguments": {"url": "/b"}}, ids[2], 5)
    graph.add_transition(ids[1], {"tool": "navigate", "arguments": {"url": "/goal"}}, ids[3], 1)
    graph.add_transition(ids[2], {"tool": "navigate", "arguments": {"url": "/goal"}}, ids[3], 1)
    return graph, ids


def test_bfs_returns_minimum_hop_path_and_metrics():
    graph, ids = make_search_graph()
    result = bfs(graph, "complete")
    assert result["goal_reachable"] is True
    assert result["path_length"] == 2
    assert result["path"] == [ids[0], ids[1], ids[3]]
    assert result["nodes_explored"] <= len(graph.states)


def test_astar_uses_weighted_cost_and_handles_unreachable_goal():
    graph, ids = make_search_graph()
    graph.states[ids[3]]
    result = astar(graph, lambda state: state.state_id == ids[3])
    assert result["goal_reachable"] is True
    assert result["total_cost"] == 2

    unreachable = astar(graph, "state that does not exist")
    assert unreachable["goal_reachable"] is False
    assert unreachable["path"] == []


def test_csp_valid_forward_checking_and_invalid_tags():
    domains = {
        "username": ["ada", "lee"],
        "email": ["ada@example.com", "lee@example.com"],
        "password": ["Password1", "Secure2"],
        "confirm_password": ["Password1", "Secure2"],
    }

    def not_empty(payload):
        return all(str(payload[name]).strip() for name in payload)

    def email_format(payload):
        if "email" not in payload:
            return True
        return "@" in str(payload["email"])

    def password_match(payload):
        if "password" not in payload or "confirm_password" not in payload:
            return True
        return payload.get("password") == payload.get("confirm_password")

    solver = CSPSolver(
        list(domains),
        domains,
        [not_empty, email_format, password_match],
    )
    valid = solver.solve(limit=5)
    assert valid
    assert all(password_match(payload) for payload in valid)

    invalid = solver.generate_invalid(
        {"username": "ada", "email": "ada@example.com",
         "password": "Password1", "confirm_password": "Password1"},
        limit=10,
    )
    assert invalid
    assert all(item["violated_constraints"] for item in invalid)


def test_ga_seeded_run_improves_initial_generation():
    seed = 8128

    def initializer(randomizer):
        return [randomizer.randint(0, 9) for _ in range(12)]

    def fitness(individual):
        return len(set(individual)) + (5 if 7 in individual else 0)

    def crossover(left, right, randomizer):
        point = randomizer.randint(1, len(left) - 1)
        return left[:point] + right[point:]

    def mutate(individual, randomizer):
        copy = individual[:]
        copy[randomizer.randrange(len(copy))] = randomizer.randint(0, 9)
        return copy

    ga = GeneticAlgorithm(
        initializer,
        fitness,
        crossover,
        mutate,
        population_size=30,
        generations=15,
        mutation_rate=0.25,
        elitism=3,
        seed=seed,
    )
    result = ga.run()
    assert result["seed"] == seed
    assert result["best_fitness"] >= result["initial_best"]
    assert result["fitness_history"][-1]["best"] >= result["fitness_history"][0]["best"]
