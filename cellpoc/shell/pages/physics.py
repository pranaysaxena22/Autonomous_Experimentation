"""Menu page: Physics (MuJoCo): the run played by an arm in a MuJoCo model of the cell, with the physics checks."""
from cellpoc.dashboard import physics_view
from cellpoc.shell import context

record, path = context.load_record()
physics_view.render(record, path)