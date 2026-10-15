/*==============================================================================

  Copyright (c) Kitware, Inc.

  See http://www.slicer.org/copyright/copyright.txt for details.

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  This file was originally developed by Julien Finet, Kitware, Inc.
  and was partially funded by NIH grant 3P41RR013218-12S1

==============================================================================*/

#ifndef __qCT3DAppMainWindow_h
#define __qCT3DAppMainWindow_h

// CT3D includes
#include "qCT3DAppExport.h"
class qCT3DAppMainWindowPrivate;
class QResizeEvent;
class QShowEvent;

// Slicer includes
#include "qSlicerMainWindow.h"

class Q_CT3D_APP_EXPORT qCT3DAppMainWindow : public qSlicerMainWindow
{
  Q_OBJECT
public:
  typedef qSlicerMainWindow Superclass;

  qCT3DAppMainWindow(QWidget *parent=0);
  virtual ~qCT3DAppMainWindow();

public slots:
  void on_HelpAboutCT3DAppAction_triggered();

protected:
  qCT3DAppMainWindow(qCT3DAppMainWindowPrivate* pimpl, QWidget* parent);
  void resizeEvent(QResizeEvent* event) override;
  void showEvent(QShowEvent* event) override;

private:
  void applyDefaultPanelRatio();
  Q_DECLARE_PRIVATE(qCT3DAppMainWindow);
  Q_DISABLE_COPY(qCT3DAppMainWindow);
};

#endif
