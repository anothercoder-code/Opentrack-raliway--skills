"""Public pure bytes scenario entry; outer tools bind run/Train scope."""
from .core import plan, ScenarioError

def generate_from_spec(courses_bytes,spec):
    return plan(courses_bytes,spec)
