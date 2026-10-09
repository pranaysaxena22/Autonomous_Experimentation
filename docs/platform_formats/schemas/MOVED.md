# The schemas moved

The machine-readable schemas (JSON Schema) now live in the package, where programs read them while they run:

`cellpoc/formats/schemas/`

This folder keeps only this pointer. `check_formats.bat` checks the schemas where they live.