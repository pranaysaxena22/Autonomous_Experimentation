"""The shared setup logic: reading, saving and checking a study setup, with plain-English messages.

The setup app only shows what this package decides; the health check uses the same functions, so both apply the same rules.
It imports no other part of the platform and needs no network.
"""
from .files import (PROJECT_ROOT, LoadResult, SetupFileError, example_setup_path, fingerprint, list_layouts, load_setup,
                    path_is_safe, resolve_reference, save_setup)
from .messages import CATALOGUE, Rule
from .problems import SCREENS, SETUP_FILE_SCREEN, Problem, has_errors
from .units import UNITS, allowed_symbols
from .validate import problems_at, validate
from .versions import PROGRAM_VERSION, SETUP_FORMAT_VERSION, FormatSupport

__all__ = ["CATALOGUE", "FormatSupport", "LoadResult", "PROGRAM_VERSION", "PROJECT_ROOT", "Problem", "Rule", "SCREENS",
           "SETUP_FILE_SCREEN", "SETUP_FORMAT_VERSION", "SetupFileError", "UNITS", "allowed_symbols", "example_setup_path",
           "fingerprint", "has_errors", "list_layouts", "load_setup", "path_is_safe", "problems_at", "resolve_reference",
           "save_setup", "validate"]
