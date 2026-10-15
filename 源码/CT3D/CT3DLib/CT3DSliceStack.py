"""Source-linked slice planes. Display offsets never modify the MRML volume."""
import hashlib
import json
import math
import os
import tempfile
import uuid
from pathlib import Path

import numpy as np
import qt
import slicer
import vtk
from .CT3DPaths import outputPath


def matrix_array(matrix):
    return np.array([[matrix.GetElement(i, j) for j in range(4)] for i in range(4)])


def vtk_matrix(array):
    result = vtk.vtkMatrix4x4()
    for i in range(4):
        for j in range(4):
            result.SetElement(i, j, float(array[i, j]))
    return result


class SliceStackModel:
    """Bounded, atomic state files keyed by source content and world geometry."""
    def __init__(self, volume, quality, directory=None):
        self.volume = volume
        self.image = volume.GetImageData()
        self.dimensions = self.image.GetDimensions()
        if self.image.GetNumberOfScalarComponents() != 1 or min(self.dimensions) < 1:
            raise ValueError("只支持已载入的单分量影像。")
        self.count = self.dimensions[2]
        matrix = vtk.vtkMatrix4x4()
        volume.GetIJKToRASMatrix(matrix)
        local = matrix_array(matrix)
        parent = volume.GetParentTransformNode()
        transform = vtk.vtkGeneralTransform()
        slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(parent, None, transform)
        def world(i, j, k):
            p = local @ np.array([i, j, k, 1.])
            return np.array(transform.TransformPoint(p[:3]))
        self.planes = []
        for k in range(self.count):
            origin = world(0, 0, k)
            u, v = world(1, 0, k)-origin, world(0, 1, k)-origin
            normal = np.cross(u, v)
            if not np.all(np.isfinite(normal)) or np.linalg.norm(normal) < 1e-10:
                raise ValueError("采集平面几何无效。")
            normal /= np.linalg.norm(normal)
            plane = np.eye(4)
            plane[:3, 0], plane[:3, 1], plane[:3, 2] = u, v, normal
            plane[:3, 3] = origin-normal*k
            # Acquisition regularization may be nonlinear between slices, but
            # each displayed source slice must remain a genuinely planar image.
            if parent:
                for i in np.linspace(0, self.dimensions[0]-1, 5):
                    for j in np.linspace(0, self.dimensions[1]-1, 5):
                        if np.linalg.norm(world(i,j,k)-(plane @ [i,j,k,1])[:3]) > .01:
                            raise ValueError("当前空间变换使切片弯曲，不能按原始平面展开。请使用原四视图核对。")
            self.planes.append(plane)
        physical = np.eye(4)
        direction = np.array(
            [[self.image.GetDirectionMatrix().GetElement(i,j) for j in range(3)] for i in range(3)])
        physical[:3,:3] = direction @ np.diag(self.image.GetSpacing())
        physical[:3,3] = self.image.GetOrigin()
        self.physical_inverse = np.linalg.inv(physical)
        digest = hashlib.sha256()
        digest.update(str(quality.get("uid") or volume.GetAttribute("DICOM.instanceUIDs") or "").encode())
        digest.update(str(self.dimensions).encode())
        digest.update(np.asarray(self.planes, dtype='<f8').round(6).tobytes())
        voxels = slicer.util.arrayFromVolume(volume)  # view, not a copied volume
        for plane in voxels:
            digest.update(np.ascontiguousarray(plane).tobytes())
        self.key = digest.hexdigest()
        self.path = Path(directory or outputPath("slice-stack")) / (self.key+".json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.offsets = np.zeros((self.count, 2))
        self.hidden = set()
        self.range = [0, self.count-1]
        self.selected = self.count//2
        self.tags = []
        self.undo = []
        self.error = ""
        self._disk_hash = None
        self.load()

    def position(self, k, i, j, display=False):
        point = (self.planes[k] @ [i,j,k,1])[:3]
        if display:
            point = point+self.displacement(k)
        return point

    def displacement(self, k):
        p = self.planes[k]
        return p[:3,0]/np.linalg.norm(p[:3,0])*self.offsets[k,0] + p[:3,1]/np.linalg.norm(p[:3,1])*self.offsets[k,1]

    def actor_matrix(self, k):
        m = self.planes[k].copy()
        m[:3,3] += self.displacement(k)
        return m @ self.physical_inverse

    def snapshot(self):
        return {"offsets_mm":self.offsets.tolist(), "hidden":sorted(self.hidden),
                "range":list(self.range), "selected":self.selected, "tags":list(self.tags)}

    def validate(self, state):
        offsets = np.asarray(state["offsets_mm"], dtype=float)
        if offsets.shape != (self.count,2) or not np.all(np.isfinite(offsets)) or np.max(np.abs(offsets)) > 10000:
            raise ValueError("切片偏移记录无效。")
        def index(value):
            if isinstance(value,bool) or not isinstance(value,int) or not 0 <= value < self.count:
                raise ValueError("切片序号越界。")
            return value
        hidden = {index(k) for k in state["hidden"]}
        limits = [index(k) for k in state["range"]]
        if len(limits) != 2 or limits[0] > limits[1]:
            raise ValueError("显示范围无效。")
        selected = index(state["selected"])
        tags = state["tags"]
        if not isinstance(tags,list) or len(tags)>1000:
            raise ValueError("tag 数量无效或超过 1000。")
        ids=set()
        for tag in tags:
            k = index(tag["slice"])
            i,j = tag["ij"]
            if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in (i,j)) or not (0<=i<=self.dimensions[0]-1 and 0<=j<=self.dimensions[1]-1):
                raise ValueError("tag 位置越界。")
            if not isinstance(tag["note"],str) or not 0 < len(tag["note"]) <= 500:
                raise ValueError("tag 备注无效。")
            if not isinstance(tag["id"],str) or tag["id"] in ids:
                raise ValueError("tag 标识无效。")
            ids.add(tag["id"])
            if not np.allclose(self.position(k,i,j), tag["original_ras_mm"], atol=.001, rtol=0):
                raise ValueError("tag 的原始坐标与影像不匹配。")
        return offsets, hidden, limits, selected, tags

    def restore(self, state):
        self.offsets,self.hidden,self.range,self.selected,self.tags = self.validate(state)

    def checkpoint(self):
        self.undo.append(self.snapshot())
        self.undo = self.undo[-50:]

    def undo_last(self):
        if self.undo:
            self.restore(self.undo.pop())

    def add_tag(self,k,i,j,note):
        if len(self.tags)>=1000:
            raise ValueError("最多保存 1000 个 tag。")
        tag={"id":uuid.uuid4().hex,"slice":int(k),"ij":[float(i),float(j)],
             "original_ras_mm":self.position(k,i,j).tolist(),"note":note.strip()}
        state=self.snapshot()
        state["tags"]=state["tags"]+[tag]
        self.validate(state)
        self.checkpoint()
        self.tags.append(tag)
        return tag

    def load(self):
        if not self.path.exists():
            return
        try:
            if self.path.stat().st_size>2*1024*1024:
                raise ValueError("记录超过允许大小。")
            raw=self.path.read_bytes()
            data=json.loads(raw)
            if data.get("schema")!=1 or data.get("source_key")!=self.key:
                raise ValueError("记录版本或来源不匹配。")
            self.restore(data["state"])
            self._disk_hash=hashlib.sha256(raw).hexdigest()
        except Exception as exc:
            self.error="记录未恢复，原文件保留且不会覆盖："+str(exc)

    def save(self):
        if self.error:
            raise ValueError(self.error)
        disk_hash=hashlib.sha256(self.path.read_bytes()).hexdigest() if self.path.exists() else None
        if disk_hash!=self._disk_hash:
            raise ValueError("记录已被其他窗口或程序修改；为避免覆盖，请关闭窗口后重新打开。")
        state=self.snapshot()
        self.validate(state)
        raw=json.dumps({"schema":1,"source_key":self.key,"coordinate_system":"RAS mm",
                        "display_offsets_only":True,"state":state},ensure_ascii=False,indent=2).encode('utf-8')
        if len(raw)>2*1024*1024:
            raise ValueError("记录超过 2 MiB，请减少 tag 或缩短备注；已有文件未覆盖。")
        fd,temp=tempfile.mkstemp(dir=str(self.path.parent),prefix='.slice-stack-',suffix='.tmp')
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp,self.path)
            self._disk_hash=hashlib.sha256(raw).hexdigest()
        finally:
            if os.path.exists(temp):
                os.unlink(temp)


