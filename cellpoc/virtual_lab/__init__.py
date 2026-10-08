"""Public face of the virtual lab. Only VirtualLab is for general use; `oracle` is for scoring and checks."""
from .lab import VirtualLab

__all__ = ["VirtualLab"]
