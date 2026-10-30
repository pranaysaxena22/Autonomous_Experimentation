"""Menu page: About and limits (the dashboard's What this shows page in the developer view; a plain summary of the same limits in the client view)."""
from cellpoc.dashboard import about, client_about
from cellpoc.shell import context

record, path = context.load_record()
if context.developer():
    about.render(record)
else:
    client_about.render(record)