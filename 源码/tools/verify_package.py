"""Run in a separate Slicer --testing process to verify release imports."""
import inspect
import json
import traceback
from pathlib import Path
import slicer

root = Path(__file__).resolve().parents[1]
result = {"checks": [], "status": "running"}
def check(name, condition):
    result["checks"].append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)
try:
    slicer.util.selectModule("CT3D")
    widget = slicer.modules.ct3d.widgetRepresentation().self()
    check("module_from_n2", Path(inspect.getfile(type(widget))).resolve() == root / "CT3D" / "CT3D.py")
    from CT3DLib import CT3DReview, CT3DExport, CT3DMeasurements, CT3DViewLabels, CT3DBookmarks
    import CT3DCTQuality
    for module in (CT3DReview, CT3DExport, CT3DMeasurements, CT3DViewLabels, CT3DBookmarks, CT3DCTQuality):
        check(module.__name__ + "_from_n2", root in Path(module.__file__).resolve().parents)
    check("quality_controls_available", hasattr(widget, "smoothInterpolationCombo") and hasattr(widget, "renderQualityCombo"))
    check("measurement_controls_available", hasattr(widget, "addMeasurementButton"))
    check("bookmark_controls_available", hasattr(widget, "addBookmarkButton") and not widget.addBookmarkButton.enabled)
    check("four_view_layout", slicer.app.layoutManager().layout == 501)
    check("no_source_volume_loaded", widget.currentVolume is None)
    result["status"] = "passed"
except Exception:
    result["status"] = "failed"
    result["traceback"] = traceback.format_exc()
finally:
    out = root / "verification"
    out.mkdir(exist_ok=True)
    (out / "package-results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    slicer.app.exit(0 if result["status"] == "passed" else 1)
