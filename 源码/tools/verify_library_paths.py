"""Check default library paths through actual Slicer widget handlers."""
import json
import traceback
from pathlib import Path
import qt
import slicer
from CT3DLib.CT3DPaths import inputDirectory, outputPath
root = Path(__file__).resolve().parents[1]
report = {"status":"running", "checks":[]}
def check(name, value):
    report["checks"].append({"name":name,"passed":bool(value)})
    if not value:
        raise AssertionError(name)

def output_inventory():
    return sorted((str(p.relative_to(root/"output")), p.stat().st_size, p.stat().st_mtime_ns)
                  for p in (root/"output").rglob("*") if p.is_file())
originalDialog = qt.QFileDialog
originalMessage = qt.QMessageBox
calls=[]
class CancelDialog:
    @staticmethod
    def getExistingDirectory(*args):
        calls.append(args)
        return ""
    @staticmethod
    def getSaveFileName(*args):
        calls.append(args)
        return ""
class TestMessage:
    Yes=1
    No=2
    @staticmethod
    def question(*args):
        return TestMessage.Yes
try:
    slicer.util.selectModule("CT3D")
    w=slicer.modules.ct3d.widgetRepresentation().self()
    check("input_at_n2",Path(inputDirectory())==root/"input")
    check("output_at_n2",Path(outputPath())==root/"output")
    output_before=output_inventory()
    qt.QFileDialog=CancelDialog
    w.onImportFolder()
    check("import_dialog_defaults_input",Path(calls[-1][2])==root/"input")
    w.currentQuality={"modality":"MR"}
    w.onExportQualityReport()
    check("report_dialog_defaults_output",Path(calls[-1][2]).parent==root/"output")
    w.onExportMeasurements()
    check("measurements_dialog_defaults_output",Path(calls[-1][2])==root/"output"/"lengths.json")
    w.currentSegmentation=slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
    w.onSaveSegmentation()
    check("segmentation_dialog_defaults_output",Path(calls[-1][2]).parent==root/"output")
    w.onExportMesh()
    check("mesh_dialog_defaults_output",Path(calls[-1][2])==root/"output")
    w.currentVolume=slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    w.loadedQuality={"burnedInAnnotation":"NO"}
    qt.QMessageBox=TestMessage
    w.onExportViewSnapshot()
    check("screenshot_dialog_defaults_output",Path(calls[-1][2]).parent==root/"output")
    check("cancel_preserves_existing_output",output_inventory()==output_before)
    report["status"]="passed"
except Exception:
    report["status"]="failed"
    report["traceback"]=traceback.format_exc()
finally:
    qt.QFileDialog=originalDialog
    qt.QMessageBox=originalMessage
    (root/"verification"/"library-paths-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    slicer.app.exit(0 if report["status"]=="passed" else 1)
