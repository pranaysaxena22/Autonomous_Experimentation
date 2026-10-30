"""Menu page: Reports (the dashboard's page, unchanged)."""
from cellpoc.dashboard import platform_reports
from cellpoc.shell import context

record, path = context.load_record()
platform_reports.render(record, path, client=not context.developer())
