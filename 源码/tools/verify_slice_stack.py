"""Real packaged-app UI/geometry/persistence acceptance; no external modules."""
import hashlib
import json
import os
from pathlib import Path
import time
import traceback
import numpy as np
import slicer
import vtk
from DICOMLib import DICOMUtils
from CT3DLib.CT3DSliceStack import SliceStackModel

OUT=Path(os.environ['CT3D_SLICE_STACK_QA'])
OUT.mkdir(parents=True,exist_ok=True)
report={'status':'running','checks':[]}
def check(name,condition,**details):
    report['checks'].append(dict(name=name,passed=bool(condition),**details))
    if not condition:
        raise AssertionError(name)
def events():
    for _ in range(5):
        slicer.app.processEvents()
        time.sleep(.02)
def pixels_hash(volume):
    digest=hashlib.sha256()
    for plane in slicer.util.arrayFromVolume(volume):
        digest.update(np.ascontiguousarray(plane).tobytes())
    return digest.hexdigest()
def screen(window,point):
    window.renderer.SetWorldPoint(*point,1)
    window.renderer.WorldToDisplay()
    x,y,_=window.renderer.GetDisplayPoint()
    return int(x),int(y)
def mouse(window,event,x,y):
    window.interactor.SetEventInformation(x,y)
    window.interactionStyle.InvokeEvent(event)
    events()

