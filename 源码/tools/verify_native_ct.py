"""End-to-end CT check inside Slicer; source DICOM is imported read-only."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import slicer
import vtk
from DICOMLib import DICOMUtils

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = Path(os.environ.get("CT3D_CT_QA_SAMPLE", str(ROOT.parent / "ct part" / "source-dcm_qa_ct")))
SOURCE = SAMPLE / "In"
REFERENCE = SAMPLE / "Ref" / "1A_TRAUMA_PLAIN_HEAD_DM_Head_202.nii"
PREFLIGHT = os.environ.get("CT3D_TEST_SCRIPT_PREFLIGHT") == "1"
OUT = ROOT / "verification" / ("test-script-preflight-ct" if PREFLIGHT else "native-ct")
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "ct-workflow.json"
result = {"status": "running", "checks": [], "slicer_version": slicer.app.applicationVersion,
          "scope": "test script preflight in existing development app" if PREFLIGHT else "native executable CT acceptance"}


def check(name, passed, **details):
    result["checks"].append({"name": name, "passed": bool(passed), **details})
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if not passed:
        raise AssertionError(name)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


source_files = sorted(path for path in SOURCE.rglob("*") if path.is_file() and path.name != "DICOMDIR")
before = {str(path): sha256(path) for path in source_files}
exit_code = 1
try:
    slicer.util.selectModule("CT3D")
    widget = slicer.modules.ct3d.widgetRepresentation().self()
    with DICOMUtils.TemporaryDICOMDatabase(str(OUT / "temporary-ct-database")) as database:
        DICOMUtils.importDicom(str(SOURCE), database, copyFiles=False)
        widget.importFolder = str(SOURCE.resolve())
        widget.populateSeries()
        choices = [(index, info) for index, info in enumerate(widget.series)
                   if info["modality"] == "CT" and info["description"] == "STD BRAIN 1MM, iDose"
                   and len(info["files"]) == 140]
        check("sample_series_indexed", len(choices) == 1, ct_series_count=sum(
            info["modality"] == "CT" for info in widget.series))
        index, info = choices[0]
        check("standard_implicit_hu_accepted", info["huEligible"], reason=info["huReason"],
              image_types=info["imageTypes"], multi_energy=info["multiEnergyValues"])
        check("series_geometry_passes", not info["errors"], errors=info["errors"],
              slices=len(info["files"]), slice_spacing=info["sliceSpacing"])
        widget.seriesCombo.setCurrentIndex(index)
        widget.onLoadSeries()
        volume = widget.currentVolume
        check("dicom_volume_loaded", widget.nodeIsPresent(volume),
              errors=widget.loadedQuality.get("errors") if widget.loadedQuality else None)
        check("volume_rendering_ready", widget.nodeIsPresent(widget.currentVRDisplay),
              detail=widget._renderIssue)
        widget.softButton.click()
        display = volume.GetDisplayNode()
        check("ct_window_level_controls", abs(display.GetWindow() - 400) < 1e-6
              and abs(display.GetLevel() - 40) < 1e-6,
              window=display.GetWindow(), level=display.GetLevel())
        widget.lungButton.click()
        check("ct_lung_window", abs(display.GetWindow() - 1500) < 1e-6
              and abs(display.GetLevel() + 600) < 1e-6,
              window=display.GetWindow(), level=display.GetLevel())
        widget.boneButton.click()
        check("ct_bone_window", abs(display.GetWindow() - 2000) < 1e-6
              and abs(display.GetLevel() - 400) < 1e-6,
              window=display.GetWindow(), level=display.GetLevel())
        widget.softButton.click()
        voxels = slicer.util.arrayFromVolume(volume)
        check("ct_hu_value_range", voxels.dtype.kind in "if" and float(np.min(voxels)) < -900
              and float(np.max(voxels)) > 500,
              dtype=str(voxels.dtype), minimum=float(np.min(voxels)), maximum=float(np.max(voxels)))

        ref = slicer.util.loadVolume(str(REFERENCE), properties={"name": "CT3D reference only"})
        ref_values = slicer.util.arrayFromVolume(ref)
        d2r, r2r = vtk.vtkMatrix4x4(), vtk.vtkMatrix4x4()
        volume.GetIJKToRASMatrix(d2r)
        ref.GetRASToIJKMatrix(r2r)
        depth, height, width = voxels.shape
        samples, grid_errors = [], []
        rng = np.random.default_rng(20261001)
        for i, j, k in rng.integers([0, 0, 0], [width, height, depth], size=(1000, 3)):
            world = d2r.MultiplyPoint([int(i), int(j), int(k), 1.0])
            ref_ijk = r2r.MultiplyPoint(world)
            ri, rj, rk = [int(round(v)) for v in ref_ijk[:3]]
            if (0 <= rk < ref_values.shape[0] and 0 <= rj < ref_values.shape[1]
                    and 0 <= ri < ref_values.shape[2]):
                samples.append((float(voxels[k, j, i]), float(ref_values[rk, rj, ri])))
                grid_errors.append(max(abs(ref_ijk[0]-ri), abs(ref_ijk[1]-rj), abs(ref_ijk[2]-rk)))
        differences = [abs(a-b) for a, b in samples]
        check("dcm2niix_reference_hu_samples", len(samples) >= 100 and max(differences, default=1e9) <= 1
              and max(grid_errors, default=1e9) <= 0.1,
              sample_count=len(samples), max_abs_difference=max(differences, default=None),
              max_reference_grid_error_voxels=max(grid_errors, default=None),
              volume_dimensions=list(volume.GetImageData().GetDimensions()),
              reference_dimensions=list(ref.GetImageData().GetDimensions()))
        slicer.mrmlScene.RemoveNode(ref)
    after = {str(path): sha256(path) for path in source_files}
    check("source_dicoms_unchanged", before == after, file_count=len(source_files))
    result["status"] = "passed"
    exit_code = 0
except Exception as error:
    result["status"] = "failed"
    result["error"] = str(error)
    import traceback
    result["traceback"] = traceback.format_exc()
finally:
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    slicer.app.exit(exit_code)
