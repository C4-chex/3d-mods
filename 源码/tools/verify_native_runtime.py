"""Run only in the packaged CT3D executable, without extra module paths."""
import ctypes
from ctypes import wintypes
import importlib
import inspect
import json
import os
from pathlib import Path
import sys
import time
import traceback

import slicer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification" / "native-runtime"
OUT.mkdir(parents=True, exist_ok=True)
EXPECTED = Path(os.environ.get("CT3D_ACCEPTANCE_RUNTIME", str(ROOT / "runtime"))).resolve()
report = {"status": "running", "checks": [], "runtime": str(EXPECTED)}


def check(name, condition, **details):
    report["checks"].append({"name": name, "passed": bool(condition), **details})
    if not condition:
        raise AssertionError(name)


def inside(path):
    return Path(path).resolve().is_relative_to(EXPECTED)


def loaded_dlls():
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    process = kernel.GetCurrentProcess()
    modules = (wintypes.HMODULE * 4096)()
    needed = wintypes.DWORD()
    psapi.EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    if not psapi.EnumProcessModules(process, modules, ctypes.sizeof(modules), ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    if needed.value > ctypes.sizeof(modules):
        raise RuntimeError("Module inventory buffer too small")
    paths = []
    for module in modules[:needed.value // ctypes.sizeof(wintypes.HMODULE)]:
        buffer = ctypes.create_unicode_buffer(32768)
        if psapi.GetModuleFileNameExW(process, module, buffer, len(buffer)):
            paths.append(buffer.value)
    return paths


try:
    slicer.util.selectModule("CT3D")
    widget = slicer.modules.ct3d.widgetRepresentation().self()
    check("application_identity", slicer.app.mainApplicationName == "CT3D", actual=slicer.app.mainApplicationName, testing_profile=slicer.app.applicationName)
    check("pinned_kernel_provenance", slicer.app.repositoryRevision == "a5df71450f1d27d87dc1c513bc25c57c702bf71d", actual=slicer.app.repositoryRevision)
    check("ct3d_archive_provenance", slicer.app.mainApplicationRepositoryRevision == "ct3d-source-0.1.0", actual=slicer.app.mainApplicationRepositoryRevision)
    check("numeric_local_scene_revision", slicer.app.mainApplicationRevision == "20261011", actual=slicer.app.mainApplicationRevision)
    check("main_executable_inside_package", inside(slicer.app.applicationFilePath()), actual=slicer.app.applicationFilePath())
    check("ct3d_module_installed", inside(inspect.getfile(type(widget))))
    libraries = ("CT3DReview", "CT3DExport", "CT3DMeasurements", "CT3DViewLabels", "CT3DBookmarks", "CT3DPaths", "CT3DCTQuality")
    for name in libraries:
        module = importlib.import_module("CT3DLib." + name)
        check("installed_" + name, inside(module.__file__), actual=module.__file__)
    for name in ("dicom", "volumerendering", "segmenteditor", "screencapture", "markups", "transforms", "cropvolume", "data", "volumes"):
        check("required_module_" + name, getattr(slicer.modules, name, None) is not None)
    for name in ("numpy", "pydicom", "vtk", "ctk"):
        module = importlib.import_module(name)
        check("bundled_dependency_" + name, inside(module.__file__), actual=module.__file__)
    from CT3DLib.CT3DPaths import workspaceRoot
    check("workspace_override", Path(workspaceRoot()).resolve() == ROOT)
    previous_workspace = os.environ.pop("CT3D_WORKSPACE_ROOT", None)
    try:
        check("installed_user_workspace_default", Path(workspaceRoot()).resolve() == (Path.home() / "CT3D").resolve())
    finally:
        if previous_workspace is not None:
            os.environ["CT3D_WORKSPACE_ROOT"] = previous_workspace
    check("four_view_layout", slicer.app.layoutManager().layout == 501)
    check("clean_initial_state", widget.currentVolume is None and not widget.addBookmarkButton.enabled)
    window = slicer.util.mainWindow()
    available = window.screen().availableGeometry
    window.resize(min(1500, available.width() - 20), min(950, available.height() - 40))
    window.show()
    for _ in range(5):
        slicer.app.processEvents()
        time.sleep(.02)
    dock = slicer.util.findChild(window, "PanelDockWidget")
    ratio = dock.width / window.centralWidget().width if dock else 0
    check("default_panel_ratio", abs(ratio - .618) < .025, actual=ratio)
    check("native_window_capture", window.grab().save(str(OUT / "native-window-empty.png")))
    log_model = slicer.app.errorLogModel()
    report["startup_log_descriptions"] = [log_model.logEntryDescription(i) for i in range(log_model.logEntryCount())]
    paths = loaded_dlls()
    report["loaded_modules"] = paths
    external_roots = (Path(r"D:\3dslicer"), ROOT.parent / "in-need", ROOT / "build-support", ROOT / "b")
    unexpected = [path for path in paths if any(Path(path).resolve().is_relative_to(root.resolve()) for root in external_roots)]
    check("no_external_slicer_or_build_library", not unexpected, unexpected=unexpected)
    external_python = [path for path in sys.path if path and "3dslicer" in path.lower() and not inside(path)]
    check("no_external_slicer_python_path", not external_python, unexpected=external_python)
    report["status"] = "passed"
except Exception:
    report["status"] = "failed"
    report["traceback"] = traceback.format_exc()
finally:
    (OUT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    slicer.app.exit(0 if report["status"] == "passed" else 1)
