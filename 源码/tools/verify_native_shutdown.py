"""Exit with live image/bookmarks; the harness requires leak-free process exit."""
import hashlib
import json
from pathlib import Path
import traceback
import slicer
from DICOMLib import DICOMUtils

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification/native-shutdown"
OUT.mkdir(parents=True, exist_ok=True)
report = {"status": "running", "checks": []}


def check(name, condition):
    report["checks"].append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)


def run_checks():
    source = Path(r"D:\dicom文件\dcm")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.dcm")}
    slicer.util.selectModule("CT3D")
    widget = slicer.modules.ct3d.widgetRepresentation().self()
    errors = []
    widget.showError = lambda message: errors.append(str(message))
    with DICOMUtils.TemporaryDICOMDatabase(str(OUT / "database")) as database:
        DICOMUtils.importDicom(str(source), database, copyFiles=False)
        widget.importFolder = str(source)
        widget.populateSeries()
        valid = [i for i, quality in enumerate(widget.series) if not quality["errors"] and len(quality["files"]) == 20]
        check("usable_mr_available", bool(valid))
        widget.seriesCombo.setCurrentIndex(valid[0])
        widget.onLoadSeries()
        check("mr_loaded_without_error", widget.currentVolume is not None and not errors)
        widget.onResetReviewViews()
        for note in ("退出清理 A", "退出清理 B"):
            widget.bookmarkNote.text = note
            widget.onAddBookmark()
        check("active_bookmarks_remain_before_exit", len(widget._bookmarks) == 2 and not errors)
        snapshots = [node for state in widget._bookmarks for node in state["slices"].values()]
        check("active_snapshots_have_one_owner", all(node.GetReferenceCount() == 1 for node in snapshots))
        check("image_still_in_scene_before_exit", slicer.mrmlScene.IsNodePresent(widget.currentVolume) > 0)
    check("original_mr_files_unchanged", before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.dcm")})


try:
    run_checks()
    report["status"] = "passed"
except Exception:
    report["status"] = "failed"
    report["traceback"] = traceback.format_exc()
finally:
    (OUT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Deliberately leave the scene and widget bookmarks populated. Product
    # shutdown cleanup, rather than test scene clearing, must release them.
    slicer.app.exit(0 if report["status"] == "passed" else 1)
