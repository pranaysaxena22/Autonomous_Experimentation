"""Menu page: 3D replay (the dashboard's page; inside the app its own title band is hidden, the app's frame is the header)."""
from cellpoc.dashboard import platform_replay
from cellpoc.shell import context

record, path = context.load_record()
platform_replay.render(record, path, embedded=True)
