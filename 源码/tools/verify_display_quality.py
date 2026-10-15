"""Real MR display quality checks; preserve source voxels and physical geometry."""
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
OUT = ROOT / "verification" / "display-quality-20261006"
OUT.mkdir(parents=True, exist_ok=True)
report = {"status": "running", "checks": []}

def check(name, result, **details):
    report["checks"].append({"name": name, "passed": bool(result), **details})
    if not result:
        raise AssertionError(name)

def digest(array):
    return hashlib.sha256(array.tobytes()).hexdigest()

def layer():
    return slicer.app.layoutManager().sliceWidget("Yellow").sliceLogic().GetBackgroundLayer()

try:
    slicer.util.selectModule("CT3D")
    w = slicer.modules.ct3d.widgetRepresentation().self()
    errors=[]
    w.showError=lambda message:errors.append(str(message))
    source = Path(r"D:\dicom文件\dcm")
    source_before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.dcm")}
    with DICOMUtils.TemporaryDICOMDatabase(str(OUT / "database")) as database:
        DICOMUtils.importDicom(str(source), database, copyFiles=False)
        w.importFolder=str(source)
        w.populateSeries()
        valid=[i for i,q in enumerate(w.series) if not q["errors"] and len(q["files"])==20]
        w.seriesCombo.setCurrentIndex(valid[0])
        w.onLoadSeries()
        check("real_mr_loaded", w.nodeIsPresent(w.currentVolume) and not errors, errors=errors)
        volume=w.currentVolume
        source_hash=digest(slicer.util.arrayFromVolume(volume))
        spacing=list(volume.GetSpacing())
        matrix=vtk.vtkMatrix4x4();volume.GetIJKToRASMatrix(matrix)
        geometry=[matrix.GetElement(i,j) for i in range(4) for j in range(4)]
        count=slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLScalarVolumeNode")
        slicer.util.mainWindow().resize(1600,1000)
        slicer.util.setPythonConsoleVisible(False)
        w.onResetReviewViews()
        w.interpolateCheck.checked=True
        w.smoothInterpolationCombo.setCurrentIndex(0)
        slicer.app.processEvents()
        layer().GetReslice().Update()
        baseline=vtk.util.numpy_support.vtk_to_numpy(layer().GetReslice().GetOutput().GetPointData().GetScalars()).copy()
        captureReviewImage(str(OUT / "linear-normal.png"))
        w.smoothInterpolationCombo.setCurrentIndex(1)
        slicer.app.processEvents()
        modes={n:slicer.app.layoutManager().sliceWidget(n).sliceLogic().GetBackgroundLayer().GetReslice().GetInterpolationMode() for n in ("Red","Yellow","Green")}
        check("cubic_active_in_all_reslicers", all(v==vtk.VTK_RESLICE_CUBIC for v in modes.values()), modes=modes,
              configured=layer().GetInterpolationMode(), selected=w.smoothInterpolationCombo.currentIndex,
              attribute=volume.GetDisplayNode().GetAttribute("CT3D.SmoothInterpolation"), enabled=volume.GetDisplayNode().GetInterpolate())
        layer().GetReslice().Update()
        cubic=vtk.util.numpy_support.vtk_to_numpy(layer().GetReslice().GetOutput().GetPointData().GetScalars()).copy()
        check("coronal_rendered_pixels_change", baseline.shape==cubic.shape and not np.array_equal(baseline,cubic))
        captureReviewImage(str(OUT / "cubic-normal.png"))
        w.onResetReviewViews()
        w.applyWindowLevel(400,40)
        check("cubic_survives_reset_and_window_change", layer().GetReslice().GetInterpolationMode()==vtk.VTK_RESLICE_CUBIC)
        w.interpolateCheck.checked=False
        check("nearest_original_sampling_available", layer().GetReslice().GetInterpolationMode()==vtk.VTK_RESLICE_NEAREST)
        w.interpolateCheck.checked=True
        check("reenabling_restores_cubic", layer().GetReslice().GetInterpolationMode()==vtk.VTK_RESLICE_CUBIC)
        w.renderQualityCombo.setCurrentIndex(2)
        w.renderSmoothingCheck.checked=True
        node=slicer.app.layoutManager().threeDWidget(0).mrmlViewNode()
        check("maximum_render_quality", node.GetVolumeRenderingQuality()==2)
        check("render_surface_smoothing", node.GetVolumeRenderingSurfaceSmoothing())
        w.applyAutoWindowLevel()
        slicer.app.processEvents()
        captureReviewImage(str(OUT / "cubic-maximum-smooth.png"))
        payload=reviewDisplayParameters(w)
        (OUT / "display-parameters.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        check("export_records_actual_modes", payload["slice_interpolation"]=="cubic" and payload["render_quality_mode"]==2 and payload["render_surface_smoothing"])
        w.renderQualityCombo.setCurrentIndex(1)
        w.renderSmoothingCheck.checked=False
        check("normal_render_quality_restored", node.GetVolumeRenderingQuality()==1 and not node.GetVolumeRenderingSurfaceSmoothing())
        w.seriesCombo.setCurrentIndex(valid[1]);w.onLoadSeries()
        check("new_series_defaults_linear", w.smoothInterpolationCombo.currentIndex==0)
        w.seriesCombo.setCurrentIndex(valid[0]);w.onLoadSeries()
        check("return_restores_series_cubic_setting", w.smoothInterpolationCombo.currentIndex==1 and layer().GetReslice().GetInterpolationMode()==vtk.VTK_RESLICE_CUBIC)
        matrix=vtk.vtkMatrix4x4();volume.GetIJKToRASMatrix(matrix)
        check("source_voxels_unchanged", digest(slicer.util.arrayFromVolume(volume))==source_hash)
        check("source_geometry_unchanged", spacing==list(volume.GetSpacing()) and geometry==[matrix.GetElement(i,j) for i in range(4) for j in range(4)])
        check("no_quality_volume_copy", slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLScalarVolumeNode")==count+1)
    check("source_dicom_unchanged", source_before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.dcm")})
    report["status"]="passed"
except Exception:
    report["status"]="failed"
    report["traceback"]=traceback.format_exc()
finally:
    (OUT / "results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    slicer.app.exit(0 if report["status"]=="passed" else 1)
