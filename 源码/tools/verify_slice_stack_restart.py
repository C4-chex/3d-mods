"""Second process proves state restoration, using the first process's output."""
import json
import os
from pathlib import Path
import traceback
import numpy as np
import slicer
from DICOMLib import DICOMUtils

OUT=Path(os.environ['CT3D_SLICE_STACK_QA'])
report={'status':'running','checks':[]}
def check(name,passed):
    report['checks'].append({'name':name,'passed':bool(passed)})
    if not passed:
        raise AssertionError(name)
def run():
    first=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
    fixture=first['restart_fixture']
    expected=json.loads(Path(fixture['path']).read_text(encoding='utf-8'))['state']
    slicer.util.selectModule('CT3D')
    w=slicer.modules.CT3DWidget
    with DICOMUtils.TemporaryDICOMDatabase(str(OUT/'restart-database')) as database:
        DICOMUtils.importDicom(r'D:\dicom文件\dcm',database,copyFiles=False)
        w.populateSeries()
        valid=[i for i,q in enumerate(w.series) if q['modality']=='MR' and not q['errors'] and len(q['files'])==20]
        w.seriesCombo.setCurrentIndex(valid[0])
        w.onLoadSeries()
        w.openSliceStack()
        slicer.app.processEvents()
        window=w._sliceStackWindow
        check('new_process_opens_window',window.isVisible() and window.model is not None)
        check('same_source_identity',window.model.key==fixture['source_key'])
        check('tags_survive_process_restart',window.model.tags==expected['tags'])
        check('display_state_survives_process_restart',window.model.snapshot()==expected)
        window.tagList.setCurrentRow(0)
        window.focus_tag()
        check('restored_tag_links_main_view',np.allclose(slicer.util.getNode('Crosshair').GetCrosshairRAS(),expected['tags'][0]['original_ras_mm'],atol=.001))
        window.close()
        w.cleanupSliceStack()
        slicer.app.processEvents()
        check('restart_cleanup',w._sliceStackWindow is None)
    report['status']='passed'
try:
    run()
except Exception:
    report['status']='failed'
    report['error']=traceback.format_exc()
finally:
    (OUT/'restart-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if report['status']!='passed':
        raise RuntimeError(report.get('error','Restart check failed'))
