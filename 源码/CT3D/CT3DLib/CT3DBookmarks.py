# -*- coding: utf-8 -*-
"""Lightweight session bookmarks: view nodes only, never volume pixels."""
import math
import ctk
import qt
import slicer
import vtk


class BookmarkControlsMixin:
    def setupBookmarkControls(self, root):
        self._bookmarks = []
        box = ctk.ctkCollapsibleButton()
        box.text = "关注位置收藏（本次会话）"
        layout = qt.QVBoxLayout(box)
        hint = qt.QLabel("先按住 Shift 在切片上定位，再填写备注并收藏。单击列表返回来源序列及显示状态。关闭或清空场景后收藏不保留。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.bookmarkNote = qt.QLineEdit()
        self.bookmarkNote.setPlaceholderText("结构或关注点备注；请勿填写患者身份信息")
        self.bookmarkNote.setMaxLength(160)
        layout.addWidget(self.bookmarkNote)
        self.addBookmarkButton = qt.QPushButton("收藏当前位置与视图")
        self.addBookmarkButton.clicked.connect(self.onAddBookmark)
        layout.addWidget(self.addBookmarkButton)
        self.bookmarkList = qt.QListWidget()
        self.bookmarkList.setMaximumHeight(150)
        self.bookmarkList.itemClicked.connect(self.onBookmarkClicked)
        layout.addWidget(self.bookmarkList)
        self.removeBookmarkButton = qt.QPushButton("删除选中收藏")
        self.removeBookmarkButton.clicked.connect(self.onRemoveBookmark)
        layout.addWidget(self.removeBookmarkButton)
        root.addWidget(box)
        self.updateBookmarkState()

    def updateBookmarkState(self):
        self.addBookmarkButton.enabled = self.nodeIsPresent(self.currentVolume) and bool(self.loadedQuality) and not self._loading
        self.removeBookmarkButton.enabled = bool(self._bookmarks)

    @staticmethod
    def _bookmarkCopy(node):
        # NewInstance carries VTK_NEWINSTANCE ownership metadata. The MRML
        # CreateNodeInstance wrapper leaves its initial C++ reference owned
        # by the caller, leaking detached snapshots when only Python releases them.
        copy = node.NewInstance()
        copy.CopyContent(node)
        return copy

    @staticmethod
    def _bookmarkGeometry(volume):
        matrix = vtk.vtkMatrix4x4()
        volume.GetIJKToRASMatrix(matrix)
        transforms = []
        parent = volume.GetParentTransformNode()
        while parent:
            # Observe transform data rather than unrelated node visibility/name changes.
            transforms.append((parent.GetID(), parent.GetTransformToParent().GetMTime()))
            parent = parent.GetParentTransformNode()
        return (tuple(matrix.GetElement(r, c) for r in range(4) for c in range(4)),
                volume.GetImageData().GetDimensions(), volume.GetImageData().GetMTime(), tuple(transforms))

    def captureBookmark(self, note):
        if not self.nodeIsPresent(self.currentVolume) or not self.loadedQuality or self._loading:
            raise RuntimeError("请先载入序列。")
        manager = slicer.app.layoutManager()
        if manager.layout != 501:
            raise RuntimeError("请先恢复 CT3D 四视图布局。")
        volume = self.currentVolume
        ras = tuple(self.crosshairNode().GetCrosshairRAS())
        if not all(math.isfinite(v) for v in ras):
            raise RuntimeError("十字线坐标无效，请重新定位。")
        worldToLocal = vtk.vtkGeneralTransform()
        slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(None, volume.GetParentTransformNode(), worldToLocal)
        matrix = vtk.vtkMatrix4x4()
        volume.GetRASToIJKMatrix(matrix)
        ijk = matrix.MultiplyPoint(list(worldToLocal.TransformPoint(ras)) + [1])
        if any(v < -0.5 or v > d - 0.5 for v, d in zip(ijk, volume.GetImageData().GetDimensions())):
            raise RuntimeError("十字线位于影像范围之外；请按住 Shift 在切片内重新定位。")
        cameraNode = slicer.modules.cameras.logic().GetViewActiveCameraNode(manager.threeDWidget(0).mrmlViewNode())
        camera = vtk.vtkCamera()
        camera.DeepCopy(cameraNode.GetCamera())
        state = {
            "note": note.strip() or "关注位置",
            "session": self.currentSession().copy(), "ras": ras,
            "geometry": self._bookmarkGeometry(volume),
            "display": self._bookmarkCopy(volume.GetDisplayNode()),
            "slices": {n: self._bookmarkCopy(manager.sliceWidget(n).mrmlSliceNode()) for n in ("Red", "Yellow", "Green")},
            "camera": camera,
            "flags": {n: getattr(self, n).checked for n in ("crosshairCheck", "slicePlanesCheck", "commonScaleCheck", "renderCheck", "cropCheck", "roiVisibleCheck", "renderSmoothingCheck")},
            "indexes": {n: getattr(self, n).currentIndex for n in ("planeCombo", "smoothInterpolationCombo", "renderQualityCombo", "renderPresetCombo")},
            "vr": None, "property": None, "roi": None,
        }
        if self.nodeIsPresent(self.currentVRDisplay):
            state["vr"] = self._bookmarkCopy(self.currentVRDisplay)
            prop = self.currentVRDisplay.GetVolumePropertyNode()
            state["property"] = self._bookmarkCopy(prop) if prop else None
            roi = self.currentVRDisplay.GetMarkupsROINode()
            state["roi"] = self._bookmarkCopy(roi) if roi else None
        return state

    def onAddBookmark(self):
        try:
            if len(self._bookmarks) >= 100:
                raise RuntimeError("本次会话最多保存 100 个关注位置，请删除不再需要的收藏。")
            state = self.captureBookmark(str(self.bookmarkNote.text))
            self._bookmarks.append(state)
            info = state["session"]["quality"]
            label = f"{info.get('displayCode', info['modality'])} · {state['note']}"
            item = qt.QListWidgetItem(label)
            item.setToolTip("世界 RAS（mm）：" + ", ".join(f"{v:.2f}" for v in state["ras"]))
            self.bookmarkList.addItem(item)
            self.bookmarkNote.clear()
            self.updateBookmarkState()
            self.statusLabel.text = "已收藏当前位置与显示状态；未复制或修改影像像素。"
            return state
        except Exception as exc:
            self.showError("收藏失败：\n" + str(exc))

    def restoreBookmark(self, state):
        target = state["session"]
        volume = target["volume"]
        if self._loading:
            raise RuntimeError("正在载入序列，请稍后返回收藏。")
        if not self.nodeIsPresent(volume):
            raise RuntimeError("收藏的来源影像已移除，请重新载入并定位；不会返回其他序列。")
        if state["geometry"] != self._bookmarkGeometry(volume):
            raise RuntimeError("来源影像或空间变换已改变，请重新核对并收藏该位置。")
        if state["vr"] and (not self.nodeIsPresent(target["vr"]) or not target["vr"].GetVolumePropertyNode() or (state["roi"] and not target["vr"].GetMarkupsROINode())):
            raise RuntimeError("收藏所需的三维显示节点已移除，请重新收藏。")
        self.stopMeasurementPlacement()
        old = self.currentSession()
        if old:
            self._sessions[old["quality"]["uid"]] = old
            self.setSessionVisibility(old, False)
        self.detachDisplayObserver()
        self.restoreSession(target)
        self.showVolume(volume, initialize=False)
        manager = slicer.app.layoutManager()
        composites = [manager.sliceWidget(n).sliceLogic().GetSliceCompositeNode() for n in ("Red", "Yellow", "Green")]
        linked = [n.GetLinkedControl() for n in composites]
        try:
            for node in composites:
                node.SetLinkedControl(False)
            for name, value in state["flags"].items():
                control = getattr(self, name)
                control.blockSignals(True)
                control.checked = value
                control.blockSignals(False)
            for name, value in state["indexes"].items():
                control = getattr(self, name)
                control.blockSignals(True)
                control.setCurrentIndex(value)
                control.blockSignals(False)
            volume.GetDisplayNode().CopyContent(state["display"])
            if state["vr"]:
                self.currentVRDisplay.CopyContent(state["vr"])
                self.currentVRDisplay.GetVolumePropertyNode().CopyContent(state["property"])
                if state["roi"]:
                    roi = self.currentVRDisplay.GetMarkupsROINode()
                    roi.CopyContent(state["roi"])
                    roi.GetDisplayNode().SetVisibility(state["flags"]["roiVisibleCheck"])
            self.onCrosshairToggled(state["flags"]["crosshairCheck"])
            self.applyDisplayInterpolation()
            self.applyRenderingQuality()
            for name, saved in state["slices"].items():
                node = manager.sliceWidget(name).mrmlSliceNode()
                node.CopyContent(saved)
                node.UpdateMatrices()
            self.crosshairNode().SetCrosshairRAS(state["ras"])
            cameraNode = slicer.modules.cameras.logic().GetViewActiveCameraNode(manager.threeDWidget(0).mrmlViewNode())
            cameraNode.GetCamera().DeepCopy(state["camera"])
            cameraNode.Modified()
        finally:
            for node, value in zip(composites, linked):
                node.SetLinkedControl(value)
        self.setSessionVisibility(self.currentSession(), True)
        self.updateReviewState()
        if self._viewLabels:
            self._viewLabels.update()
        slicer.util.forceRenderAllViews()
        self.statusLabel.text = "已返回收藏：" + state["note"] + "。已恢复来源序列、定位及显示状态。"

    def onBookmarkClicked(self, item):
        index = self.bookmarkList.row(item)
        if 0 <= index < len(self._bookmarks):
            try:
                self.restoreBookmark(self._bookmarks[index])
            except Exception as exc:
                self.showError("无法返回收藏：\n" + str(exc))

    def onRemoveBookmark(self):
        row = self.bookmarkList.currentRow
        if 0 <= row < len(self._bookmarks):
            self._bookmarks.pop(row)
            self.bookmarkList.takeItem(row)
        self.updateBookmarkState()

    def clearBookmarks(self):
        self._bookmarks.clear()
        self.bookmarkList.clear()
        self.updateBookmarkState()
