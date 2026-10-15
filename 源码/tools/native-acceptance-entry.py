"""Run one acceptance script with strict leak exit status and scoped globals."""
import gc
import os
import runpy
import vtk

# The harness uses VTK's dashboard mode to send diagnostics to stderr rather
# than modal dialogs. Leaks must still fail the actual process exit.
vtk.vtkDebugLeaks.SetExitError(1)


def run_case():
    runpy.run_path(os.environ["CT3D_ACCEPTANCE_SCRIPT"], run_name="__main__")


run_case()
gc.collect()
