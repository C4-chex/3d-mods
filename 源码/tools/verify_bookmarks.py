"""Exercise session bookmarks, then release test-owned VTK snapshots before exit."""
import gc
import time
import hashlib
import json
import traceback
from pathlib import Path
import numpy as np
import qt
import slicer
import vtk
from DICOMLib import DICOMUtils
from CT3DLib.CT3DExport import captureReviewImage, reviewDisplayParameters
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification" / "bookmarks"
OUT.mkdir(parents=True, exist_ok=True)
report = {"status": "running", "checks": []}
def check(name, condition):
    report["checks"].append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)
def pixels(volume):
    return hashlib.sha256(slicer.util.arrayFromVolume(volume).tobytes()).hexdigest()
def same(a,b):
    return np.allclose(a,b,atol=1e-6,rtol=1e-8)

def run_checks():
    try:
        slicer.util.selectModule("CT3D")
        w = slicer.modules.ct3d.widgetRepresentation().self()
        errors = []
        w.showError = lambda message: errors.append(str(message))
        check("empty_scene_add_disabled", not w.addBookmarkButton.enabled)
        source = Path(r"D:\dicom文件\dcm")
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.dcm")}
        with DICOMUtils.TemporaryDICOMDatabase(str(OUT / "database")) as database:
            DICOMUtils.importDicom(str(source), database, copyFiles=False)
            w.importFolder = str(source)
            w.populateSeries()
            valid = [i for i,q in enumerate(w.series) if not q["errors"] and len(q["files"])==20]
            w.seriesCombo.setCurrentIndex(valid[0]); w.onLoadSeries()
            check("actual_mr_loaded", w.currentVolume is not None and not errors)
            volume = w.currentVolume
            original = pixels(volume)
            window = slicer.util.mainWindow()
            available = window.screen().availableGeometry
            window.resize(min(1600, available.width() - 20), min(1000, available.height() - 40))
            slicer.util.setPythonConsoleVisible(False)
            for _ in range(5):
                slicer.app.processEvents()
                time.sleep(.02)
            w.onResetReviewViews()
            w.windowSpin.value = 650; w.levelSpin.value = 200; w.applyManualWindowLevel()
            w.smoothInterpolationCombo.setCurrentIndex(1)
            w.cropCheck.checked = True
            roi = w.roiNode(); roi.SetSize(70,80,90)
            camera = slicer.modules.cameras.logic().GetViewActiveCameraNode(slicer.app.layoutManager().threeDWidget(0).mrmlViewNode()).GetCamera()
            camera.Azimuth(27); camera.Elevation(11)
            w.bookmarkNote.text = "关注结构 A"
            count = slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLScalarVolumeNode")
            w.addBookmarkButton.click()
            check("button_created_bookmark", len(w._bookmarks)==1 and not errors)
            state = w._bookmarks[0]
            snapshots = list(state["slices"].values()) + [state[name] for name in ("display", "vr", "property", "roi") if state[name] is not None]
            check("snapshot_nodes_python_owned", all(node.GetReferenceCount() == 1 for node in snapshots))
            baseline = reviewDisplayParameters(w)
            check("bookmark_no_volume_copy", slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLScalarVolumeNode")==count)
            w.windowSpin.value = 100; w.applyManualWindowLevel()
            w.onFitROI(); w.onResetReviewViews()
            w.seriesCombo.setCurrentIndex(valid[1]); w.onLoadSeries()
            other = w.currentVolume
            check("second_series_loaded", other != volume and not errors)
            w.onBookmarkClicked(w.bookmarkList.item(0))
            check("list_click_restores_source", w.currentVolume==volume and not errors)
            restored = reviewDisplayParameters(w)
            check("window_level_restored", baseline["volume"]["window_level"]==restored["volume"]["window_level"])
            check("interpolation_restored", restored["slice_interpolation"]=="cubic")
            check("crosshair_restored", same(w.crosshairNode().GetCrosshairRAS(),state["ras"]))
            check("three_slice_matrices_restored", all(same(baseline["slice_views"][n]["slice_to_world_ras_matrix"],restored["slice_views"][n]["slice_to_world_ras_matrix"]) for n in ("Red","Yellow","Green")))
            report["zoom_comparison"] = {n: {"before": baseline["slice_views"][n]["field_of_view_mm"], "restored": restored["slice_views"][n]["field_of_view_mm"]} for n in ("Red","Yellow","Green")}
            check("three_slice_zoom_restored", all(same(baseline["slice_views"][n]["field_of_view_mm"],restored["slice_views"][n]["field_of_view_mm"]) for n in ("Red","Yellow","Green")))
            check("camera_restored", all(same(baseline["camera"][n], restored["camera"][n]) for n in baseline["camera"]))
            check("crop_restored", restored["volume_rendering"]["cropping_enabled"] and same(restored["volume_rendering"]["roi"]["size_object_mm"],[70,80,90]))
            captureReviewImage(str(OUT / "restored-four-views.png"))
            # Move all slices and locate a different interior point, then save another bookmark.
            point = list(state["ras"]); point[2] += 3
            w.crosshairNode().SetCrosshairRAS(point)
            slicer.vtkMRMLSliceNode.JumpAllSlices(slicer.mrmlScene,*point,slicer.vtkMRMLSliceNode.CenteredJumpSlice)
            w.bookmarkNote.text = "关注结构 B"; w.addBookmarkButton.click()
            check("second_bookmark_created", len(w._bookmarks)==2)
            w.onBookmarkClicked(w.bookmarkList.item(0))
            check("different_location_returned", same(w.crosshairNode().GetCrosshairRAS(),state["ras"]))
            transform = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLinearTransformNode")
            volume.SetAndObserveTransformNodeID(transform.GetID())
            try:
                w.restoreBookmark(state)
                rejected = False
            except RuntimeError:
                rejected = True
            check("changed_transform_rejected", rejected)
            volume.SetAndObserveTransformNodeID(None)
            check("source_pixels_unchanged", pixels(volume)==original)
            w.bookmarkList.setCurrentRow(1); w.removeBookmarkButton.click()
            check("delete_selected_only", len(w._bookmarks)==1)
            slicer.mrmlScene.RemoveNode(volume)
            try:
                w.restoreBookmark(state)
                rejected = False
            except RuntimeError:
                rejected = True
            check("removed_source_rejected", rejected)
            slicer.mrmlScene.Clear(0)
            check("scene_clear_discards_bookmarks", not w._bookmarks and not w.addBookmarkButton.enabled)
        check("source_dicom_unchanged", before=={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.dcm")})
        report["status"]="passed"
    except Exception:
        report["status"]="failed"
        report["errors"] = errors if 'errors' in locals() else []
        report["traceback"]=traceback.format_exc()

run_checks()
# Function-local VTK snapshots must die before the application shutdown checks.
gc.collect()
(OUT / "results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
slicer.app.exit(0 if report["status"]=="passed" else 1)
