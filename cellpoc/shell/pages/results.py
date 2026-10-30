"""Menu page: Results at a glance: the run told as results a client cares about, with charts."""
from cellpoc.dashboard import client_results
from cellpoc.shell import context

record, path = context.load_record()
client_results.render(record, path)
