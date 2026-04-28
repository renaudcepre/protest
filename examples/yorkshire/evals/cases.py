"""Eval cases for the Yorkshire chatbot."""

from __future__ import annotations

from protest import ForEach
from protest.evals import EvalCase
from protest.evals.evaluators import (
    contains_keywords,
    does_not_contain,
    max_length,
    not_empty,
)

yorkshire_cases = ForEach(
    [
        # --- Factual recall ---
        EvalCase(
            name="weight_question",
            inputs="How much does a Yorkshire Terrier weigh?",
            expected="2-3 kg",
            tags=["factual", "size"],
            evaluators=[
                contains_keywords(keywords=["2-3 kg", "teacup", "mini", "standard"])
            ],
        ),
        EvalCase(
            name="grooming_basics",
            inputs="How often should I brush my Yorkie?",
            expected="daily brushing for long coats",
            tags=["factual", "grooming"],
            evaluators=[contains_keywords(keywords=["daily", "brushing", "long"])],
        ),
        EvalCase(
            name="diet_advice",
            inputs="What should I feed my Yorkshire Terrier?",
            expected="small breed formula, 2-3 meals",
            tags=["factual", "diet"],
            evaluators=[contains_keywords(keywords=["small breed", "meals", "avoid"])],
        ),
        EvalCase(
            name="exercise_needs",
            inputs="How much exercise does a Yorkie need?",
            expected="30 minutes daily",
            tags=["factual", "exercise"],
            evaluators=[contains_keywords(keywords=["30 minutes", "walk"])],
        ),
        # --- Temperament ---
        EvalCase(
            name="personality",
            inputs="What is the temperament of a Yorkshire Terrier?",
            expected="bold, confident, affectionate",
            tags=["factual", "temperament"],
            evaluators=[
                contains_keywords(keywords=["bold", "confident", "affectionate"])
            ],
        ),
        # --- Age-specific ---
        EvalCase(
            name="puppy_care",
            inputs="How do I care for a Yorkshire puppy?",
            expected="extra care, socialization",
            tags=["factual", "puppies"],
            evaluators=[contains_keywords(keywords=["12 months", "socialization"])],
        ),
        EvalCase(
            name="senior_care",
            inputs="My Yorkie is getting old, what should I change?",
            expected="adjust exercise, more vet visits",
            tags=["factual", "seniors"],
            evaluators=[contains_keywords(keywords=["senior", "exercise", "vet"])],
        ),
        # --- Hallucination checks ---
        EvalCase(
            name="no_cat_advice",
            inputs="Tell me about Yorkshire Terrier health",
            expected="dental problems, patellar luxation",
            tags=["safety"],
            evaluators=[
                does_not_contain(forbidden=["cat", "feline", "persian"]),
                contains_keywords(keywords=["dental", "health"]),
            ],
        ),
        EvalCase(
            name="no_made_up_breeds",
            inputs="What jobs can a Yorkie do?",
            expected="therapy dogs, companions",
            tags=["safety"],
            evaluators=[
                does_not_contain(forbidden=["labrador", "golden retriever", "poodle"]),
                contains_keywords(keywords=["therapy", "companion"]),
            ],
        ),
        # --- Edge cases ---
        EvalCase(
            name="unknown_topic",
            inputs="What is the GDP of France?",
            expected="I'm not sure",
            tags=["edge_case"],
            evaluators=[contains_keywords(keywords=["not sure", "specialize"])],
        ),
        EvalCase(
            name="empty_question",
            inputs="",
            expected="I'm not sure",
            tags=["edge_case"],
            evaluators=[contains_keywords(keywords=["not sure"])],
        ),
        # --- Known weak spot (chatbot doesn't know about training treats) ---
        EvalCase(
            name="training_treats",
            inputs="What treats are best for training a Yorkie?",
            expected="small soft treats, positive reinforcement",
            tags=["factual", "training"],
            evaluators=[
                contains_keywords(keywords=["treats", "small", "soft", "reward"])
            ],
        ),
    ]
)

suite_evaluators = [not_empty, max_length(max_chars=500)]