def run():
    slicer.util.selectModule('CT3D')
    w=slicer.modules.CT3DWidget
    errors=[]
    w.showError=lambda message:errors.append(str(message))
    check('no_volume_button_disabled',not w.sliceStackButton.enabled)
    with DICOMUtils.TemporaryDICOMDatabase(str(OUT/'database')) as db:
        source=Path(r'D:\dicom文件\dcm')
        source_hash={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.dcm')}
        DICOMUtils.importDicom(str(source),db,copyFiles=False)
        w.populateSeries()
        valid=[i for i,q in enumerate(w.series) if q['modality']=='MR' and not q['errors'] and len(q['files'])==20]
        check('mr_fixtures',len(valid)>=2)
        first,second=valid[:2]
        w.seriesCombo.setCurrentIndex(first)
        w.onLoadSeries()
        events()
        check('mr_load',w.currentVolume is not None and not errors,errors=errors)
        original=pixels_hash(w.currentVolume)
        started=time.perf_counter()
        w.sliceStackButton.click()
        events()
        win=w._sliceStackWindow
        check('button_opens_independent_window',win is not None and win.isVisible() and win.model is not None,
              button_enabled=bool(w.sliceStackButton.enabled),info=str(win.info.text) if win else 'not created')
        m=win.model
        check('all_source_planes_visible',len(win.actors)==m.count and all(a.GetVisibility() for a in win.actors),count=m.count)
        check('image_data_shared',all(a.GetMapper().GetInput()==w.currentVolume.GetImageData() for a in win.actors))
        check('nearest_neighbor',all(a.GetProperty().GetInterpolationType()==0 for a in win.actors))
        old_size=(win.width,win.height)
        win.resize(800,450)
        events()
        check('small_window_controls_scroll',win.height<=450 and win.controlsScroll.verticalScrollBar().maximum>0)
        win.grab().save(str(OUT/'small-window.png'))
        win.resize(*old_size)
        events()
        report['open_seconds']=round(time.perf_counter()-started,3)
        deviations=[]
        for path in w.loadedQuality['files']:
            lps=np.array(w.numbers(w.tag(db,path,'0020,0032')))
            expected=lps*np.array([-1,-1,1])
            k=min(range(m.count),key=lambda k:np.linalg.norm(m.position(k,0,0)-expected))
            orientation=np.array(w.numbers(w.tag(db,path,'0020,0037')))
            spacing=w.numbers(w.tag(db,path,'0028,0030'))
            for i,j in ((0,0),(m.dimensions[0]-1,0),(0,m.dimensions[1]-1)):
                target=(lps+orientation[:3]*spacing[1]*i+orientation[3:]*spacing[0]*j)*[-1,-1,1]
                deviations.append(float(np.linalg.norm(m.position(k,i,j)-target)))
        check('original_dicom_plane_geometry',max(deviations)<.01,max_error_mm=max(deviations))
        w.openSliceStack()
        check('repeated_open_reuses_window',w._sliceStackWindow is win)
        k=m.selected
        win.only_selected()
        win.fit()
        events()
        win.view.threeDView().renderWindow().Render()
        point=m.position(k,100,100,display=True)
        x,y=screen(win,point)
        win.mode.setCurrentIndex(1)
        mouse(win,'LeftButtonPressEvent',x,y)
        check('real_drag_pick',win.drag is not None)
        mouse(win,'MouseMoveEvent',x+40,y+20)
        mouse(win,'LeftButtonReleaseEvent',x+40,y+20)
        displacement=m.displacement(k)
        check('drag_moves_slice_in_plane',np.linalg.norm(displacement)>.1 and abs(np.dot(displacement,m.planes[k][:3,2]))<1e-6,offset_mm=m.offsets[k].tolist())
        check('original_position_unchanged',np.allclose(m.position(k,100,100),point))
        win.undo()
        check('undo_move',np.allclose(m.offsets[k],0))
        win.offsetSpins[0].setValue(25)
        win.offsetSpins[1].setValue(-12)
        events()
        win.view.threeDView().renderWindow().Render()
        win.note.setText('验收：原图位置关联')
        win.mode.setCurrentIndex(2)
        x,y=screen(win,m.position(k,110,115,display=True))
        mouse(win,'LeftButtonPressEvent',x,y)
        mouse(win,'LeftButtonReleaseEvent',x,y)
        check('mouse_adds_position_tag',len(m.tags)==1,tag_count=len(m.tags))
        tag=m.tags[0]
        tag_world=np.array(tag['original_ras_mm'])
        check('tag_bound_to_original_coordinates',np.allclose(tag_world,m.position(k,*tag['ij'])))
        win.tagList.setCurrentRow(0)
        win.focus_tag()
        crosshair=slicer.util.getNode('Crosshair')
        position=crosshair.GetCrosshairRAS()
        check('tag_main_view_link',np.allclose(position,tag_world,atol=.001))
        win.show_all()
        win.sliceSpin.setValue(1)
        win.hiddenCheck.setChecked(True)
        check('hide_slice',not win.actors[0].GetVisibility())
        win.fromSpin.setValue(2)
        win.toSpin.setValue(m.count-1)
        check('range_filter',not win.actors[-1].GetVisibility())
        check('state_saved',win.save() and m.path.is_file())
        saved=m.snapshot()
        state_path=m.path
        win.close()
        events()
        check('close_releases_volume',win.model is None and not win.actors)
        w.openSliceStack()
        events()
        m=win.model
        check('reopen_restores_tags',m.tags==saved['tags'])
        check('reopen_restores_display_state',m.snapshot()==saved)
        report['restart_fixture']={'source_key':m.key,'path':str(state_path),'state':saved}
        w.seriesCombo.setCurrentIndex(second)
        w.onLoadSeries()
        events()
        check('follows_sequence_switch',win.model is not None and win.model.volume==w.currentVolume and win.model.key!=report['restart_fixture']['source_key'])
        check('tags_do_not_mix',not win.model.tags)
        w.seriesCombo.setCurrentIndex(first)
        w.onLoadSeries()
        events()
        check('return_restores_first_sequence_tags',win.model.tags==saved['tags'])
        win.reset_all()
        check('reset_all_preserves_tags',np.allclose(win.model.offsets,0) and not win.model.hidden and len(win.model.tags)==1)
        # Right-button camera interaction works even in the tag/move modes.
        win.mode.setCurrentIndex(2)
        camera=win.renderer.GetActiveCamera()
        before_camera=np.array(camera.GetPosition())
        win.interactor.SetEventInformation(200,200)
        win.interactionStyle.OnRightButtonDown()
        mouse(win,'MouseMoveEvent',200,225)
        win.interactionStyle.OnRightButtonUp()
        check('camera_zoom_in_tag_mode',not np.allclose(camera.GetPosition(),before_camera))
        # Bound and concurrency guards: isolated records, never the user's output.
        guard=SliceStackModel(w.currentVolume,w.loadedQuality,OUT/'guard')
        guard.path.write_text('{invalid',encoding='utf-8')
        malformed=SliceStackModel(w.currentVolume,w.loadedQuality,OUT/'guard')
        check('invalid_record_not_applied',bool(malformed.error) and not malformed.tags)
        try:
            malformed.save()
            refused=False
        except ValueError:
            refused=True
        check('invalid_record_not_overwritten',refused and guard.path.read_text()=='{invalid')
        simultaneous=SliceStackModel(w.currentVolume,w.loadedQuality,OUT/'concurrent')
        simultaneous.save()
        concurrent=SliceStackModel(w.currentVolume,w.loadedQuality,OUT/'concurrent')
        simultaneous.add_tag(0,1,1,'另一个窗口')
        simultaneous.save()
        try:
            concurrent.save()
            refused=False
        except ValueError:
            refused=True
        check('concurrent_file_write_guard',refused)
        capacity=SliceStackModel(w.currentVolume,w.loadedQuality,OUT/'capacity')
        capacity.save()
        prior=capacity.path.read_bytes()
        capacity.tags=[{'id':str(n),'slice':0,'ij':[1.,1.],'original_ras_mm':capacity.position(0,1,1).tolist(),'note':'😀'*500} for n in range(1000)]
        try:
            capacity.save()
            refused=False
        except ValueError:
            refused=True
        check('oversize_save_preserves_previous_file',refused and capacity.path.read_bytes()==prior)
        win.save()
        live_path=win.model.path
        live_bytes=live_path.read_bytes()
        win.close()
        live_path.write_text('{invalid',encoding='utf-8')
        w.openSliceStack()
        check('invalid_record_window_read_only',bool(win.model.error) and not win.panel.enabled)
        win.close()
        check('invalid_record_window_can_close',not win.isVisible() and live_path.read_text()=='{invalid')
        live_path.write_bytes(live_bytes)
        w.openSliceStack()
        win.save()
        check('source_pixels_unchanged',pixels_hash(w.currentVolume)==original)
        check('source_dicom_unchanged',source_hash=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.dcm')})
        win.show_all()
        win.sliceSpin.setValue(k+2)
        win.offsetSpins[0].setValue(-110)
        win.offsetSpins[1].setValue(30)
        win.sliceSpin.setValue(k+1)
        win.offsetSpins[0].setValue(140)
        win.offsetSpins[1].setValue(-40)
        check('independent_offsets_and_tag_display_binding',np.count_nonzero(np.linalg.norm(win.model.offsets,axis=1)>.1)==2
              and np.allclose(win.tag_actors[0].GetPosition(),win.model.displacement(k)))
        win.fit()
        win.save()
        events()
        win.grab().save(str(OUT/'slice-stack-mr.png'))
        slicer.util.mainWindow().grab().save(str(OUT/'main-3d-button.png'))
        win.close()
        # Real public CT sequence: all planes use the same source buffer.
        ct=Path(r'D:\3d - 1\ct part\source-dcm_qa_ct\In')
        if not ct.is_dir():
            raise AssertionError('CT fixture unavailable')
        DICOMUtils.importDicom(str(ct),db,copyFiles=False)
        w.populateSeries()
        candidates=[i for i,q in enumerate(w.series) if q['modality']=='CT' and not q['errors'] and q['huEligible']]
        check('ct_fixture',bool(candidates))
        choice=max(candidates,key=lambda i:len(w.series[i]['files']))
        w.seriesCombo.setCurrentIndex(choice)
        w.onLoadSeries()
        events()
        w.openSliceStack()
        events()
        m=win.model
        check('ct_all_planes',m is not None and len(win.actors)==m.count and all(a.GetVisibility() for a in win.actors),count=m.count if m else 0)
        check('ct_buffer_shared',all(a.GetMapper().GetInput()==w.currentVolume.GetImageData() for a in win.actors))
        ct_errors=[]
        for path in w.loadedQuality['files']:
            lps=np.array(w.numbers(w.tag(db,path,'0020,0032')))
            expected=lps*[-1,-1,1]
            ct_errors.append(min(float(np.linalg.norm(m.position(k,0,0)-expected)) for k in range(m.count)))
        check('ct_dicom_plane_origins',max(ct_errors)<.01,max_error_mm=max(ct_errors))
        check('ct_hu_display_matches_main',abs(win.actors[0].GetProperty().GetColorWindow()-w.currentVolume.GetDisplayNode().GetWindow())<.001)
        win.grab().save(str(OUT/'slice-stack-ct.png'))
        win.close()
        w.cleanupSliceStack()
        events()
        check('window_cleanup',w._sliceStackWindow is None)
        check('no_application_errors',not errors,errors=errors)
    report['status']='passed'

try:
    run()
except Exception:
    report['status']='failed'
    report['error']=traceback.format_exc()
finally:
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if report['status']!='passed':
        raise RuntimeError(report.get('error','Slice stack check failed'))
