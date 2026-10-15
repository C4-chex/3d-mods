"""Leave a tagged stack window open during actual application shutdown."""
import json
import os
from pathlib import Path
import slicer
from DICOMLib import DICOMUtils

out=Path(os.environ['CT3D_SLICE_STACK_QA'])
slicer.util.selectModule('CT3D')
w=slicer.modules.CT3DWidget
with DICOMUtils.TemporaryDICOMDatabase(str(out/'shutdown-database')) as database:
    DICOMUtils.importDicom(r'D:\dicom文件\dcm',database,copyFiles=False)
    w.populateSeries()
    index=next(i for i,q in enumerate(w.series) if q['modality']=='MR' and not q['errors'] and len(q['files'])==20)
    w.seriesCombo.setCurrentIndex(index)
    w.onLoadSeries()
    w.openSliceStack()
    window=w._sliceStackWindow
    if not window or not window.model or not window.isVisible():
        raise AssertionError('Open window required')
    if not window.model.tags:
        window.model.add_tag(0,1,1,'正常退出恢复检查')
    window.changed()
    if not window.save():
        raise AssertionError('State save required')
    result={'status':'prepared_for_actual_shutdown','window_open':True,'tags':len(window.model.tags),'state_path':str(window.model.path)}
    (out/'open-window-shutdown.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
# Do not close the window or call cleanup here. The host must verify actual exit.
