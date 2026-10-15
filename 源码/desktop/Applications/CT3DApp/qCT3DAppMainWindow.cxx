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

// CT3D includes
#include "qCT3DAppMainWindow.h"
#include "qCT3DAppMainWindow_p.h"

// Qt includes
#include <QDesktopWidget>
#include <QLabel>
#include <QDockWidget>
#include <QResizeEvent>
#include <QShowEvent>
#include <QTimer>

// Slicer includes
#include "qSlicerApplication.h"
#include "qSlicerAboutDialog.h"
#include "qSlicerMainWindow_p.h"
#include "qSlicerModuleSelectorToolBar.h"
#include "qMRMLWidget.h"

//-----------------------------------------------------------------------------
// qCT3DAppMainWindowPrivate methods

qCT3DAppMainWindowPrivate::qCT3DAppMainWindowPrivate(qCT3DAppMainWindow& object)
  : Superclass(object)
{
}

//-----------------------------------------------------------------------------
qCT3DAppMainWindowPrivate::~qCT3DAppMainWindowPrivate()
{
}

//-----------------------------------------------------------------------------
void qCT3DAppMainWindowPrivate::init()
{
#if (QT_VERSION >= QT_VERSION_CHECK(5, 7, 0))
  QApplication::setAttribute(Qt::AA_UseHighDpiPixmaps);
#endif
  Q_Q(qCT3DAppMainWindow);
  this->Superclass::init();
}

//-----------------------------------------------------------------------------
void qCT3DAppMainWindowPrivate::setupUi(QMainWindow * mainWindow)
{
  qSlicerApplication * app = qSlicerApplication::application();

  //----------------------------------------------------------------------------
  // Add actions
  //----------------------------------------------------------------------------
  QAction* helpAboutSlicerAppAction = new QAction(mainWindow);
  helpAboutSlicerAppAction->setObjectName("HelpAboutCT3DAppAction");
  helpAboutSlicerAppAction->setText(qCT3DAppMainWindow::tr("About %1").arg(qSlicerApplication::application()->mainApplicationDisplayName()));

  //----------------------------------------------------------------------------
  // Calling "setupUi()" after adding the actions above allows the call
  // to "QMetaObject::connectSlotsByName()" done in "setupUi()" to
  // successfully connect each slot with its corresponding action.
  this->Superclass::setupUi(mainWindow);

  // Add Help Menu Action
  this->HelpMenu->addAction(helpAboutSlicerAppAction);

  //----------------------------------------------------------------------------
  // Configure
  //----------------------------------------------------------------------------
  mainWindow->setWindowIcon(QIcon(":/Icons/Medium/DesktopIcon.png"));

  // Use the default panel title; retain File/Save and editor access.
  // Hide the menus
  //this->menubar->setVisible(false);
  //this->FileMenu->setVisible(false);
  //this->EditMenu->setVisible(false);
  //this->ViewMenu->setVisible(false);
  //this->LayoutMenu->setVisible(false);
  //this->HelpMenu->setVisible(false);
}

//-----------------------------------------------------------------------------
// qCT3DAppMainWindow methods

//-----------------------------------------------------------------------------
qCT3DAppMainWindow::qCT3DAppMainWindow(QWidget* windowParent)
  : Superclass(new qCT3DAppMainWindowPrivate(*this), windowParent)
{
  Q_D(qCT3DAppMainWindow);
  d->init();
}

//-----------------------------------------------------------------------------
qCT3DAppMainWindow::qCT3DAppMainWindow(
  qCT3DAppMainWindowPrivate* pimpl, QWidget* windowParent)
  : Superclass(pimpl, windowParent)
{
  // init() is called by derived class.
}

//-----------------------------------------------------------------------------
qCT3DAppMainWindow::~qCT3DAppMainWindow()
{
}

//-----------------------------------------------------------------------------
void qCT3DAppMainWindow::resizeEvent(QResizeEvent* event)
{
  this->Superclass::resizeEvent(event);
  // Wait until Qt has laid out the central views. Dock dragging remains free;
  // the requested default ratio is reapplied when the whole window is resized.
  QTimer::singleShot(0, this, [this]() { this->applyDefaultPanelRatio(); });
}

//-----------------------------------------------------------------------------
void qCT3DAppMainWindow::showEvent(QShowEvent* event)
{
  this->Superclass::showEvent(event);
  // Initial resize can occur while the window is hidden. Apply the requested
  // ratio on first display as well, including restored window geometries.
  QTimer::singleShot(0, this, [this]() { this->applyDefaultPanelRatio(); });
}

//-----------------------------------------------------------------------------
void qCT3DAppMainWindow::applyDefaultPanelRatio()
{
  Q_D(qCT3DAppMainWindow);
  if (!this->isVisible() || !d->PanelDockWidget ||
      !d->PanelDockWidget->isVisible() || d->PanelDockWidget->isFloating() ||
      !this->centralWidget())
    {
    return;
    }
  const int available = d->PanelDockWidget->width() + this->centralWidget()->width();
  const int leftWidth = qRound(available * 0.618 / 1.618);
  this->resizeDocks({d->PanelDockWidget}, {leftWidth}, Qt::Horizontal);
}

//-----------------------------------------------------------------------------
void qCT3DAppMainWindow::on_HelpAboutCT3DAppAction_triggered()
{
  qSlicerAboutDialog about(this);
  about.setLogo(QPixmap(":/Logo.png"));
  about.exec();
}
