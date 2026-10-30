"""Menu page: Data and model (the dashboard's page, unchanged)."""
from cellpoc.dashboard import platform_data
from cellpoc.shell import context

record, path = context.load_record()
platform_data.render(record)