class SliceStackWindow(qt.QDialog):
    def __init__(self,owner):
        super().__init__(slicer.util.mainWindow())
        self.setWindowFlags(qt.Qt.Window)
        self.setWindowTitle("CT3D · 切片展开（展示偏移，不改变原图）")
        available=slicer.util.mainWindow().screen().availableGeometry
        self.resize(min(1100,max(400,available.width()-40)),min(760,max(300,available.height()-60)))
        self.owner=owner
        self.model=None
        self.actors=[]
        self.tag_actors=[]
        self._tagSignature=None
        self.drag=None
        self._updating=False
        self._display=None
        self._displayObserver=None
        self.scene=slicer.vtkMRMLScene()
        self.viewNode=self.scene.AddNewNodeByClass('vtkMRMLViewNode')
        self.viewNode.SetBoxVisible(False)
        self.viewNode.SetAxisLabelsVisible(True)
        self.viewNode.SetBackgroundColor(.08,.08,.1)
        self.viewNode.SetBackgroundColor2(.08,.08,.1)
        root=qt.QHBoxLayout(self)
        panel=qt.QWidget()
        self.panel=panel
        panel.setMaximumWidth(320)
        left=qt.QVBoxLayout(panel)
        self.controlsScroll=qt.QScrollArea()
        self.controlsScroll.setWidgetResizable(True)
        self.controlsScroll.setMaximumWidth(330)
        self.controlsScroll.setWidget(panel)
        root.addWidget(self.controlsScroll)
        self.info=qt.QLabel("尚未载入影像")
        self.info.setWordWrap(True)
        left.addWidget(self.info)
        self.mode=qt.QComboBox()
        self.mode.addItems(['旋转观察','移动切片（平面内）','添加 tag'])
        left.addWidget(self.mode)
        hint=qt.QLabel('左键按当前模式操作；右键缩放，中键平移视角。移动只改变展示，原始坐标不变。')
        hint.setWordWrap(True)
        left.addWidget(hint)
        self.sliceSpin=qt.QSpinBox()
        left.addWidget(qt.QLabel('选中切片（从 1 开始）'))
        left.addWidget(self.sliceSpin)
        self.sliceSpin.valueChanged.connect(self.select_slice)
        self.offsetSpins=[]
        for axis in ('切片横向偏移 / mm','切片纵向偏移 / mm'):
            left.addWidget(qt.QLabel(axis))
            spin=qt.QDoubleSpinBox()
            spin.setRange(-10000,10000)
            spin.setDecimals(2)
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self.offset_changed)
            self.offsetSpins.append(spin)
            left.addWidget(spin)
        self.hiddenCheck=qt.QCheckBox('隐藏选中切片')
        self.hiddenCheck.toggled.connect(self.hide_selected)
        left.addWidget(self.hiddenCheck)
        row=qt.QHBoxLayout()
        self.fromSpin,self.toSpin=qt.QSpinBox(),qt.QSpinBox()
        left.addWidget(qt.QLabel('显示层范围（包含两端）'))
        row.addWidget(self.fromSpin)
        row.addWidget(self.toSpin)
        left.addLayout(row)
        for spin in (self.fromSpin,self.toSpin):
            spin.valueChanged.connect(self.range_changed)
        for text,callback in [('只看选中层',self.only_selected),('恢复全部显示',self.show_all),
                              ('当前切片复位',self.reset_selected),('全部复位',self.reset_all),
                              ('撤销上次操作',self.undo),('视角复位',self.fit)]:
            button=qt.QPushButton(text)
            button.clicked.connect(callback)
            left.addWidget(button)
        self.note=qt.QLineEdit()
        self.note.setMaxLength(500)
        self.note.setPlaceholderText('输入备注后，以“添加 tag”模式点击切片')
        left.addWidget(self.note)
        self.tagList=qt.QListWidget()
        self.tagList.itemClicked.connect(self.focus_tag)
        left.addWidget(self.tagList)
        for text,callback in [('修改选中 tag 备注',self.edit_tag),('删除选中 tag',self.remove_tag),('保存当前状态',self.save)]:
            button=qt.QPushButton(text)
            button.clicked.connect(callback)
            left.addWidget(button)
        self.status=qt.QLabel('')
        self.status.setWordWrap(True)
        left.addWidget(self.status)
        self.view=slicer.qMRMLThreeDWidget()
        self.view.setMRMLScene(self.scene)
        self.view.setMRMLViewNode(self.viewNode)
        self.view.threeDController().hide()
        root.addWidget(self.view,1)
        self.renderer=self.view.threeDView().renderWindow().GetRenderers().GetFirstRenderer()
        self.interactor=self.view.threeDView().renderWindow().GetInteractor()
        self.interactionStyle=vtk.vtkInteractorStyleTrackballCamera()
        self.interactor.SetInteractorStyle(self.interactionStyle)
        self._observers=[self.interactionStyle.AddObserver(event,callback) for event,callback in
                         [('LeftButtonPressEvent',self.press),('MouseMoveEvent',self.move),('LeftButtonReleaseEvent',self.release)]]
        self.picker=vtk.vtkCellPicker()
        self.picker.PickFromListOn()
        self.picker.SetTolerance(.001)
        self.outline=self.poly_actor([], (1,.8,.1))
        self.link=self.poly_actor([], (.6,.6,.6))
        self.original=self.poly_actor([], (.5,.5,.5))
        self._saveTimer=qt.QTimer(self)
        self._saveTimer.setSingleShot(True)
        self._saveTimer.timeout.connect(self.save)

    def poly_actor(self,points,color):
        poly=vtk.vtkPolyData()
        mapper=vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)
        actor=vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*color)
        actor.GetProperty().SetLineWidth(2)
        actor.PickableOff()
        self.renderer.AddActor(actor)
        return actor

    @staticmethod
    def line_points(actor,coordinates):
        points=vtk.vtkPoints()
        line=vtk.vtkPolyLine()
        line.GetPointIds().SetNumberOfIds(len(coordinates))
        for i,p in enumerate(coordinates):
            points.InsertNextPoint(*p)
            line.GetPointIds().SetId(i,i)
        cells=vtk.vtkCellArray()
        if coordinates:
            cells.InsertNextCell(line)
        poly=actor.GetMapper().GetInput()
        poly.SetPoints(points)
        poly.SetLines(cells)
        poly.Modified()

    def clear_volume(self):
        self._saveTimer.stop()
        if self._display and self._displayObserver is not None:
            self._display.RemoveObserver(self._displayObserver)
        self._display=self._displayObserver=None
        for actor in self.actors+self.tag_actors:
            self.renderer.RemoveViewProp(actor)
        self.actors,self.tag_actors=[],[]
        self._tagSignature=None
        self.picker.InitializePickList()
        for actor in (self.outline,self.original,self.link):
            self.line_points(actor,[])
        self.model=None
        self.drag=None
        self.tagList.clear()

    def bind(self,volume,quality):
        if self.model and self.model.volume is volume:
            return
        if self.model:
            self.save()
        self.clear_volume()
        if not volume or not quality:
            self.info.setText('尚未载入影像；请在主窗口载入序列。')
            return
        try:
            model=SliceStackModel(volume,quality)
            self.model=model
            self.panel.setEnabled(not bool(model.error))
            for k in range(model.count):
                mapper=vtk.vtkImageSliceMapper()
                mapper.SetInputData(model.image)
                mapper.SetOrientationToZ()
                mapper.SetSliceNumber(k)
                mapper.SliceAtFocalPointOff()
                mapper.SliceFacesCameraOff()
                actor=vtk.vtkImageSlice()
                actor.SetMapper(mapper)
                actor.GetProperty().SetInterpolationTypeToNearest()
                self.renderer.AddViewProp(actor)
                self.picker.AddPickList(actor)
                self.actors.append(actor)
            self._display=volume.GetDisplayNode()
            self._displayObserver=self._display.AddObserver(vtk.vtkCommand.ModifiedEvent,self.display_changed)
            self.display_changed()
            self.refresh()
            self.fit()
            if model.error:
                self.status.setText(model.error)
        except Exception as exc:
            self.clear_volume()
            self.info.setText('无法展开：'+str(exc))

    def display_changed(self,*_):
        if not self.model or not self._display:
            return
        for actor in self.actors:
            actor.GetProperty().SetColorWindow(max(.01,self._display.GetWindow()))
            actor.GetProperty().SetColorLevel(self._display.GetLevel())
        self.view.threeDView().scheduleRender()

    def refresh(self):
        m=self.model
        if not m:
            return
        self._updating=True
        try:
            for spin in (self.sliceSpin,self.fromSpin,self.toSpin):
                spin.setRange(1,m.count)
            self.sliceSpin.setValue(m.selected+1)
            self.fromSpin.setValue(m.range[0]+1)
            self.toSpin.setValue(m.range[1]+1)
            self.hiddenCheck.setChecked(m.selected in m.hidden)
            for i,spin in enumerate(self.offsetSpins):
                spin.setValue(float(m.offsets[m.selected,i]))
            for k,actor in enumerate(self.actors):
                actor.SetUserMatrix(vtk_matrix(m.actor_matrix(k)))
                actor.SetVisibility(m.range[0]<=k<=m.range[1] and k not in m.hidden)
            corners=[(0,0),(m.dimensions[0]-1,0),(m.dimensions[0]-1,m.dimensions[1]-1),(0,m.dimensions[1]-1),(0,0)]
            self.line_points(self.outline,[m.position(m.selected,i,j,True) for i,j in corners])
            moved=np.linalg.norm(m.offsets[m.selected])>.001
            self.line_points(self.original,[m.position(m.selected,i,j) for i,j in corners] if moved else [])
            center=((m.dimensions[0]-1)/2,(m.dimensions[1]-1)/2)
            self.line_points(self.link,[m.position(m.selected,*center),m.position(m.selected,*center,display=True)] if moved else [])
            selected_visible=self.actors[m.selected].GetVisibility()
            for actor in (self.outline,self.original,self.link):
                actor.SetVisibility(selected_visible)
            old=self.tagList.currentRow
            radius=max(.5,np.linalg.norm(m.planes[0][:3,0])*2)
            signature=tuple((tag['id'],tag['note']) for tag in m.tags)
            if signature!=self._tagSignature:
                for actor in self.tag_actors:
                    self.renderer.RemoveViewProp(actor)
                self.tag_actors=[]
                self.tagList.clear()
                for n,tag in enumerate(m.tags):
                    self.tagList.addItem(f"{n+1} · 层 {tag['slice']+1} · {tag['note']}")
                    sphere=vtk.vtkSphereSource()
                    sphere.SetRadius(radius)
                    sphere.SetCenter(*m.position(tag['slice'],*tag['ij']))
                    mapper=vtk.vtkPolyDataMapper()
                    mapper.SetInputConnection(sphere.GetOutputPort())
                    actor=vtk.vtkActor()
                    actor.SetMapper(mapper)
                    actor.GetProperty().SetColor(1,.3,.1)
                    actor.PickableOff()
                    self.renderer.AddActor(actor)
                    self.tag_actors.append(actor)
                self._tagSignature=signature
            for tag,actor in zip(m.tags,self.tag_actors):
                actor.SetPosition(*m.displacement(tag['slice']))
                actor.SetVisibility(self.actors[tag['slice']].GetVisibility())
            if 0<=old<len(m.tags):
                self.tagList.setCurrentRow(old)
            visible=sum(a.GetVisibility() for a in self.actors)
            self.info.setText(f"原始采样平面 · {m.count} 层，显示 {visible} 层\n选中第 {m.selected+1} 层 · {'展示已偏移' if moved else '原始位置'}\n最近邻显示，不填补层间细节。")
        finally:
            self._updating=False
        self.view.threeDView().scheduleRender()

    def changed(self):
        self.refresh()
        self._saveTimer.start(300)

    def select_slice(self,value):
        if not self.model or self._updating:
            return
        self.model.selected=int(value)-1
        self.changed()
        m=self.model
        self.jump(m.position(m.selected,(m.dimensions[0]-1)/2,(m.dimensions[1]-1)/2))

    def offset_changed(self,*_):
        if not self.model or self._updating:
            return
        self.model.checkpoint()
        self.model.offsets[self.model.selected]=[spin.value for spin in self.offsetSpins]
        self.changed()

    def hide_selected(self,hidden):
        if not self.model or self._updating:
            return
        self.model.checkpoint()
        if hidden:
            self.model.hidden.add(self.model.selected)
        else:
            self.model.hidden.discard(self.model.selected)
        self.changed()

    def range_changed(self,*_):
        if not self.model or self._updating:
            return
        a,b=self.fromSpin.value-1,self.toSpin.value-1
        if a>b:
            self.status.setText('起始层不能大于结束层。')
            self.refresh()
            return
        self.model.checkpoint()
        self.model.range=[a,b]
        self.changed()

    def only_selected(self):
        if self.model:
            self.model.checkpoint()
            self.model.range=[self.model.selected]*2
            self.model.hidden.discard(self.model.selected)
            self.changed()

    def show_all(self):
        if self.model:
            self.model.checkpoint()
            self.model.range=[0,self.model.count-1]
            self.model.hidden.clear()
            self.changed()

    def reset_selected(self):
        if self.model:
            self.model.checkpoint()
            self.model.offsets[self.model.selected]=0
            self.changed()

    def reset_all(self):
        if self.model:
            self.model.checkpoint()
            self.model.offsets[:]=0
            self.model.hidden.clear()
            self.model.range=[0,self.model.count-1]
            self.changed()
            self.fit()

    def undo(self):
        if self.model:
            self.model.undo_last()
            self.changed()

    def fit(self):
        if self.model:
            m=self.model
            center=m.position(m.count//2,(m.dimensions[0]-1)/2,(m.dimensions[1]-1)/2)
            u=m.planes[0][:3,0]; u=u/np.linalg.norm(u)
            v=m.planes[0][:3,1]; v=v/np.linalg.norm(v)
            normal=np.cross(u,v)
            camera=self.renderer.GetActiveCamera()
            camera.SetFocalPoint(*center)
            camera.SetPosition(*(center+normal*500+u*250-v*100))
            camera.SetViewUp(*(-v))
            corners=[]
            for k,actor in enumerate(self.actors):
                if actor.GetVisibility():
                    for i,j in ((0,0),(m.dimensions[0]-1,0),(0,m.dimensions[1]-1),(m.dimensions[0]-1,m.dimensions[1]-1)):
                        corners.append(m.position(k,i,j,display=True))
            if corners:
                corners=np.asarray(corners)
                low,high=corners.min(axis=0),corners.max(axis=0)
                self.renderer.ResetCamera(low[0],high[0],low[1],high[1],low[2],high[2])
            self.renderer.ResetCameraClippingRange()
            self.view.threeDView().scheduleRender()

    def pick(self):
        if not self.model:
            return None
        x,y=self.interactor.GetEventPosition()
        if not self.picker.Pick(x,y,0,self.renderer):
            return None
        prop=self.picker.GetViewProp()
        for k,actor in enumerate(self.actors):
            if prop==actor:
                return k,np.array(self.picker.GetPickPosition())
        return None

    def ray_plane(self,k):
        x,y=self.interactor.GetEventPosition()
        points=[]
        for z in (0,1):
            self.renderer.SetDisplayPoint(x,y,z)
            self.renderer.DisplayToWorld()
            w=np.array(self.renderer.GetWorldPoint())
            points.append(w[:3]/w[3])
        normal=self.model.planes[k][:3,2]
        direction=points[1]-points[0]
        denominator=np.dot(direction,normal)
        if abs(denominator)<1e-9:
            return None
        origin=self.model.position(k,0,0,display=True)
        return points[0]+direction*np.dot(origin-points[0],normal)/denominator

    def press(self,*_):
        hit=self.pick()
        if hit:
            k,point=hit
            self.model.selected=k
            self.refresh()
            if self.mode.currentIndex==1:
                plane_point=self.ray_plane(k)
                if plane_point is not None:
                    self.model.checkpoint()
                    self.drag=(k,plane_point,self.model.offsets[k].copy())
                return
            if self.mode.currentIndex==2:
                ijk=np.linalg.inv(self.model.planes[k]) @ np.r_[point-self.model.displacement(k),1.]
                i=float(np.clip(ijk[0],0,self.model.dimensions[0]-1))
                j=float(np.clip(ijk[1],0,self.model.dimensions[1]-1))
                try:
                    self.model.add_tag(k,i,j,str(self.note.text))
                    self.changed()
                    self.jump(self.model.position(k,i,j))
                except Exception as exc:
                    self.status.setText('未添加 tag：'+str(exc))
                return
            self.jump(self.model.position(k,(self.model.dimensions[0]-1)/2,(self.model.dimensions[1]-1)/2))
        if self.mode.currentIndex==0:
            self.interactionStyle.OnLeftButtonDown()

    def move(self,*_):
        if self.drag and self.model:
            k,start,offset=self.drag
            point=self.ray_plane(k)
            if point is not None:
                axes=self.model.planes[k][:3,:2]
                axes=axes/np.linalg.norm(axes,axis=0)
                uv=np.linalg.lstsq(axes,point-start,rcond=None)[0]
                self.model.offsets[k]=np.clip(offset+uv,-10000,10000)
                self.refresh()
        else:
            self.interactionStyle.OnMouseMove()

    def release(self,*_):
        if self.drag:
            self.drag=None
            self.changed()
        else:
            self.interactionStyle.OnLeftButtonUp()

    @staticmethod
    def jump(position):
        crosshair=slicer.util.getNode('Crosshair')
        crosshair.SetCrosshairRAS(*position)
        for name in ('Red','Yellow','Green'):
            widget=slicer.app.layoutManager().sliceWidget(name)
            if widget:
                widget.mrmlSliceNode().JumpSliceByCentering(*position)

    def focus_tag(self,*_):
        if not self.model:
            return
        row=self.tagList.currentRow
        if 0<=row<len(self.model.tags):
            tag=self.model.tags[row]
            self.model.selected=tag['slice']
            self.model.hidden.discard(tag['slice'])
            self.model.range=[min(self.model.range[0],tag['slice']),max(self.model.range[1],tag['slice'])]
            self.changed()
            self.jump(self.model.position(tag['slice'],*tag['ij']))

    def edit_tag(self):
        row=self.tagList.currentRow
        if self.model and 0<=row<len(self.model.tags) and str(self.note.text).strip():
            self.model.checkpoint()
            self.model.tags[row]=dict(self.model.tags[row],note=str(self.note.text).strip())
            self.changed()

    def remove_tag(self):
        row=self.tagList.currentRow
        if self.model and 0<=row<len(self.model.tags):
            self.model.checkpoint()
            self.model.tags.pop(row)
            self.changed()

    def save(self):
        if self.model:
            if self.model.error:
                # Corrupt state is read-only, so closing/switching is safe and
                # never overwrites the original record.
                self.status.setText(self.model.error)
                return True
            try:
                self.model.save()
                self.status.setText('已保存到 output/slice-stack；原图坐标未改变。')
                return True
            except Exception as exc:
                self.status.setText('保存失败：'+str(exc))
                return False
        return True

    def closeEvent(self,event):
        self._saveTimer.stop()
        if self.save():
            self.clear_volume()
            event.accept()
        else:
            event.ignore()

    def dispose(self):
        self._saveTimer.stop()
        self.save()
        self.clear_volume()
        for observer in self._observers:
            self.interactionStyle.RemoveObserver(observer)
        self._observers=[]
        self.renderer.RemoveAllViewProps()
        self.view.setMRMLViewNode(None)
        self.view.setMRMLScene(None)
        self.scene.Clear(0)
        self.hide()
        self.deleteLater()


class SliceStackControlsMixin:
    def setupSliceStack(self):
        self._sliceStackInstalled=True
        self._sliceStackWindow=None
        self.sliceStackButton=qt.QPushButton('切片展开')
        self.sliceStackButton.setToolTip('独立窗口按原始采样排列切片；移开遮挡并添加可恢复的 tag。')
        self.sliceStackButton.clicked.connect(self.openSliceStack)
        self.sliceStackButton.enabled=False
        self.attachSliceStackButton()
        slicer.app.layoutManager().layoutChanged.connect(self.attachSliceStackButton)
        slicer.app.aboutToQuit.connect(self.cleanupSliceStack)

    def attachSliceStackButton(self,*_):
        widget=slicer.app.layoutManager().threeDWidget(0)
        if widget:
            controller=widget.threeDController()
            self.sliceStackButton.setParent(controller)
            layout=controller.layout()
            if layout and layout.inherits('QGridLayout'):
                layout.addWidget(self.sliceStackButton,0,layout.columnCount())
            elif layout:
                layout.addWidget(self.sliceStackButton)
            else:
                self.sliceStackButton.setParent(widget.threeDView())
                self.sliceStackButton.move(8,8)
            self.sliceStackButton.show()

    def openSliceStack(self):
        if not self.currentVolume or not self.loadedQuality:
            return
        if self._sliceStackWindow is None:
            self._sliceStackWindow=SliceStackWindow(self)
        self._sliceStackWindow.bind(self.currentVolume,self.loadedQuality)
        self._sliceStackWindow.show()
        self._sliceStackWindow.raise_()
        self._sliceStackWindow.activateWindow()
        qt.QTimer.singleShot(0,self._sliceStackWindow.fit)

    def updateSliceStack(self):
        if not hasattr(self,'sliceStackButton'):
            return
        self.sliceStackButton.enabled=self.nodeIsPresent(self.currentVolume) and bool(self.loadedQuality)
        if self._sliceStackWindow and self._sliceStackWindow.isVisible():
            self._sliceStackWindow.bind(self.currentVolume,self.loadedQuality)

    def cleanupSliceStack(self):
        if not getattr(self,'_sliceStackInstalled',False):
            return
        self._sliceStackInstalled=False
        if self._sliceStackWindow:
            self._sliceStackWindow.dispose()
            self._sliceStackWindow=None
        slicer.app.layoutManager().layoutChanged.disconnect(self.attachSliceStackButton)
        slicer.app.aboutToQuit.disconnect(self.cleanupSliceStack)
        self.sliceStackButton.deleteLater()
