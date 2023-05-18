import os

import soundfile
import numpy as np
import urllib

from typing import List
from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtGui import *
from slicer2 import Slicer

from gui.Ui_MainWindow import Ui_MainWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.ui.btnAddFiles.clicked.connect(self._on_add_audio_files)
        self.ui.btnBrowse.clicked.connect(self._on_browse_output_dir)
        self.ui.btnRemove.clicked.connect(self._on_remove_audio_file)
        self.ui.btnClearList.clicked.connect(self._on_clear_audio_list)
        self.ui.btnAbout.clicked.connect(self._on_about)
        self.ui.btnStart.clicked.connect(self._on_start)

        self.ui.progressBar.setMinimum(0)
        self.ui.progressBar.setMaximum(100)
        self.ui.progressBar.setValue(0)
        self.ui.btnStart.setDefault(True)

        validator = QRegularExpressionValidator(QRegularExpression(r"\d+"))
        self.ui.leThreshold.setValidator(QDoubleValidator())
        self.ui.leMinLen.setValidator(validator)
        self.ui.leMinInterval.setValidator(validator)
        self.ui.leHopSize.setValidator(validator)
        self.ui.leMaxSilence.setValidator(validator)

        # State variables
        self.workers: list[QThread] = []
        self.workCount = 0
        self.workFinished = 0
        self.processing = False

        self.setWindowTitle(QApplication.applicationName())

        # Must set to accept drag and drop events
        self.setAcceptDrops(True)

    def _on_browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Browse Output Directory", ".")
        if path != "":
            self.ui.leOutputDir.setText(QDir.toNativeSeparators(path))

    def _on_add_audio_files(self):
        if self.processing:
            self._warningProcessNotFinished()
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Select Audio Files', ".", 'Wave Files(*.wav)')
        for path in paths:
            item = QListWidgetItem()
            item.setText(QFileInfo(path).fileName())
            # Save full path at custom role
            item.setData(Qt.ItemDataRole.UserRole + 1, path)
            self.ui.lwTaskList.addItem(item)

    def _on_remove_audio_file(self):
        selectedItems = self.ui.lwTaskList.selectedItems
        
        return

    def _on_clear_audio_list(self):
        if self.processing:
            self._warningProcessNotFinished()
            return

        self.ui.lwTaskList.clear()

    def _on_about(self):
        QMessageBox.information(
            self, "About", "Audio Slicer v1.1.0\nCopyright 2020-2023 OpenVPI Team")

    def _on_start(self):
        if self.processing:
            self._warningProcessNotFinished()
            return

        item_count = self.ui.lwTaskList.count()
        if item_count == 0:
            return

        class WorkThread(QThread):
            oneFinished = Signal()

            def __init__(self, filenames: List[str], window: MainWindow):
                super().__init__()

                self.filenames = filenames
                self.win = window

            def run(self):
                for filename in self.filenames:
                    audio, sr = soundfile.read(filename, dtype=np.float32)
                    is_mono = True
                    if len(audio.shape) > 1:
                        is_mono = False
                        audio = audio.T
                    slicer = Slicer(
                        sr=sr,
                        threshold=float(self.win.ui.leThreshold.text()),
                        min_length=int(self.win.ui.leMinLen.text()),
                        min_interval=int(
                            self.win.ui.leMinInterval.text()),
                        hop_size=int(self.win.ui.leHopSize.text()),
                        max_sil_kept=int(self.win.ui.leMaxSilence.text())
                    )
                    sil_tags, total_frames = slicer.get_slice_tags(audio)
                    chunks = slicer.slice(audio, sil_tags, total_frames)
                    out_dir = self.win.ui.leOutputDir.text()
                    if out_dir == '':
                        out_dir = os.path.dirname(os.path.abspath(filename))
                    else:
                        # Make dir if not exists
                        info = QDir(out_dir)
                        if not info.exists():
                            info.mkpath(out_dir)

                    for i, chunk in enumerate(chunks):
                        path = os.path.join(out_dir, f'%s_%d.wav' % (os.path.basename(filename)
                                                                     .rsplit('.', maxsplit=1)[0], i))
                        if not is_mono:
                            chunk = chunk.T
                        soundfile.write(path, chunk, sr)

                    self.oneFinished.emit()

        # Collect paths
        paths: list[str] = []
        for i in range(0, item_count):
            item = self.ui.lwTaskList.item(i)
            path = item.data(Qt.ItemDataRole.UserRole + 1)  # Get full path
            paths.append(path)

        self.ui.progressBar.setMaximum(item_count)
        self.ui.progressBar.setValue(0)

        self.workCount = item_count
        self.workFinished = 0
        self._setProcessing(True)

        # Start work thread
        worker = WorkThread(paths, self)
        worker.oneFinished.connect(self._oneFinished)
        worker.finished.connect(self._threadFinished)
        worker.start()

        self.workers.append(worker)  # Collect in case of auto deletion

    def _oneFinished(self):
        self.workFinished += 1
        self.ui.progressBar.setValue(self.workFinished)

    def _threadFinished(self):
        # Join all workers
        for worker in self.workers:
            worker.wait()
        self.workers.clear()
        self._setProcessing(False)

        QMessageBox.information(
            self, QApplication.applicationName(), "Slicing complete!")

    def _warningProcessNotFinished(self):
        QMessageBox.warning(self, QApplication.applicationName(),
                            "Please wait for slicing to complete!")

    def _setProcessing(self, processing: bool):
        is_enabled = not processing
        self.ui.btnStart.setText(
            "Slicing..." if processing else "Start")
        self.ui.btnStart.setEnabled(is_enabled)
        self.ui.btnPreview.setEnabled(is_enabled)
        self.ui.btnAddFiles.setEnabled(is_enabled)
        self.ui.lwTaskList.setEnabled(is_enabled)
        self.ui.btnClearList.setEnabled(is_enabled)
        self.ui.leThreshold.setEnabled(is_enabled)
        self.ui.leMinLen.setEnabled(is_enabled)
        self.ui.leMinInterval.setEnabled(is_enabled)
        self.ui.leHopSize.setEnabled(is_enabled)
        self.ui.leMaxSilence.setEnabled(is_enabled)
        self.ui.leOutputDir.setEnabled(is_enabled)
        self.ui.btnBrowse.setEnabled(is_enabled)
        self.processing = processing

    # Event Handlers
    def closeEvent(self, event):
        if self.processing:
            self._warningProcessNotFinished()
            event.ignore()

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        has_wav = False
        for url in urls:
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1]
            if ext.lower() == '.wav':
                has_wav = True
                break
        if has_wav:
            event.accept()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        for url in urls:
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1]
            if ext.lower() != '.wav':
                continue
            item = QListWidgetItem()
            item.setText(QFileInfo(path).fileName())
            item.setData(Qt.ItemDataRole.UserRole + 1,
                         path)
            self.ui.lwTaskList.addItem(item)
