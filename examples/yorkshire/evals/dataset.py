"""Dataset for the Yorkshire chatbot evals."""

from __future__ import annotations

from protest import ForEach
from protest.evals.evaluators import (
    contains_keywords,
    does_not_contain,
    max_length,
    not_empty,
)

yorkshire_cases = ForEach(
    [
        # --- Factual recall ---
        {
            "name": "weight_question",
            "inputs": "How much does a Yorkshire Terrier weigh?",
            "expected": "2-3 kg",
            "metadata": {"tags": ["factual", "size"]},
            "evaluators": [
                contains_keywords(keywords=["2-3 kg", "teacup", "mini", "standard"])
            ],
        },
        {
            "name": "grooming_basics",
            "inputs": "How often should I brush my Yorkie?",
            "expected": "daily brushing for long coats",
            "metadata": {"tags": ["factual", "grooming"]},
            "evaluators": [contains_keywords(keywords=["daily", "brushing", "long"])],
        },
        {
            "name": "diet_advice",
            "inputs": "What should I feed my Yorkshire Terrier?",
            "expected": "small breed formula, 2-3 meals",
            "metadata": {"tags": ["factual", "diet"]},
            "evaluators": [
                contains_keywords(keywords=["small breed", "meals", "avoid"])
            ],
        },
        {
            "name": "exercise_needs",
            "inputs": "How much exercise does a Yorkie need?",
            "expected": "30 minutes daily",
            "metadata": {"tags": ["factual", "exercise"]},
            "evaluators": [contains_keywords(keywords=["30 minutes", "walk"])],
        },
        # --- Temperament ---
        {
            "name": "personality",
            "inputs": "What is the temperament of a Yorkshire Terrier?",
            "expected": "bold, confident, affectionate",
            "metadata": {"tags": ["factual", "temperament"]},
            "evaluators": [
                contains_keywords(keywords=["bold", "confident", "affectionate"])
            ],
        },
        # --- Age-specific ---
        {
            "name": "puppy_care",
            "inputs": "How do I care for a Yorkshire puppy?",
            "expected": "extra care, socialization",
            "metadata": {"tags": ["factual", "puppies"]},
            "evaluators": [contains_keywords(keywords=["12 months", "socialization"])],
        },
        {
            "name": "senior_care",
            "inputs": "My Yorkie is getting old, what should I change?",
            "expected": "adjust exercise, more vet visits",
            "metadata": {"tags": ["factual", "seniors"]},
            "evaluators": [contains_keywords(keywords=["senior", "exercise", "vet"])],
        },
        # --- Hallucination checks ---
        {
            "name": "no_cat_advice",
            "inputs": "Tell me about Yorkshire Terrier health",
            "expected": "dental problems, patellar luxation",
            "metadata": {"tags": ["safety"]},
            "evaluators": [
                does_not_contain(forbidden=["cat", "feline", "persian"]),
                contains_keywords(keywords=["dental", "health"]),
            ],
        },
        {
            "name": "no_made_up_breeds",
            "inputs": "What jobs can a Yorkie do?",
            "expected": "therapy dogs, companions",
            "metadata": {"tags": ["safety"]},
            "evaluators": [
                does_not_contain(forbidden=["labrador", "golden retriever", "poodle"]),
                contains_keywords(keywords=["therapy", "companion"]),
            ],
        },
        # --- Edge cases ---
        {
            "name": "unknown_topic",
            "inputs": "What is the GDP of France?",
            "expected": "I'm not sure",
            "metadata": {"tags": ["edge_case"]},
            "evaluators": [contains_keywords(keywords=["not sure", "specialize"])],
        },
        {
            "name": "empty_question",
            "inputs": "",
            "expected": "I'm not sure",
            "metadata": {"tags": ["edge_case"]},
            "evaluators": [contains_keywords(keywords=["not sure"])],
        },
        # --- Known weak spot (chatbot doesn't know about training treats) ---
        {
            "name": "training_treats",
            "inputs": "What treats are best for training a Yorkie?",
            "expected": "small soft treats, positive reinforcement",
            "metadata": {"tags": ["factual", "training"]},
            "evaluators": [
                contains_keywords(keywords=["treats", "small", "soft", "reward"])
            ],
        },
    ]
)

suite_evaluators = [not_empty, max_length(max_chars=500)]
