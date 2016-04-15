#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extracting 2D and 3D points with subsequent 2D to 3D correlation.
This module can be run as a standalone python application, but is best paired
with the preceding data processing (cubing voxels, merge single image files
to one single stack file, ...).

# @Title			: TDCT_correlation
# @Project			: 3DCTv2
# @Description		: Extracting 2D and 3D points for 2D to 3D correlation
# @Author			: Jan Arnold
# @Email			: jan.arnold (at) coraxx.net
# @Copyright		: Copyright (C) 2016  Jan Arnold
# @License			: GPLv3 (see LICENSE file)
# @Credits			:
# @Maintainer		: Jan Arnold
# @Date				: 2016/01
# @Version			: 3DCT 2.0.0 module rev. 1
# @Status			: beta
# @Usage			: part of 3D Correlation Toolbox
# @Notes			:
# @Python_version	: 2.7.11
"""
# ======================================================================================================================


import sys
import os
import time
import re
import tempfile
from PyQt4 import QtCore, QtGui, uic
import numpy as np
import cv2
import tifffile as tf
## Colored stdout, custom Qt functions (mostly to handle events), CSV handler
## and correlation algorithm
from tdct import clrmsg, QtCustom, csvHandler, correlation

__version__ = 'v2.0.0'

# add working directory temporarily to PYTHONPATH
if getattr(sys, 'frozen', False):
	# program runs in a bundle (pyinstaller)
	execdir = sys._MEIPASS
else:
	execdir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(execdir)

qtCreatorFile_main = os.path.join(execdir, "TDCT_correlation.ui")
Ui_WidgetWindow, QtBaseClass = uic.loadUiType(qtCreatorFile_main)

debug = True
if debug is True: print clrmsg.DEBUG + "Execdir =", execdir


class MainWidget(QtGui.QMainWindow, Ui_WidgetWindow):
	def __init__(self, parent=None, leftImage=None, rightImage=None,workingdir=None):
		if debug is True: print clrmsg.DEBUG + 'Debug messages enabled'
		QtGui.QWidget.__init__(self)
		Ui_WidgetWindow.__init__(self)
		self.setupUi(self)
		self.parent = parent
		self.counter = 0		# Just for testing (loop counter for test button)
		self.refreshUI = QtGui.QApplication.processEvents
		self.currentFocusedWidgetName = QtGui.QApplication.focusWidget()
		if workingdir is None:
			self.workingdir = execdir
		else:
			self.workingdir = workingdir
		self.lineEdit_workingDir.setText(self.workingdir)

		## Stylesheet colors:
		self.stylesheet_orange = "color: rgb(255, 120,   0);"
		self.stylesheet_green = "color:  rgb(  0, 200,   0);"
		self.stylesheet_blue = "color:   rgb(  0, 190, 255);"
		self.stylesheet_red = "color:    rgb(255,   0,   0);"

		## Tableview and models
		self.modelLleft = QtCustom.QStandardItemModelCustom(self)
		self.tableView_left.setModel(self.modelLleft)
		self.modelLleft.tableview = self.tableView_left

		self.modelRight = QtCustom.QStandardItemModelCustom(self)
		self.tableView_right.setModel(self.modelRight)
		self.modelRight.tableview = self.tableView_right

		self.modelResults = QtGui.QStandardItemModel(self)
		self.modelResultsProxy = QtCustom.NumberSortModel()
		self.modelResultsProxy.setSourceModel(self.modelResults)
		self.tableView_results.setModel(self.modelResultsProxy)

		## store parameters for resizing
		self.parent = parent
		self.size = 500
		self.leftImage = leftImage
		self.rightImage = rightImage

		## Initialize parameters
		self.brightness_left = 0
		self.contrast_left = 10
		self.brightness_right = 0
		self.contrast_right = 10
		## Initialize Images and connect image load buttons
		self.toolButton_loadLeftImage.clicked.connect(self.openImageLeft)
		self.toolButton_loadRightImage.clicked.connect(self.openImageRight)
		if leftImage is None or rightImage is None:
			return
		self.initImageLeft()
		self.initImageRight()

		## connect item change signal to write changes in model back to QGraphicItems as well as highlighting selected points
		self.modelLleft.itemChanged.connect(self.tableView_left.updateItems)
		self.modelRight.itemChanged.connect(self.tableView_right.updateItems)
		self.tableView_left.selectionModel().selectionChanged.connect(self.tableView_left.showSelectedItem)
		self.tableView_right.selectionModel().selectionChanged.connect(self.tableView_right.showSelectedItem)
		self.tableView_results.selectionModel().selectionChanged.connect(self.showSelectedResidual)
		self.tableView_results.doubleClicked.connect(lambda: self.showSelectedResidual(doubleclick=True))

		# SpinBoxes
		self.spinBox_rot.valueChanged.connect(self.rotateImage)
		self.spinBox_markerSize.valueChanged.connect(self.changeMarkerSize)
		self.doubleSpinBox_scatterPlotFrameSize.valueChanged.connect(lambda: self.displayResults(
																frame=self.checkBox_scatterPlotFrame.isChecked(),
																framesize=self.doubleSpinBox_scatterPlotFrameSize.value()))

		## Checkboxes
		self.checkBox_scatterPlotFrame.stateChanged.connect(lambda: self.displayResults(
																frame=self.checkBox_scatterPlotFrame.isChecked(),
																framesize=self.doubleSpinBox_scatterPlotFrameSize.value()))
		self.checkBox_resultsAbsolute.stateChanged.connect(lambda: self.displayResults(
																frame=self.checkBox_scatterPlotFrame.isChecked(),
																framesize=self.doubleSpinBox_scatterPlotFrameSize.value()))

		## Buttons
		self.toolButton_rotcw.clicked.connect(lambda: self.rotateImage45(direction='cw'))
		self.toolButton_rotccw.clicked.connect(lambda: self.rotateImage45(direction='ccw'))
		self.toolButton_brightness_reset.clicked.connect(lambda: self.horizontalSlider_brightness.setValue(0))
		self.toolButton_contrast_reset.clicked.connect(lambda: self.horizontalSlider_contrast.setValue(10))
		self.toolButton_importPoints.clicked.connect(self.importPoints)
		self.toolButton_exportPoints.clicked.connect(self.exportPoints)
		self.toolButton_selectWorkingDir.clicked.connect(self.selectWorkingDir)
		self.commandLinkButton_correlate.clicked.connect(self.correlate)

		## Sliders
		self.horizontalSlider_brightness.valueChanged.connect(self.adjustBrightCont)
		self.horizontalSlider_contrast.valueChanged.connect(self.adjustBrightCont)
		## Capture focus change events
		QtCore.QObject.connect(QtGui.QApplication.instance(), QtCore.SIGNAL("focusChanged(QWidget *, QWidget *)"), self.changedFocusSlot)

		## Pass models and scenes to tableview for easy access
		self.tableView_left._model = self.modelLleft
		self.tableView_right._model = self.modelRight
		self.tableView_left._scene = self.sceneLeft
		self.tableView_right._scene = self.sceneRight

		self.tableView_results.setContextMenuPolicy(3)
		self.tableView_results.customContextMenuRequested.connect(self.cmTableViewResults)

		self.lineEdit_workingDir.textChanged.connect(self.updateWorkingDir)

	def keyPressEvent(self,event):
		"""Filter key press event
		Selected table rows can be deleted by pressing the "Del" key
		"""
		if event.key() == QtCore.Qt.Key_Delete:
			if self.currentFocusedWidgetName == 'tableView_left':
				if debug is True: print clrmsg.DEBUG + "Deleting item(s) on the left side"
				# self.deleteItem(self.tableView_left,self.modelLleft,self.sceneLeft)
				self.tableView_left.deleteItem()
				# self.updateItems(self.modelLleft,self.sceneLeft)
				self.tableView_left.updateItems()
			elif self.currentFocusedWidgetName == 'tableView_right':
				if debug is True: print clrmsg.DEBUG + "Deleting item(s) on the right side"
				# self.deleteItem(self.tableView_right,self.modelRight,self.sceneRight)
				self.tableView_right.deleteItem()
				# self.updateItems(self.modelRight,self.sceneRight)
				self.tableView_right.updateItems()

	def closeEvent(self, event):
		"""Warning when closing application to prevent unintentional quitting with reminder to save data"""
		quit_msg = "Are you sure you want to exit the\n3DCT Correlation?\n\nUnsaved data will be lost!"
		reply = QtGui.QMessageBox.question(self, 'Message', quit_msg, QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
		if reply == QtGui.QMessageBox.Yes:
			event.accept()
			if self.parent:
				self.parent.cleanUp()
				self.parent.exitstatus = 0
		else:
			event.ignore()
			if self.parent:
				self.parent.exitstatus = 1

	def selectWorkingDir(self):
		path = str(QtGui.QFileDialog.getExistingDirectory(self, "Select working directory", self.workingdir))
		if path:
			workingdir = self.checkWorkingDirPrivileges(path)
			if workingdir:
				self.workingdir = workingdir
			self.lineEdit_workingDir.setText(self.workingdir)

	def updateWorkingDir(self):
		if os.path.isdir(self.lineEdit_workingDir.text()):
			workingdir = self.checkWorkingDirPrivileges(str(self.lineEdit_workingDir.text()))
			if workingdir:
				self.workingdir = workingdir
			self.lineEdit_workingDir.setText(self.workingdir)
			print 'updated working dir to:', self.workingdir
		else:
			self.lineEdit_workingDir.setText(self.workingdir)
			print clrmsg.ERROR + "Dropped object is not a valid path. Returning to {0} as working directory.".format(self.workingdir)

	def checkWorkingDirPrivileges(self,path):
		try:
			testfile = tempfile.TemporaryFile(dir=path)
			testfile.close()
			return path
		except Exception:
			QtGui.QMessageBox.critical(
				self,"Warning",
				"I cannot write to this folder: {0}\nFalling back to {1} as the working directory".format(path, self.workingdir))
			return None

	def changedFocusSlot(self, former, current):
		if debug is True: print clrmsg.DEBUG + "focus changed from/to:", former.objectName() if former else former, \
				current.objectName() if current else current
		if current:
			self.currentFocusedWidgetName = current.objectName()
			self.currentFocusedWidget = current
		if former:
			self.formerFocusedWidgetName = former.objectName()
			self.formerFocusedWidget = former

		## Label showing selected image
		if self.currentFocusedWidgetName in ['spinBox_rot','spinBox_markerSize','horizontalSlider_brightness','horizontalSlider_contrast']:
			pass
		else:
			if self.currentFocusedWidgetName != 'graphicsView_left' and self.currentFocusedWidgetName != 'graphicsView_right':
				self.label_selimg.setStyleSheet(self.stylesheet_orange)
				self.label_selimg.setText('none')
				self.label_markerSizeNano.setText('')
				self.label_markerSizeNanoUnit.setText('')
				self.label_imgpxsize.setText('')
				self.label_imgpxsizeUnit.setText('')
				self.label_imagetype.setText('')
				self.ctrlEnDisAble(False)
			elif self.currentFocusedWidgetName == 'graphicsView_left':
				self.label_selimg.setStyleSheet(self.stylesheet_green)
				self.label_selimg.setText('left')
				self.label_imagetype.setStyleSheet(self.stylesheet_green)
				self.label_imagetype.setText('(2D)' if '{0:b}'.format(self.sceneLeft.imagetype)[-1] == '1' else '(3D)')
				self.ctrlEnDisAble(True)
			elif self.currentFocusedWidgetName == 'graphicsView_right':
				self.label_selimg.setStyleSheet(self.stylesheet_blue)
				self.label_selimg.setText('right')
				self.label_imagetype.setStyleSheet(self.stylesheet_blue)
				self.label_imagetype.setText('(2D)' if '{0:b}'.format(self.sceneRight.imagetype)[-1] == '1' else '(3D)')
				self.ctrlEnDisAble(True)

		# ## Label showing selected table
		if self.currentFocusedWidgetName != 'tableView_left' and self.currentFocusedWidgetName != 'tableView_right':
			self.label_selectedTable.setStyleSheet(self.stylesheet_orange)
			self.label_selectedTable.setText('none')
			self.ctrlEnDisAble(True)
		elif self.currentFocusedWidgetName == 'tableView_left':
			self.label_selectedTable.setStyleSheet(self.stylesheet_green)
			self.label_selectedTable.setText('left')
			self.ctrlEnDisAble(False)
		elif self.currentFocusedWidgetName == 'tableView_right':
			self.label_selectedTable.setStyleSheet(self.stylesheet_blue)
			self.label_selectedTable.setText('right')
			self.ctrlEnDisAble(False)

		## Feed saved rotation angle/brightness-contrast value from selected image to spinbox/slider
		# Block emitting signals for correct setting of BOTH sliders. Otherwise the second one gets overwritten with the old value
		self.horizontalSlider_brightness.blockSignals(True)
		self.horizontalSlider_contrast.blockSignals(True)
		if self.currentFocusedWidgetName == 'graphicsView_left':
			self.spinBox_rot.setValue(self.sceneLeft.rotangle)
			self.spinBox_markerSize.setValue(self.sceneLeft.markerSize)
			self.horizontalSlider_brightness.setValue(self.brightness_left)
			self.horizontalSlider_contrast.setValue(self.contrast_left)
			self.label_imgpxsize.setText(str(self.sceneLeft.pixelSize))  # + ' um') # breaks marker size adjustments check
			self.label_imgpxsizeUnit.setText('um') if self.sceneLeft.pixelSize else self.label_imgpxsizeUnit.setText('')
		elif self.currentFocusedWidgetName == 'graphicsView_right':
			self.spinBox_rot.setValue(self.sceneRight.rotangle)
			self.spinBox_markerSize.setValue(self.sceneRight.markerSize)
			self.horizontalSlider_brightness.setValue(self.brightness_right)
			self.horizontalSlider_contrast.setValue(self.contrast_right)
			self.label_imgpxsize.setText(str(self.sceneRight.pixelSize))  # + ' um') # breaks marker size adjustments check
			self.label_imgpxsizeUnit.setText('um') if self.sceneRight.pixelSize else self.label_imgpxsizeUnit.setText('')
		# Unblock emitting signals.
		self.horizontalSlider_brightness.blockSignals(False)
		self.horizontalSlider_contrast.blockSignals(False)
		# update marker size in nm
		self.changeMarkerSize()

	## Function to dis-/enabling the buttons controlling rotation and contrast/brightness
	def ctrlEnDisAble(self,status):
		self.spinBox_rot.setEnabled(status)
		self.spinBox_markerSize.setEnabled(status)
		self.horizontalSlider_brightness.setEnabled(status)
		self.horizontalSlider_contrast.setEnabled(status)
		self.toolButton_brightness_reset.setEnabled(status)
		self.toolButton_contrast_reset.setEnabled(status)
		self.toolButton_rotcw.setEnabled(status)
		self.toolButton_rotccw.setEnabled(status)
		self.toolButton_importPoints.setEnabled(not status)
		self.toolButton_exportPoints.setEnabled(not status)

	def colorModels(self):
		rowsLeft = self.modelLleft.rowCount()
		rowsRight = self.modelRight.rowCount()
		alpha = 100
		for row in range(min([rowsLeft,rowsRight])):
			color_correlate = (50,220,175,alpha)
			if rowsLeft != 0:
				self.modelLleft.item(row, 0).setBackground(QtGui.QColor(*color_correlate))
				self.modelLleft.item(row, 1).setBackground(QtGui.QColor(*color_correlate))
				self.modelLleft.item(row, 2).setBackground(QtGui.QColor(*color_correlate))
			if rowsRight != 0:
				self.modelRight.item(row, 0).setBackground(QtGui.QColor(*color_correlate))
				self.modelRight.item(row, 1).setBackground(QtGui.QColor(*color_correlate))
				self.modelRight.item(row, 2).setBackground(QtGui.QColor(*color_correlate))
		if rowsLeft > rowsRight:
			if '{0:b}'.format(self.sceneLeft.imagetype)[-1] == '0':
				color_overflow = (105,220,0,alpha)  # green if entries are used as POIs
			else:
				color_overflow = (220,25,105,alpha)  # red(ish) color to indicate unbalanced amount of markers for correlation
			for row in range(rowsRight,rowsLeft):
				self.modelLleft.item(row, 0).setBackground(QtGui.QColor(*color_overflow))
				self.modelLleft.item(row, 1).setBackground(QtGui.QColor(*color_overflow))
				self.modelLleft.item(row, 2).setBackground(QtGui.QColor(*color_overflow))
		elif rowsLeft < rowsRight:
			if '{0:b}'.format(self.sceneRight.imagetype)[-1] == '0':
				color_overflow = (105,220,0,alpha)  # green if entries are used as POIs
			else:
				color_overflow = (220,25,105,alpha)  # red(ish) color to indicate unbalanced amount of markers for correlation
			for row in range(rowsLeft,rowsRight):
				self.modelRight.item(row, 0).setBackground(QtGui.QColor(*color_overflow))
				self.modelRight.item(row, 1).setBackground(QtGui.QColor(*color_overflow))
				self.modelRight.item(row, 2).setBackground(QtGui.QColor(*color_overflow))

												###############################################
												###### Image initialization and rotation ######
												#################### START ####################
	def initImageLeft(self):
		if self.leftImage is not None:
			## Changed GraphicsSceneLeft(self) to QtCustom.QGraphicsSceneCustom(self.graphicsView_left) to reuse class for both scenes
			self.sceneLeft = QtCustom.QGraphicsSceneCustom(self.graphicsView_left,mainWidget=self,side='left',model=self.modelLleft)
			## set pen color yellow
			self.sceneLeft.pen = QtGui.QPen(QtCore.Qt.red)
			## Splash screen message
			try:
				splashscreen.splash.showMessage("Loading images... "+self.leftImage,color=QtCore.Qt.white)
			except Exception as e:
				print clrmsg.WARNING, e
				pass
			QtGui.QApplication.processEvents()
			## Get pixel size
			self.sceneLeft.pixelSize = self.pxSize(self.leftImage)
			self.sceneLeft.pixelSizeUnit = 'um'
			## Load image, assign it to scene and store image type information
			self.img_left,self.sceneLeft.imagetype,self.imgstack_left = self.imread(self.leftImage)
			self.img_left_displayed = np.copy(self.img_left)
			## link image to QTableview for determining z
			self.tableView_left.img = self.imgstack_left
			## check if coloring z values in table is needed (correlation needs z=0 in 2D image, so no checking for valid z
			## with 2D images needed)
			if self.imgstack_left is None:
				self.sceneLeft._z = False
			else:
				self.sceneLeft._z = True
				self.setCustomRotCenter(max(self.imgstack_left.shape))
			# self.pixmap_left = QtGui.QPixmap(self.leftImage)
			self.pixmap_left = self.cv2Qimage(self.img_left_displayed)
			self.pixmap_item_left = QtGui.QGraphicsPixmapItem(self.pixmap_left, None, self.sceneLeft)
			## connect scenes to GUI elements
			self.graphicsView_left.setScene(self.sceneLeft)
			## reset scaling (needed for reinitialization)
			self.graphicsView_left.resetMatrix()
			## scaling scene, not image
			scaling_factor = float(self.size)/max(self.pixmap_left.width(), self.pixmap_left.height())
			self.graphicsView_left.scale(scaling_factor,scaling_factor)

	def initImageRight(self):
		if self.rightImage is not None:
			self.sceneRight = QtCustom.QGraphicsSceneCustom(self.graphicsView_right,mainWidget=self,side='right',model=self.modelRight)
			## set pen color yellow
			self.sceneRight.pen = QtGui.QPen(QtCore.Qt.yellow)
			## Splash screen message
			try:
				splashscreen.splash.showMessage("Loading images... "+self.rightImage,color=QtCore.Qt.white)
			except Exception as e:
				print clrmsg.WARNING, e
				pass
			QtGui.QApplication.processEvents()
			## Get pixel size
			self.sceneRight.pixelSize = self.pxSize(self.rightImage)
			self.sceneRight.pixelSizeUnit = 'um'
			## Load image, assign it to scene and store image type information
			self.img_right,self.sceneRight.imagetype,self.imgstack_right = self.imread(self.rightImage)
			self.img_right_displayed = np.copy(self.img_right)
			## link image to QTableview for determining z
			self.tableView_right.img = self.imgstack_right
			## check if coloring z values in table is needed (correlation needs z=0 in 2D image, so no checking for valid z
			## with 2D images needed)
			if self.imgstack_right is None:
				self.sceneRight._z = False
			else:
				self.sceneRight._z = True
				self.setCustomRotCenter(max(self.imgstack_right.shape))
			# self.pixmap_right = QtGui.QPixmap(self.rightImage)
			self.pixmap_right = self.cv2Qimage(self.img_right_displayed)
			self.pixmap_item_right = QtGui.QGraphicsPixmapItem(self.pixmap_right, None, self.sceneRight)
			## connect scenes to GUI elements
			self.graphicsView_right.setScene(self.sceneRight)
			## reset scaling (needed for reinitialization)
			self.graphicsView_right.resetMatrix()
			## scaling scene, not image
			scaling_factor = float(self.size)/max(self.pixmap_right.width(), self.pixmap_right.height())
			self.graphicsView_right.scale(scaling_factor,scaling_factor)

	def openImageLeft(self):
		## *.png *.jpg *.bmp not yet supported
		path = str(QtGui.QFileDialog.getOpenFileName(
			None,"Select image file for correlation", self.workingdir,"Image Files (*.tif *.tiff);; All (*.*)"))
		if path != '':
			self.leftImage = path
			self.initImageLeft()
			self.tableView_left._scene = self.sceneLeft
			for i in range(self.tableView_left._model.rowCount()):
				self.sceneLeft.addCircle(0.0,0.0,0.0)
			self.tableView_left.updateItems()

	def openImageRight(self):
		## *.png *.jpg *.bmp not yet supported
		path = str(QtGui.QFileDialog.getOpenFileName(
			None,"Select image file for correlation", self.workingdir,"Image Files (*.tif *.tiff);; All (*.*)"))
		if path != '':
			self.rightImage = path
			self.initImageRight()
			self.tableView_right._scene = self.sceneRight
			for i in range(self.tableView_right._model.rowCount()):
				self.sceneRight.addCircle(0.0,0.0,0.0)
			self.tableView_right.updateItems()

	def rotateImage(self):
		if self.label_selimg.text() == 'left':
			if int(self.spinBox_rot.value()) == 360:
				self.spinBox_rot.setValue(0)
			elif int(self.spinBox_rot.value()) == -1:
				self.spinBox_rot.setValue(359)
			self.graphicsView_left.rotate(int(self.spinBox_rot.value())-self.sceneLeft.rotangle)
			self.sceneLeft.rotangle = int(self.spinBox_rot.value())
			## Update graphics
			self.sceneLeft.enumeratePoints()
		elif self.label_selimg.text() == 'right':
			if int(self.spinBox_rot.value()) == 360:
				self.spinBox_rot.setValue(0)
			elif int(self.spinBox_rot.value()) == -1:
				self.spinBox_rot.setValue(359)
			self.graphicsView_right.rotate(int(self.spinBox_rot.value())-self.sceneRight.rotangle)
			self.sceneRight.rotangle = int(self.spinBox_rot.value())
			## Update graphics
			self.sceneRight.enumeratePoints()

	def rotateImage45(self,direction=None):
		if direction is None:
			print clrmsg.ERROR + "Please specify direction ('cw' or 'ccw')."
		# rotate 45 degree clockwise
		elif direction == 'cw':
			if self.label_selimg.text() == 'left':
				self.sceneLeft.rotangle = self.sceneLeft.rotangle+45
				self.graphicsView_left.rotate(45)
				self.sceneLeft.rotangle = self.anglectrl(angle=self.sceneLeft.rotangle)
				self.spinBox_rot.setValue(self.sceneLeft.rotangle)
				## Update graphics
				self.sceneLeft.enumeratePoints()
			elif self.label_selimg.text() == 'right':
				self.sceneRight.rotangle = self.sceneRight.rotangle+45
				self.graphicsView_right.rotate(45)
				self.sceneRight.rotangle = self.anglectrl(angle=self.sceneRight.rotangle)
				self.spinBox_rot.setValue(self.sceneRight.rotangle)
				## Update graphics
				self.sceneRight.enumeratePoints()
		# rotate 45 degree anticlockwise
		elif direction == 'ccw':
			if self.label_selimg.text() == 'left':
				self.sceneLeft.rotangle = self.sceneLeft.rotangle-45
				self.graphicsView_left.rotate(-45)
				self.sceneLeft.rotangle = self.anglectrl(angle=self.sceneLeft.rotangle)
				self.spinBox_rot.setValue(self.sceneLeft.rotangle)
			elif self.label_selimg.text() == 'right':
				self.sceneRight.rotangle = self.sceneRight.rotangle-45
				self.graphicsView_right.rotate(-45)
				self.sceneRight.rotangle = self.anglectrl(angle=self.sceneRight.rotangle)
				self.spinBox_rot.setValue(self.sceneRight.rotangle)

	def anglectrl(self,angle=None):
		if angle is None:
			print clrmsg.ERROR + "Please specify side, e.g. anglectrl(angle=self.sceneLeft.rotangle)"
		elif angle >= 360:
			angle = angle-360
		elif angle < 0:
			angle = angle+360
		return angle

	def changeMarkerSize(self):
		if self.label_selimg.text() == 'left':
			self.sceneLeft.markerSize = int(self.spinBox_markerSize.value())
			## Update graphics
			self.sceneLeft.enumeratePoints()
			if self.sceneLeft.pixelSize:
				if debug is True: print clrmsg.DEBUG + "Doing stuff with image pixelSize (left image).", self.label_imgpxsize.text()
				try:
					self.label_markerSizeNano.setText(str(self.sceneLeft.markerSize*2*self.sceneLeft.pixelSize))
					self.label_markerSizeNanoUnit.setText(self.sceneLeft.pixelSizeUnit)
				except:
					if debug is True: print clrmsg.DEBUG + "Image pixel size is not a number:", self.label_imgpxsize.text()
					self.label_markerSizeNano.setText("NaN")
					self.label_markerSizeNanoUnit.setText('')
			else:
				self.label_markerSizeNano.setText('')
				self.label_markerSizeNanoUnit.setText('')
		elif self.label_selimg.text() == 'right':
			self.sceneRight.markerSize = int(self.spinBox_markerSize.value())
			## Update graphics
			self.sceneRight.enumeratePoints()
			if self.sceneRight.pixelSize:
				if debug is True: print clrmsg.DEBUG + "Doing stuff with image pixelSize (right image).", self.label_imgpxsize.text()
				try:
					self.label_markerSizeNano.setText(str(self.sceneRight.markerSize*2*self.sceneRight.pixelSize))
					self.label_markerSizeNanoUnit.setText(self.sceneRight.pixelSizeUnit)
				except:
					if debug is True: print clrmsg.DEBUG + "Image pixel size is not a number:", self.label_imgpxsize.text()
					self.label_markerSizeNano.setText("NaN")
					self.label_markerSizeNanoUnit.setText('')
			else:
				self.label_markerSizeNano.setText('')
				self.label_markerSizeNanoUnit.setText('')

	def setCustomRotCenter(self,maxdim):
		## The default value is set as the center of a cube with an edge length equal to the longest edge of the image volume
		halfmaxdim = 0.5 * maxdim
		self.doubleSpinBox_custom_rot_center_x.setValue(halfmaxdim)
		self.doubleSpinBox_custom_rot_center_y.setValue(halfmaxdim)
		self.doubleSpinBox_custom_rot_center_z.setValue(halfmaxdim)

												##################### END #####################
												###### Image initialization and rotation ######
												###############################################

												###############################################
												######    Image processing functions     ######
												#################### START ####################
	## Read image
	def imread(self,path,normalize=True):
		"""
		return 5 bit encoded image property:
			1 = 2D
			2 = 3D (always normalized, +16)
			4 = gray scale
			8 = multicolor/multichannel
			16= normalized
		"""
		if debug is True: print clrmsg.DEBUG + "===== imread"
		img = tf.imread(path)
		if debug is True: print clrmsg.DEBUG + "Image shape/dtype:", img.shape, img.dtype
		## Displaying issues with uint16 images -> convert to uint8
		if img.dtype == 'uint16':
			img = img*(255.0/img.max())
			img = img.astype(dtype='uint8')
			if debug is True: print clrmsg.DEBUG + "Image dtype converted to:", img.shape, img.dtype
		if img.ndim == 4:
			if debug is True: print clrmsg.DEBUG + "Calculating multichannel MIP"
			## return MIP, code 2+8+16 and image stack
			return np.amax(img, axis=1), 26, img
		## this can only handle rgb. For more channels set "3" to whatever max number of channels should be handled
		elif img.ndim == 3 and any([True for dim in img.shape if dim <= 4]) or img.ndim == 2:
			if debug is True: print clrmsg.DEBUG + "Loading regular 2D image... multicolor/normalize:", \
				[True for x in [img.ndim] if img.ndim == 3],'/',[normalize]
			if normalize is True:
				## return normalized 2D image with code 1+4+16 for gray scale normalized 2D image and 1+8+16 for
				## multicolor normalized 2D image
				return self.norm_img(img), 25 if img.ndim == 3 else 21, None
			else:
				## return 2D image with code 1+4 for gray scale 2D image and 1+8 for multicolor 2D image
				return img, 9 if img.ndim == 3 else 5, None
		elif img.ndim == 3:
			if debug is True: print clrmsg.DEBUG + "Calculating MIP"
			## return MIP and code 2+4+1E6
			return np.amax(img, axis=0), 22, img

	def pxSize(self,img_path,z=False):
		with tf.TiffFile(img_path) as tif:
			for page in tif:
				for tag in page.tags.values():
					if isinstance(tag.value, str):
						for keyword in ['PhysicalSizeX','PixelWidth','PixelSize'] if not z else ['PhysicalSizeZ','FocusStepSize']:
							tagposs = [m.start() for m in re.finditer(keyword, tag.value)]
							for tagpos in tagposs:
								if keyword == 'PhysicalSizeX' or 'PhysicalSizeZ':
									for piece in tag.value[tagpos:tagpos+30].split('"'):
										try:
											pixelSize = float(piece)
											if debug is True: print clrmsg.DEBUG + "Pixel size from exif metakey:", keyword
											## Value is in um from CorrSight/LA tiff files
											if z:
												pixelSize = pixelSize*1000
											return pixelSize
										except Exception as e:
											if debug is True: print clrmsg.DEBUG + "Pixel size parser:", e
											pass
								elif keyword == 'PixelWidth':
									for piece in tag.value[tagpos:tagpos+30].split('='):
										try:
											pixelSize = float(piece.strip().split('\r\n')[0])
											if debug is True: print clrmsg.DEBUG + "Pixel size from exif metakey:", keyword
											## *1E6 because these values from SEM/FIB image is in m
											return pixelSize*1E6
										except Exception as e:
											if debug is True: print clrmsg.DEBUG + "Pixel size parser:", e
											pass
								elif keyword == 'PixelSize' or 'FocusStepSize':
									for piece in tag.value[tagpos:tagpos+30].split('"'):
										try:
											pixelSize = float(piece)
											if debug is True: print clrmsg.DEBUG + "Pixel size from exif metakey:", keyword
											## Value is in um from CorrSight/LA tiff files
											return pixelSize
										except Exception as e:
											if debug is True: print clrmsg.DEBUG + "Pixel size parser:", e
											pass

	## Convert opencv image (numpy array in BGR) to RGB QImage and return pixmap. Only takes 2D images
	def cv2Qimage(self,img):
		if debug is True: print clrmsg.DEBUG + "===== cv2Qimage"
		## Format 2D gray-scale to RGB for QImage
		if img.ndim == 2:
			img = cv2.cvtColor(img,cv2.COLOR_GRAY2RGB)
		if img.shape[0] <= 4:
			if debug is True: print clrmsg.DEBUG + "Swapping image axes from c,y,x to y,x,c."
			img = img.swapaxes(0,2).swapaxes(0,1)
		if debug is True: print clrmsg.DEBUG + "Image shape:", img.shape
		if img.shape[-1] == 4:
			image = QtGui.QImage(img.tobytes(), img.shape[1], img.shape[0], QtGui.QImage.Format_ARGB32).rgbSwapped()
		else:
			image = QtGui.QImage(img.tobytes(), img.shape[1], img.shape[0], QtGui.QImage.Format_RGB888)  # .rgbSwapped()
		return QtGui.QPixmap.fromImage(image)

	## Adjust Brightness and Contrast by sliders
	def adjustBrightCont(self):
		if debug is True: print clrmsg.DEBUG + "===== adjustBrightCont"
		if self.label_selimg.text() == 'left':
			self.brightness_left = self.horizontalSlider_brightness.value()
			self.contrast_left = self.horizontalSlider_contrast.value()
			# print self.brightness_left,self.contrast_left
			## Remove image (item)
			self.sceneLeft.removeItem(self.pixmap_item_left)
			## Load replacement
			img_adj = np.copy(self.img_left_displayed)
			## Load contrast value (Slider value between 0 and 100)
			contr = self.contrast_left*0.1
			## Adjusting contrast
			img_adj = np.where(img_adj*contr >= 255,255,img_adj*contr)
			## Convert float64 back to uint8
			img_adj = img_adj.astype(dtype='uint8')
			## Adjust brightness
			if self.brightness_left > 0:
				img_adj = np.where(255-img_adj <= self.brightness_left,255,img_adj+self.brightness_left)
			else:
				img_adj = np.where(img_adj <= -self.brightness_left,0,img_adj+self.brightness_left)
				## Convert from int16 back to uint8
				img_adj = img_adj.astype(dtype='uint8')
			## Display image
			self.pixmap_left = self.cv2Qimage(img_adj)
			self.pixmap_item_left = QtGui.QGraphicsPixmapItem(self.pixmap_left, None, self.sceneLeft)
			## Put exchanged image into background
			QtGui.QGraphicsItem.stackBefore(self.pixmap_item_left, self.sceneLeft.items()[-1])
		elif self.label_selimg.text() == 'right':
			self.brightness_right = self.horizontalSlider_brightness.value()
			self.contrast_right = self.horizontalSlider_contrast.value()
			# print self.brightness_right,self.contrast_right
			## Remove image (item)
			self.sceneRight.removeItem(self.pixmap_item_right)
			## Load replacement
			img_adj = np.copy(self.img_right_displayed)
			## Load contrast value (Slider value between 0 and 100)
			contr = self.contrast_right*0.1
			## Adjusting contrast
			img_adj = np.where(img_adj*contr >= 255,255,img_adj*contr)
			## Convert float64 back to uint8
			img_adj = img_adj.astype(dtype='uint8')
			## Adjust brightness
			if self.brightness_right > 0:
				img_adj = np.where(255-img_adj <= self.brightness_right,255,img_adj+self.brightness_right)
			else:
				img_adj = np.where(img_adj <= -self.brightness_right,0,img_adj+self.brightness_right)
				## Convert from int16 back to uint8
				img_adj = img_adj.astype(dtype='uint8')
			## Display image
			self.pixmap_right = self.cv2Qimage(img_adj)
			self.pixmap_item_right = QtGui.QGraphicsPixmapItem(self.pixmap_right, None, self.sceneRight)
			## Put exchanged image into background
			QtGui.QGraphicsItem.stackBefore(self.pixmap_item_right, self.sceneRight.items()[-1])

	## Normalize Image
	def norm_img(self,img,copy=False):
		if debug is True: print clrmsg.DEBUG + "===== norm_img"
		if copy is True:
			img = np.copy(img)
		dtype = str(img.dtype)
		## Determine data type
		if dtype == "uint16" or dtype == "int16":
			typesize = 65535
		elif dtype == "uint8" or dtype == "int8":
			typesize = 255
		elif dtype == "float32" or dtype == "float64":
			typesize = 1
		else:
			print clrmsg.ERROR + "Sorry, I don't know this file type yet: ", dtype
		## 2D image
		if img.ndim == 2: img *= typesize/img.max()
		## 3D or multichannel image
		elif img.ndim == 3:
			## tifffile reads z,y,x for stacks but y,x,c if it is multichannel image (or z,c,y,x if it is a multicolor image stack)
			if img.shape[-1] > 4:
				if debug is True: print clrmsg.DEBUG + "image stack"
				for i in range(int(img.shape[0])):
					img[i,:,:] *= typesize/img[i,:,:].max()
			else:
				if debug is True: print clrmsg.DEBUG + "multichannel image"
				for i in range(int(img.shape[2])):
					img[:,:,i] *= typesize/img[:,:,i].max()
		return img

												##################### END #####################
												######    Image processing functions    #######
												###############################################

												###############################################
												######     CSV - Point import/export    #######
												#################### START ####################

	def autosave(self):
		csv_file_out = os.path.splitext(self.leftImage)[0] + '_coordinates.txt'
		csvHandler.model2csv(self.modelLleft,csv_file_out,delimiter="\t")
		csv_file_out = os.path.splitext(self.rightImage)[0] + '_coordinates.txt'
		csvHandler.model2csv(self.modelRight,csv_file_out,delimiter="\t")

	def exportPoints(self):
		if self.label_selectedTable.text() == 'left':
			model = self.modelLleft
		elif self.label_selectedTable.text() == 'right':
			model = self.modelRight
		## Export Dialog. Needs check for extension or add default extension
		csv_file_out, filterdialog = QtGui.QFileDialog.getSaveFileNameAndFilter(
			self, 'Export file as',
			os.path.dirname(self.leftImage) if self.label_selectedTable.text() == 'left' else os.path.dirname(self.rightImage),
			"Tabstop separated (*.csv *.txt);;Comma separated (*.csv *.txt)")
		if str(filterdialog).startswith('Comma') is True:
			csvHandler.model2csv(model,csv_file_out,delimiter=",")
		elif str(filterdialog).startswith('Tabstop') is True:
			csvHandler.model2csv(model,csv_file_out,delimiter="\t")

	def importPoints(self):
		csv_file_in, filterdialog = QtGui.QFileDialog.getOpenFileNameAndFilter(
			self, 'Import file as',
			os.path.dirname(self.leftImage) if self.label_selectedTable.text() == 'left' else os.path.dirname(self.rightImage),
			"Tabstop separated (*.csv *.txt);;Comma separated (*.csv *.txt)")
		if str(filterdialog).startswith('Comma') is True:
			itemlist = csvHandler.csv2list(csv_file_in,delimiter=",",parent=self,sniff=True)
		elif str(filterdialog).startswith('Tabstop') is True:
			itemlist = csvHandler.csv2list(csv_file_in,delimiter="\t",parent=self,sniff=True)
		if self.label_selectedTable.text() == 'left':
			for item in itemlist: self.sceneLeft.addCircle(
				float(item[0]),
				float(item[1]),
				float(item[2]) if len(item) > 2 else 0)
			self.sceneLeft.itemsToModel()
			# csvHandler.csvAppend2model(csv_file_in,self.modelLleft,delimiter="\t",parent=self,sniff=True)
		elif self.label_selectedTable.text() == 'right':
			for item in itemlist: self.sceneRight.addCircle(
				float(item[0]),
				float(item[1]),
				float(item[2]) if len(item) > 2 else 0)
			self.sceneRight.itemsToModel()
			# csvHandler.csvAppend2model(csv_file_in,self.modelRight,delimiter="\t",parent=self,sniff=True)

												##################### END #####################
												######     CSV - Point import/export    #######
												###############################################

												###############################################
												######            Correlation           #######
												#################### START ####################

	def model2np(self,model,rows):
		listarray = []
		for rowNumber in range(*rows):
			fields = [
					model.data(model.index(rowNumber, columnNumber), QtCore.Qt.DisplayRole).toFloat()[0]
					for columnNumber in range(model.columnCount())]
			listarray.append(fields)
		return np.array(listarray).astype(np.float)

	def correlate(self):
		if '{0:b}'.format(self.sceneLeft.imagetype)[-1] == '1' and '{0:b}'.format(self.sceneRight.imagetype)[-1] == '0':
			model2D = self.modelLleft
			model3D = self.modelRight
			## Temporary img to draw results and save it
			img = np.copy(self.img_left)
			if img.ndim == 2:
				## Need RGB for colored markers
				img = cv2.cvtColor(img,cv2.COLOR_GRAY2BGR)
		elif '{0:b}'.format(self.sceneLeft.imagetype)[-1] == '0' and '{0:b}'.format(self.sceneRight.imagetype)[-1] == '1':
			model2D = self.modelRight
			model3D = self.modelLleft
			## Temporary img to draw results and save it
			img = np.copy(self.img_right)
			if img.ndim == 2:
				## Need RGB for colored markers
				img = cv2.cvtColor(img,cv2.COLOR_GRAY2BGR)
		else:
			if '{0:b}'.format(self.sceneLeft.imagetype)[-1] == '0' and '{0:b}'.format(self.sceneRight.imagetype)[-1] == '0':
				raise ValueError('Both datasets contain only 2D information. I need one 3D and one 2D dataset')
			elif '{0:b}'.format(self.sceneLeft.imagetype)[-1] == '1' and '{0:b}'.format(self.sceneRight.imagetype)[-1] == '1':
				raise ValueError('Both datasets contain only 3D information. I need one 3D and one 2D dataset')
			else:
				raise ValueError('Cannot determine if datasets are 2D or 3D')
		## variables for dataset validation. The amount of markers from the 2D and 3D model have to be in corresponding order.
		## All extra rows in the 3D model are used as POIs.
		nrRowsModel2D = model2D.rowCount()
		nrRowsModel3D = model3D.rowCount()
		# self.rotation_center = [self.doubleSpinBox_psi.value(),self.doubleSpinBox_phi.value(),self.doubleSpinBox_theta.value()]
		# self.rotation_center = [670, 670, 670]
		self.rotation_center = [
								self.doubleSpinBox_custom_rot_center_x.value(),
								self.doubleSpinBox_custom_rot_center_y.value(),
								self.doubleSpinBox_custom_rot_center_z.value()]

		if nrRowsModel2D >= 3:
			if nrRowsModel2D <= nrRowsModel3D:
				timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
				self.correlation_results = correlation.main(
														markers_3d=self.model2np(model3D,[0,nrRowsModel2D]),
														markers_2d=self.model2np(model2D,[0,nrRowsModel2D]),
														spots_3d=self.model2np(model3D,[nrRowsModel2D,nrRowsModel3D]),
														rotation_center=self.rotation_center,
														results_file=''.join([
															self.workingdir,'/',timestamp, '_correlation.txt'
															] if self.checkBox_writeReport.isChecked() else '')
														)
			else:
				QtGui.QMessageBox.critical(self, "Data Structure", "The two datasets do not contain the same amount of markers!")
				return
		else:
			QtGui.QMessageBox.critical(self, "Data Structure",'At least THREE markers are needed to do the correlation')
			return

		transf_3d = self.correlation_results[1]
		for i in range(transf_3d.shape[1]):
			cv2.circle(img, (int(round(transf_3d[0,i])), int(round(transf_3d[1,i]))), 3, (0,255,0), -1)
		if self.correlation_results[2] is not None:
			calc_spots_2d = self.correlation_results[2]
			# draw POI cv2.circle(img, (center x, center y), radius, [b,g,r], thickness(-1 for filled))
			for i in range(calc_spots_2d.shape[1]):
				cv2.circle(img, (int(round(calc_spots_2d[0,i])), int(round(calc_spots_2d[1,i]))), 1, (0,0,255), -1)
		if self.checkBox_writeReport.isChecked():
			cv2.imwrite(os.path.join(self.workingdir,timestamp+"_correlated.tif"), img)
		try:
			img = cv2.cvtColor(img,cv2.COLOR_BGR2RGB)
		except:
			pass
		## Display image
		if '{0:b}'.format(self.sceneLeft.imagetype)[-1] == '1':
			self.img_left_displayed = np.copy(img)
			## Remove image (item)
			self.sceneLeft.removeItem(self.pixmap_item_left)
			self.pixmap_left = self.cv2Qimage(img)
			self.pixmap_item_left = QtGui.QGraphicsPixmapItem(self.pixmap_left, None, self.sceneLeft)
			## Put exchanged image into background
			QtGui.QGraphicsItem.stackBefore(self.pixmap_item_left, self.sceneLeft.items()[-1])
		else:
			self.img_right_displayed = np.copy(img)
			## Remove image (item)
			self.sceneRight.removeItem(self.pixmap_item_right)
			self.pixmap_right = self.cv2Qimage(img)
			self.pixmap_item_right = QtGui.QGraphicsPixmapItem(self.pixmap_right, None, self.sceneRight)
			## Put exchanged image into background
			QtGui.QGraphicsItem.stackBefore(self.pixmap_item_right, self.sceneRight.items()[-1])

		# self.displayResults(frame=False,framesize=None)
		self.displayResults(frame=self.checkBox_scatterPlotFrame.isChecked(),framesize=self.doubleSpinBox_scatterPlotFrameSize.value())
		model2D.tableview._scene.deleteArrows()
		for i in range(nrRowsModel2D):
			model2D.tableview._scene.addArrow(self.model2np(
				model2D,[0,nrRowsModel2D])[i,:2],self.correlation_results[1][:2,i],arrowangle=45,color=QtCore.Qt.red)

	def displayResults(self,frame=False,framesize=None):
		"""Populates the result tab with the appropriate information from the correlation result

		This also includes a scatter plot of the clicked markers' deviation from their calculated coordinates.

		Optionally a "frame" (boolean) with the pixel size of "framesize" (int or float) can be drawn to validate
		graphically how large the deviation is. E.g. if the correlation deviation should ideally be lower than 300 um
		at a pixel size of 161 nm, a frame with the size of 1.863 could be drawn to validate if the deviation is inside
		this margin.

		The frame is drawn in x and y from -framesize/2 to framesize/2.
		"""
		if hasattr(self, "correlation_results"):
			## get data
			transf = self.correlation_results[0]
			# transf_3d = self.correlation_results[1]			## unused atm
			# calc_spots_2d = self.correlation_results[2]		## unused atm
			delta2D = self.correlation_results[3]
			delta2D_mean = np.absolute(delta2D).mean(axis=1)
			# cm_3D_markers = self.correlation_results[4]		## unused atm
			translation = (transf.d[0], transf.d[1], transf.d[2])
			translation_customRotation = self.correlation_results[5]
			eulers = transf.extract_euler(r=transf.q, mode='x', ret='one')
			eulers = eulers * 180 / np.pi
			scale = transf.s_scalar

			# ## display data
			self.label_phi.setText('{0:.3f}'.format(eulers[0]))
			self.label_phi.setStyleSheet(self.stylesheet_green)
			self.label_psi.setText('{0:.3f}'.format(eulers[2]))
			self.label_psi.setStyleSheet(self.stylesheet_green)
			self.label_theta.setText('{0:.3f}'.format(eulers[1]))
			self.label_theta.setStyleSheet(self.stylesheet_green)
			self.label_scale.setText('{0:.3f}'.format(scale))
			self.label_scale.setStyleSheet(self.stylesheet_green)
			self.label_translation.setText('x = {0:.3f} | y = {1:.3f}'.format(translation[0], translation[1]))
			self.label_translation.setStyleSheet(self.stylesheet_green)
			self.label_custom_rot_center.setText('[{0},{1},{2}]:'.format(
								int(self.doubleSpinBox_custom_rot_center_x.value()),
								int(self.doubleSpinBox_custom_rot_center_y.value()),
								int(self.doubleSpinBox_custom_rot_center_z.value())))
			self.label_translation_custom_rot.setText('x = {0:.3f} | y = {1:.3f}'.format(
				translation_customRotation[0], translation_customRotation[1]))
			self.label_translation_custom_rot.setStyleSheet(self.stylesheet_green)
			self.label_meandxdy.setText('{0:.5f} / {1:.5f}'.format(delta2D_mean[0], delta2D_mean[1]))
			if delta2D_mean[0] <= 1 and delta2D_mean[1] <= 1: self.label_meandxdy.setStyleSheet(self.stylesheet_green)
			elif delta2D_mean[0] < 2 or delta2D_mean[1] < 2: self.label_meandxdy.setStyleSheet(self.stylesheet_orange)
			else: self.label_meandxdy.setStyleSheet(self.stylesheet_red)
			self.label_rms.setText('{0:.5f}'.format(transf.rmsError))
			self.label_rms.setStyleSheet(self.stylesheet_green if transf.rmsError < 1 else self.stylesheet_orange)

			self.widget_matplotlib.setupScatterCanvas(width=4,height=4,dpi=52,toolbar=False)
			self.widget_matplotlib.scatterPlot(x=delta2D[0,:],y=delta2D[1,:],frame=frame,framesize=framesize,xlabel="px",ylabel="px")

			## Populate tableView_results
			self.modelResults.removeRows(0,self.modelResults.rowCount())
			if self.checkBox_resultsAbsolute.isChecked():
				delta2D = np.absolute(delta2D)
			for i in range(delta2D.shape[1]):
				item = [
					QtGui.QStandardItem(str(i+1)),
					QtGui.QStandardItem('{0:.5f}'.format(delta2D[0,i])),
					QtGui.QStandardItem('{0:.5f}'.format(delta2D[1,i]))]
				self.modelResults.appendRow(item)
			self.modelResults.setHeaderData(0, QtCore.Qt.Horizontal,'Nr.')
			self.modelResults.setHeaderData(1, QtCore.Qt.Horizontal,'dx')
			self.modelResults.setHeaderData(1, QtCore.Qt.Horizontal,'dx')
			self.modelResults.setHeaderData(2, QtCore.Qt.Horizontal,'dy')
			self.tableView_results.setColumnWidth(1, 86)
			self.tableView_results.setColumnWidth(2, 86)

		else:
			# QtGui.QMessageBox.critical(self, "Error", "No data to display!")
			pass

	def showSelectedResidual(self,doubleclick=False):
		"""Show position of selected residual (results tab)

		Simply selected will color the corresponding point in the image green.
		A double click will center and zoom on the selected point.
		"""
		indices = self.tableView_results.selectedIndexes()
		if '{0:b}'.format(self.sceneLeft.imagetype)[-1] == '1':
			tableView1 = self.tableView_left
			tableView2 = self.tableView_right
			graphicsView = self.graphicsView_left
		else:
			tableView2 = self.tableView_left
			tableView1 = self.tableView_right
			graphicsView = self.graphicsView_right
		if indices:
			## Filter selected rows
			rows = set(index.row() for index in indices)
			## Select rows (only one row selectable in the results table)
			for row in rows:
				markerNr = int(self.modelResultsProxy.data(self.modelResultsProxy.index(row, 0)).toString())-1
				tableView1.selectRow(markerNr)
				tableView2.selectRow(markerNr)
		else:
			tableView1.clearSelection()
			tableView2.clearSelection()
		if doubleclick is True:
			if debug is True: print clrmsg.DEBUG + 'double click'
			if debug is True: print clrmsg.DEBUG, graphicsView.transform().m11(), graphicsView.transform().m22()
			graphicsView.setTransform(QtGui.QTransform(
				20,  # m11
				graphicsView.transform().m12(),
				graphicsView.transform().m13(),
				graphicsView.transform().m21(),
				20,  # m22
				graphicsView.transform().m23(),
				graphicsView.transform().m31(),
				graphicsView.transform().m32(),
				graphicsView.transform().m33(),
				))
			if debug is True: print clrmsg.DEBUG, graphicsView.transform().m11(), graphicsView.transform().m22()
			## Center on coordinate
			graphicsView.centerOn(
				float(tableView1._model.data(tableView1._model.index(markerNr, 0)).toString()),
				float(tableView1._model.data(tableView1._model.index(markerNr, 1)).toString()))

	def cmTableViewResults(self,pos):
		"""Context menu for residuals table (results tab)"""
		indices = self.tableView_results.selectedIndexes()
		if indices:
			cmApplyShift = QtGui.QAction('Apply shift to marker', self)
			cmApplyShift.triggered.connect(self.applyResidualShift)
			self.contextMenu = QtGui.QMenu(self)
			self.contextMenu.addAction(cmApplyShift)
			self.contextMenu.popup(QtGui.QCursor.pos())

	def applyResidualShift(self):
		"""Applies the selected residual from the correlation to the corresponding clicked 2D values

		The correlation returns the delta between the clicked fiducial 2D and the calculated 2D coordinates derived
		from the applied correlation to the corresponding fiducial 3D coordinate.
		"""
		indices = self.tableView_results.selectedIndexes()
		if '{0:b}'.format(self.sceneLeft.imagetype)[-1] == '1':
			tableView = self.tableView_left
			scene = self.sceneLeft
		else:
			tableView = self.tableView_right
			scene = self.sceneRight
		items = []
		for item in scene.items():
			if isinstance(item, QtGui.QGraphicsEllipseItem):
				items.append(item)
		if indices:
			## Filter selected rows
			rows = set(index.row() for index in indices)
			## Select rows (only one row selectable in the results table)
			for row in rows:
				markerNr = int(self.modelResultsProxy.data(self.modelResultsProxy.index(row, 0)).toString())-1
				if debug is True: print clrmsg.DEBUG + 'Marker number/background color (Qrgba)', markerNr, \
					self.modelResults.itemFromIndex(
						self.modelResultsProxy.mapToSource((self.modelResultsProxy.index(row, 0)))).background().color().rgba()
				if self.modelResults.itemFromIndex(self.modelResultsProxy.mapToSource((
					self.modelResultsProxy.index(row, 0)))).background().color().rgba() == 4278190080:
					BackColor = (50,220,175,100)
					ForeColor = (180,180,180,255)
					items[markerNr].setPos(
						float(tableView._model.data(
							tableView._model.index(markerNr, 0)).toString())+self.correlation_results[3][0,markerNr],
						float(tableView._model.data(
							tableView._model.index(markerNr, 1)).toString())+self.correlation_results[3][1,markerNr])
					self.modelResults.itemFromIndex(self.modelResultsProxy.mapToSource((
						self.modelResultsProxy.index(row, 0)))).setBackground(QtGui.QColor(*BackColor))
					self.modelResults.itemFromIndex(self.modelResultsProxy.mapToSource((
						self.modelResultsProxy.index(row, 1)))).setBackground(QtGui.QColor(*BackColor))
					self.modelResults.itemFromIndex(self.modelResultsProxy.mapToSource((
						self.modelResultsProxy.index(row, 2)))).setBackground(QtGui.QColor(*BackColor))
					self.modelResults.itemFromIndex(self.modelResultsProxy.mapToSource((
						self.modelResultsProxy.index(row, 0)))).setForeground(QtGui.QColor(*ForeColor))
					self.modelResults.itemFromIndex(self.modelResultsProxy.mapToSource((
						self.modelResultsProxy.index(row, 1)))).setForeground(QtGui.QColor(*ForeColor))
					self.modelResults.itemFromIndex(self.modelResultsProxy.mapToSource((
						self.modelResultsProxy.index(row, 2)))).setForeground(QtGui.QColor(*ForeColor))
		scene.itemsToModel()
		self.tableView_results.clearSelection()

												##################### END #####################
												######            Correlation           #######
												###############################################


class SplashScreen():
	def __init__(self):
		"""Splash screen

		The splash screen, besides being fancy, shows the path to image being loaded at the moment.
		"""
		QtGui.QApplication.processEvents()
		## Load splash screen image
		splash_pix = QtGui.QPixmap(os.path.join(execdir,'icons','SplashScreen.png'))
		## Add version
		painter = QtGui.QPainter()
		painter.begin(splash_pix)
		painter.setPen(QtCore.Qt.white)
		painter.drawText(
			0,0,
			splash_pix.size().width()-3,splash_pix.size().height()-1,QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight, __version__)
		painter.end()
		## Show splash screen
		self.splash = QtGui.QSplashScreen(splash_pix, QtCore.Qt.WindowStaysOnTopHint)
		self.splash.setMask(splash_pix.mask())
		self.splash.show()
		self.splash.showMessage("Initializing...",color=QtCore.Qt.white)
		## Needed to receive mouse clicks to hide splash screen
		QtGui.QApplication.processEvents()

		# Simulate something that takes time
		time.sleep(1)
		self.splash.showMessage("Loading images...",color=QtCore.Qt.white)


class Main():
	def __init__(self,leftImage=None,rightImage=None,nosplash=False,workingdir=None):
		"""Class for running this application either as standalone or as imported QT Widget

		args:
				self:		self is another QT (main) widget passed as parent when this file's main widget is called
							from it.

		kwargs:
				leftImage:	string, required
							Path to first image.
							The image has to be a tiff file. It can be a gray-scale 2D image (y,x)
							or 3D image stack (z,y,x). Color channels are supported as well like (y,x,c) or (z,c,y,x)
							respectively. Color channels are detected by checking the third (images with 3 dimensions)
							or the second (images with 4 dimensions) dimension for values equal or less then 3. That
							means, if the image contains more than 3 channels, the color channel detection can result
							in funny and wrong image reads.

				rightImage:	string, required
							Path to first image.
							See "leftImage".

				nosplash:	bool, optional
							If True, a splash screen showing which image is being loaded at the moment is rendered at
							startup.

				workingdir:	string, optional
							If None, the execution directory is used as the working directory.


		For standalone mode, just run python -u TDCT_correlation.py
		For loading this widget from another main QT application:

		import TDCT_correlation
		# inside of the qt (main) widget:
			...
			self.correlationModul = TDCT_correlation.Main(
														leftImage="path/to/first/image.tif",
														rightImage="path/to/second/image.tif",
														nosplash=False,
														workingdir="path/to/workingdir")
		"""
		self.exitstatus = 1
		if leftImage is None or rightImage is None:
			sys.exit("Please pass 'leftImage=PATH' and 'rightImage=PATH' to this function")

		if nosplash is False:
			global splashscreen
			splashscreen = SplashScreen()

		if workingdir is None:
			workingdir = execdir

		self.window = MainWidget(parent=self,leftImage=leftImage, rightImage=rightImage,workingdir=workingdir)
		self.window.show()
		self.window.raise_()

		if nosplash is False:
			splashscreen.splash.finish(self.window)

	def cleanUp(self):
		"""Clean up instance mostly for external call case, to check if the window still exists."""
		try:
			del self.window
		except Exception as e:
			if debug is True: print clrmsg.DEBUG + str(e)


if __name__ == "__main__":
	if debug is True:
		print clrmsg.DEBUG + 'Debug Test'
		print clrmsg.OK + 'OK Test'
		print clrmsg.ERROR + 'Error Test'
		print clrmsg.INFO + 'Info Test'
		print clrmsg.INFO + 'Info Test'
		print clrmsg.WARNING + 'Warning Test'
		print '='*20, 'Initializing', '='*20

	app = QtGui.QApplication(sys.argv)

	## File dialogs for standalone mode
	## *.png *.jpg *.bmp not yet supported
	left = str(QtGui.QFileDialog.getOpenFileName(
		None,"Select first image file for correlation", execdir,"Image Files (*.tif *.tiff);; All (*.*)"))
	if left == '': sys.exit()
	right = str(QtGui.QFileDialog.getOpenFileName(
		None,"Select second image file for correlation", execdir,"Image Files (*.tif *.tiff);; All (*.*)"))
	if right == '': sys.exit()

	main = Main(leftImage=left,rightImage=right)

	sys.exit(app.exec_())