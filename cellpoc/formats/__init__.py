"""Data files that programs read while they run: the JSON Schemas (schemas/) and the bundled example setup,
layout and experiment table (examples/). They live in the package so no program depends on a documentation folder.

The master copies are here. docs/platform_formats/ keeps identical copies of the four example files (the other examples refer to
them by relative path) and a pointer for the schemas; check_formats.bat fails if a docs copy differs from the package copy.
"""
