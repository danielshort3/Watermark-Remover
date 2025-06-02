#!/usr/bin/env python
# coding: utf-8

# Standard library imports
import re
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
import subprocess
import platform

# Third-party library imports
from PyQt5.QtGui import QIcon, QTextCursor, QFont, QPixmap
from PyQt5.QtCore import Qt, pyqtSlot, QThread, pyqtSignal, QByteArray, QSize
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QLineEdit,
    QProgressBar,
    QCheckBox,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QComboBox,
    QTextEdit,
    QGroupBox,
    QDialog,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
    QMessageBox,
    QInputDialog,
)
from transposition_utils import (
    normalize_key as util_normalize_key,
    get_interval_name as util_get_interval_name,
    get_transposition_suggestions as util_get_transposition_suggestions,
    VALID_KEYS,
    INSTRUMENT_TRANSPOSITIONS,
)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import requests

# Imports moved to dedicated modules
from selenium_utils import SeleniumHelper, xpaths
from sheet_music_threads import (
    FindSongsThread,
    SelectSongThread,
    SelectKeyThread,
    DownloadAndProcessThread,
)
from batch_processor import BatchProcessor
from batch_grid_dialog import BatchGridDialog

# Main application window
class App(QMainWindow):
    def __init__(self, *args, **kwargs):
        super(App, self).__init__(*args, **kwargs)

        self.paths = {
            'window_icon_path': 'data/Church_Music_Watermark/praisecharts-logo-icon-only.png',
            'wm_model_path': 'models/Watermark_Removal',
            'us_model_path': 'models/VDSR',
            'download_dir': 'Praise_Charts',
            'temp_sub_dir': 'temp',
            'tensor_path': 'data/Church_Music_Watermark/mask.png'
        }

        self.setWindowIcon(QIcon(self.paths['window_icon_path']))

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--headless")  # Uncomment if you want to run Chrome in headless mode
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=3")  # Suppress logging

        # **Suppress WebDriver Manager logs by setting log_level**
        driver_manager = ChromeDriverManager()  # 0 for INFO, 1 for WARNING, etc.

        # **Suppress ChromeDriver logs by redirecting stdout and stderr**
        service = Service(driver_manager.install(), log_path=os.devnull)

        # driver_path = '/usr/bin/google-chrome-stable'
        # service = Service(driver_path, log_path=os.devnull)

        self.driver = webdriver.Chrome(service=service, options=options)
        url = "https://www.praisecharts.com/"
        self.driver.get(url)
        self.song_info = []  # Changed to list of dicts
        self.button_elements = []
        self.full_paths = []
        self.instrument_parts = []  # To store instrument parts
        self.selected_instruments = []  # To store selected instruments
        self.is_song_selected = False  # Flag to track if a song has been selected
        self.batch_processor = BatchProcessor(self)


        self.setWindowTitle("Praise Charts Music Downloader")
        self.setMinimumWidth(600)
        self.setMaximumWidth(1200)
        self.setMinimumHeight(800)
        self.setMaximumHeight(1200)

        # Styling and Font
        self.setFont(QFont("Arial", 9))
        self.setStyleSheet(
            """
            QWidget {
                background-color: #2b2b2b;
                color: #f0f0f0;
            }
            QLineEdit, QComboBox, QTextEdit, QProgressBar {
                background-color: #3c3f41;
                color: #f0f0f0;
                border: 1px solid #555;
                border-radius: 4px;
                font-size: 10pt;
                selection-background-color: #5a5a5a;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border-radius: 4px;
                padding: 5px 20px;
                min-height: 20px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #555555;
            }
            QLabel {
                color: #ffffff;
                font-weight: bold;
                font-size: 10pt;
            }
            QGroupBox {
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 10px;
                padding: 10px;
                font-size: 9pt;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 3px;
                background-color: #2b2b2b;
            }
            QProgressBar {
                text-align: center;
                font-size: 10pt;
            }
            QProgressBar::chunk {
                background-color: #3498db;
            }
            """
        )


        # GUI elements
        self.create_widgets()
        self.create_layout()
        self.show()

    def create_widgets(self):
        # Search Section
        self.song_search_box = QLineEdit(self)
        self.song_search_box.setPlaceholderText("Enter the song you're looking for")
        self.song_search_box.setToolTip("Type the song name you want to search for")

        self.search_button = QPushButton("Search", self)
        self.search_button.setToolTip("Click to search for songs")
        self.search_button.clicked.connect(self.find_songs)

        # Song Selection Section
        self.song_choice_box = QComboBox(self)
        self.song_choice_box.setIconSize(QSize(40, 40))  # Set the icon size for the combo box
        self.song_choice_box.setFixedHeight(45)
        self.song_choice_box.setMaxVisibleItems(100)
        self.song_choice_box.setToolTip("Select a song from the search results")

        self.song_select_button = QPushButton("Select song", self)
        self.song_select_button.setToolTip("Click to select the highlighted song")
        self.song_select_button.clicked.connect(self.select_song)

        # Key Selection Section
        self.key_choice_box = QComboBox(self)
        self.key_choice_box.setMaxVisibleItems(100)
        self.key_choice_box.setToolTip("Select a key for the selected song")
        self.key_choice_box.currentIndexChanged.connect(self.select_key)

        # Add Target Key Input Field
        self.target_key_input = QLineEdit(self)
        self.target_key_input.setPlaceholderText("Enter target key (e.g., C, D#, F)")
        self.target_key_input.setToolTip("Enter the target key for transposition")
        self.target_key_input.textChanged.connect(self.update_transposition_suggestions)

        # Add Instrument Selection Dropdown
        self.instrument_choice_box = QComboBox(self)
        self.instrument_choice_box.setToolTip("Select your instrument for transposition suggestions")
        self.instrument_choice_box.currentIndexChanged.connect(self.update_transposition_suggestions)
        self.instrument_choice_box.setMinimumWidth(200)  # Increase width as needed
        self.instrument_choice_box.setMaximumWidth(300)  # Prevent it from being too wide

        # Set default instrument
        self.default_instrument = "French Horn 1/2"

        # Direct Transpositions Display
        self.direct_transpositions_display = QTextEdit(self)
        self.direct_transpositions_display.setReadOnly(True)
        self.direct_transpositions_display.setToolTip("Direct Transpositions")
        self.direct_transpositions_display.setStyleSheet("font-size: 10pt;")
        self.direct_transpositions_display.setMaximumHeight(150)

        # Closest Matches Display
        self.closest_matches_display = QTextEdit(self)
        self.closest_matches_display.setReadOnly(True)
        self.closest_matches_display.setToolTip("Closest Matches")
        self.closest_matches_display.setStyleSheet("font-size: 10pt;")
        self.closest_matches_display.setMaximumHeight(150)

        # Download Options
        self.horn_checkbox = QCheckBox("Download horn image only", self)
        self.horn_checkbox.setToolTip("Check this box to download only horn images")

        self.select_instruments_button = QPushButton("Select Instruments", self)
        self.select_instruments_button.setEnabled(False)
        self.select_instruments_button.clicked.connect(self.open_instrument_selection_dialog)

        self.download_and_process_button = QPushButton("Download/process images", self)
        self.download_and_process_button.setToolTip("Download and process images for the selected song")
        self.download_and_process_button.clicked.connect(self.download_and_process_images)

        # Batch processing button
        self.batch_process_button = QPushButton("Batch Process List", self)
        self.batch_process_button.setToolTip("Enter a list of songs for batch processing")
        self.batch_process_button.clicked.connect(self.batch_process_songs)

        # Log and Progress Bar
        self.log_area = QTextEdit(self)
        self.log_area.setReadOnly(True)
        self.log_area.setToolTip("Log area displaying process updates")

        self.progress_label = QLabel("", self)
        self.progress_label.setAlignment(Qt.AlignCenter)

        self.progressBar = QProgressBar(self)
        self.progressBar.setValue(0)



    def create_layout(self):
        # Search Section
        search_group = QGroupBox("Search for a Song")
        search_layout = QVBoxLayout()
        search_layout.addWidget(self.song_search_box)
        search_layout.addWidget(self.search_button)
        search_group.setLayout(search_layout)

        # Song Selection Section
        song_group = QGroupBox("Select a Song")
        song_layout = QVBoxLayout()
        song_layout.addWidget(self.song_choice_box)
        song_layout.addWidget(self.song_select_button)
        song_group.setLayout(song_layout)

        # Key Selection Section
        key_group = QGroupBox("Select a Key")
        key_layout = QVBoxLayout()

        # Create a horizontal layout for key selection, target key input, and instrument selection
        key_selection_layout = QHBoxLayout()
        key_selection_layout.addWidget(QLabel("Available Keys:"))
        key_selection_layout.addWidget(self.key_choice_box)
        key_selection_layout.addWidget(QLabel("Target Key:"))
        key_selection_layout.addWidget(self.target_key_input)
        key_selection_layout.addWidget(QLabel("Instrument:"))
        key_selection_layout.addWidget(self.instrument_choice_box)

        key_layout.addLayout(key_selection_layout)
        key_group.setLayout(key_layout)

        # Transposition Suggestions Section
        transposition_group = QGroupBox("Transposition Suggestions")
        transposition_layout = QHBoxLayout()

        # Direct Transpositions Layout
        direct_layout = QVBoxLayout()
        direct_label = QLabel("Direct Transpositions")
        direct_label.setAlignment(Qt.AlignCenter)
        direct_layout.addWidget(direct_label)
        direct_layout.addWidget(self.direct_transpositions_display)

        # Closest Matches Layout
        closest_layout = QVBoxLayout()
        closest_label = QLabel("Closest Matches")
        closest_label.setAlignment(Qt.AlignCenter)
        closest_layout.addWidget(closest_label)
        closest_layout.addWidget(self.closest_matches_display)

        # Add both layouts to the transposition layout
        transposition_layout.addLayout(direct_layout)
        transposition_layout.addLayout(closest_layout)
        transposition_group.setLayout(transposition_layout)

        # Download Options
        download_group = QGroupBox("Download Options")
        download_layout = QHBoxLayout()
        download_layout.addWidget(self.horn_checkbox)
        download_layout.addWidget(self.select_instruments_button)
        download_group.setLayout(download_layout)

        # Main Layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(search_group)
        main_layout.addWidget(song_group)
        main_layout.addWidget(key_group)
        main_layout.addWidget(transposition_group)  # Add the transposition group
        main_layout.addWidget(download_group)
        main_layout.addWidget(self.download_and_process_button)
        main_layout.addWidget(self.batch_process_button)
        main_layout.addWidget(QLabel("Log:"))
        main_layout.addWidget(self.log_area)
        main_layout.addWidget(self.progress_label)
        main_layout.addWidget(self.progressBar)

        # Central widget
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Adjust the window size to be slightly taller and wider
        self.resize(1000, 1200)  # Increased width and height

        # Initial state
        self.enable_search_section()
        self.disable_song_selection()
        self.disable_key_selection()



    def enable_search_section(self):
        self.song_search_box.setEnabled(True)
        self.search_button.setEnabled(True)

    def disable_search_section(self):
        self.song_search_box.setEnabled(False)
        self.search_button.setEnabled(False)

    def enable_song_selection(self):
        self.song_choice_box.setEnabled(True)
        self.song_select_button.setEnabled(True)

    def disable_song_selection(self):
        self.song_choice_box.setEnabled(False)
        self.song_select_button.setEnabled(False)

    def enable_key_selection(self):
        self.key_choice_box.setEnabled(True)

    def disable_key_selection(self):
        self.key_choice_box.setEnabled(False)

    def disable_all_sections(self):
        self.disable_search_section()
        self.disable_song_selection()
        self.disable_key_selection()
        self.select_instruments_button.setEnabled(False)
        self.download_and_process_button.setEnabled(False)
        self.horn_checkbox.setEnabled(False)

    def enable_after_download(self):
        self.enable_search_section()
        self.enable_key_selection()
        # Do not enable song selection
        if self.instrument_parts:
            self.select_instruments_button.setEnabled(True)
        self.download_and_process_button.setEnabled(True)
        self.horn_checkbox.setEnabled(True)

    @pyqtSlot()
    def batch_process_songs(self):
        instruments = sorted(INSTRUMENT_TRANSPOSITIONS.keys())
        keys = sorted(VALID_KEYS)
        dialog = BatchGridDialog(instruments, keys, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        entries = dialog.get_entries()
        if not entries:
            QMessageBox.information(self, "No Songs", "No valid songs entered.")
            return
        self.batch_processor.process_batch(entries)

    def open_instrument_selection_dialog(self):
        if not self.instrument_parts:
            QMessageBox.information(self, "No Instruments", "No instruments available to select.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Select Instruments")
        layout = QVBoxLayout()

        list_widget = QListWidget()
        for instrument in self.instrument_parts:
            instrument_clean = instrument.strip()
            if not instrument_clean or instrument_clean == "Conductor's Score":
                continue  # Skip empty or unwanted instruments
            item = QListWidgetItem(instrument_clean)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if instrument_clean in self.selected_instruments:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
            list_widget.addItem(item)

        layout.addWidget(list_widget)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        if dialog.exec_() == QDialog.Accepted:
            self.selected_instruments = []
            for index in range(list_widget.count()):
                item = list_widget.item(index)
                if item.checkState() == Qt.Checked:
                    self.selected_instruments.append(item.text())
            self.append_log(f"Selected instruments: {', '.join(self.selected_instruments)}")
        else:
            pass


    def append_log(self, message):
        timestamp = datetime.now().strftime('%H:%M:%S')
        formatted_message = f"{timestamp}: {message}"
        self.log_area.append(formatted_message)
        cursor = self.log_area.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_area.setTextCursor(cursor)

    def updateProgressBar(self, val):
        self.progressBar.setValue(val)

    def updateStatusLabel(self, message):
        self.progress_label.setText(message)

    def closeEvent(self, event):
        self.driver.quit()
        event.accept()

    @pyqtSlot()
    def find_songs(self):
        driver = self.driver
        user_song_choice = self.song_search_box.text()

        if not user_song_choice.strip():
            QMessageBox.warning(self, "Input Required", "Please enter a song to search.")
            self.append_log("Please enter a song to search.")
            return

        # Reset flags and UI elements
        self.is_song_selected = False
        self.clear_song_info()
        self.clear_song_choice_box()
        self.clear_key_choice_box()
        self.disable_song_selection()
        self.disable_key_selection()
        self.instrument_parts.clear()
        self.selected_instruments.clear()
        self.target_key_input.clear()  # Also clears the target key input

        self.find_songs_thread = FindSongsThread(driver, user_song_choice)
        self.find_songs_thread.log_updated.connect(self.update_log)
        self.find_songs_thread.progress.connect(self.updateProgressBar)
        self.find_songs_thread.status.connect(self.updateStatusLabel)
        self.find_songs_thread.request_song_choice_box_count.connect(self.send_song_choice_box_count)
        self.find_songs_thread.insert_separator_in_song_choice_box.connect(self.insert_separator_slot)
        self.find_songs_thread.clear_song_info.connect(self.clear_song_info)
        self.find_songs_thread.clear_song_choice_box.connect(self.clear_song_choice_box)
        self.find_songs_thread.clear_key_choice_box.connect(self.clear_key_choice_box)
        self.find_songs_thread.song_info_updated.connect(self.update_song_info)
        self.find_songs_thread.song_choice_box_updated.connect(self.update_song_choice_box)
        self.find_songs_thread.started.connect(self.disable_search_section)
        self.find_songs_thread.finished.connect(self.enable_search_section)
        self.find_songs_thread.finished.connect(self.enable_song_selection)
        self.find_songs_thread.finished.connect(self.disable_key_selection)
        self.find_songs_thread.finished.connect(self.check_search_results)
        self.find_songs_thread.start()

        # Disable song selection UI until search completes
        self.disable_song_selection()

    @pyqtSlot()
    def select_song(self):
        selected_song = self.song_choice_box.currentText()
        if not selected_song:
            QMessageBox.warning(self, "No Selection", "Please select a song from the list.")
            self.append_log("No song selected.")
            return
    
        selected_song_index = None
        for idx, song in enumerate(self.song_info):
            if song['text'] == selected_song:
                selected_song_index = idx
                break
    
        if selected_song_index is None:
            QMessageBox.warning(self, "Selection Error", "Selected song not found in the list.")
            self.append_log("Selected song not found in song_info.")
            return
    
        selected_song_title = selected_song.split('\n')[0]
        user_song_choice = self.song_search_box.text()
    
        self.select_song_thread = SelectSongThread(self.driver, selected_song, selected_song_index, selected_song_title, user_song_choice)
        self.select_song_thread.log_updated.connect(self.update_log)
        self.select_song_thread.progress.connect(self.updateProgressBar)
        self.select_song_thread.status.connect(self.updateStatusLabel)
        self.select_song_thread.key_choice_box_updated.connect(self.update_key_choice_box)
        self.select_song_thread.button_elements_signal.connect(self.update_button_elements)
        self.select_song_thread.clear_button_elements.connect(self.clear_button_elements)
        self.select_song_thread.clear_key_choice_box.connect(self.clear_key_choice_box)
        self.select_song_thread.instrument_parts_signal.connect(self.update_instrument_parts)
        self.select_song_thread.song_selection_failed.connect(self.handle_song_selection_failure)  # New connection
        self.select_song_thread.started.connect(self.disable_search_section)
        self.select_song_thread.finished.connect(self.enable_search_section)
        self.select_song_thread.finished.connect(self.disable_song_selection)
        self.select_song_thread.finished.connect(self.enable_key_selection)
        self.select_song_thread.start()
    
        # Set the flag that a song has been selected
        self.is_song_selected = True
    
        # Disable song selection UI after selection
        self.disable_song_selection()

    def handle_song_selection_failure(self):
        QMessageBox.warning(self, "Selection Failed", "Orchestration not found or an error occurred. Please select another song.")
        self.append_log("Orchestration not found or an error occurred. Please select another song.")
        # Reset UI elements
        self.clear_song_info()
        self.clear_song_choice_box()
        self.clear_key_choice_box()
        self.disable_song_selection()
        self.disable_key_selection()
        # Re-enable search
        self.enable_search_section()



    @pyqtSlot()
    def select_key(self):
        selected_key = self.key_choice_box.currentText()
        if not selected_key:
            QMessageBox.warning(self, "No Selection", "Please select a key.")
            self.append_log("No key selected.")
            return

        self.select_key_thread = SelectKeyThread(self.driver, selected_key, self.button_elements)
        self.select_key_thread.log_updated.connect(self.update_log)
        self.select_key_thread.progress.connect(self.updateProgressBar)
        self.select_key_thread.status.connect(self.updateStatusLabel)
        self.select_key_thread.instrument_parts_signal.connect(self.update_instrument_parts)
        self.select_key_thread.started.connect(self.disable_search_section)
        self.select_key_thread.finished.connect(self.enable_search_section)
        self.select_key_thread.finished.connect(self.update_transposition_suggestions)  # Update suggestions after key selection
        self.select_key_thread.start()

        
        # Update transposition suggestions
        self.update_transposition_suggestions()
    
    def clear_transposition_suggestions(self):
        self.direct_transpositions_display.clear()
        self.closest_matches_display.clear()

    def normalize_key(self, key):
        return util_normalize_key(key)

    def update_transposition_suggestions(self):
        target_key = self.target_key_input.text().strip()
        if not target_key:
            self.clear_transposition_suggestions()
            return

        available_keys = [self.key_choice_box.itemText(i) for i in range(self.key_choice_box.count())]
        if not available_keys:
            self.clear_transposition_suggestions()
            return



        # Validate target key
        normalized_target_key = self.normalize_key(target_key)
        if normalized_target_key not in VALID_KEYS:
            QMessageBox.warning(
                self,
                "Invalid Key",
                f"Invalid target key: {target_key}. Please enter a valid key (e.g., C, D#, F).",
            )
            self.append_log(
                f"Invalid target key: {target_key}. Please enter a valid key (e.g., C, D#, F)."
            )
            self.clear_transposition_suggestions()
            return

        # Compute suggestions
        suggestions = self.get_transposition_suggestions(available_keys, [], target_key)

        # Update the GUI with the suggestions
        self.show_transposition_suggestions(suggestions)


    def get_transposition_suggestions(self, available_keys, instrument_parts, target_key):
        selected_instrument = self.instrument_choice_box.currentText().strip()

        suggestions = util_get_transposition_suggestions(
            available_keys,
            selected_instrument,
            target_key,
        )

        if not suggestions['direct'] and not suggestions['closest']:
            # Handle invalid key or instrument by checking validity manually
            normalized_target = util_normalize_key(target_key)
            if normalized_target not in VALID_KEYS:
                QMessageBox.warning(
                    self,
                    "Invalid Key",
                    f"Invalid target key: {target_key}. Please enter a valid key (e.g., C, D#, F).",
                )
                self.append_log(
                    f"Invalid target key: {target_key}. Please enter a valid key (e.g., C, D#, F)."
                )
            elif selected_instrument not in INSTRUMENT_TRANSPOSITIONS:
                self.append_log(
                    f"Instrument '{selected_instrument}' not recognized for transposition."
                )
        return suggestions





    def show_transposition_suggestions(self, suggestions):
        direct_matches = suggestions.get('direct', [])
        closest_matches = suggestions.get('closest', [])

        # Build direct matches text
        direct_text = ""
        if direct_matches:
            for match in direct_matches:
                # For direct transpositions, the difference is 0.
                direct_text += (f"- {match['instrument']} in '{match['key']}' (Perfect Unison) transposes to target key.\n\n")
        else:
            direct_text = "No direct transpositions available."

        # Build closest matches text
        closest_text = ""
        if closest_matches:
            for match in closest_matches:
                if match['interval_direction'] == 'none':
                    closest_text += (f"- {match['instrument']} in '{match['key']}' ({match['interval']}).\n\n")
                else:
                    closest_text += (f"- {match['instrument']} in '{match['key']}' ({match['interval']} {match['interval_direction']} target).\n\n")
        else:
            closest_text = "No close matches found."

        self.direct_transpositions_display.setPlainText(direct_text.strip())
        self.closest_matches_display.setPlainText(closest_text.strip())




    def get_key_name(self, semitone):
        semitone_to_key = {
            0: 'C',
            1: 'C#/Db',
            2: 'D',
            3: 'D#/Eb',
            4: 'E',
            5: 'F',
            6: 'F#/Gb',
            7: 'G',
            8: 'G#/Ab',
            9: 'A',
            10: 'A#/Bb',
            11: 'B'
        }
        return semitone_to_key.get(semitone % 12, 'Unknown')

    def get_interval_name(self, semitones):
        return util_get_interval_name(semitones)



    @pyqtSlot()
    def download_and_process_images(self, open_after_download=True):
        print("[DEBUG] download_and_process_images called")
        if not self.key_choice_box.currentText():
            QMessageBox.warning(self, "No Key", "Please select a key before downloading.")
            self.append_log("Please select a key before downloading.")
            return

        if not self.song_choice_box.currentText():
            QMessageBox.warning(self, "No Song", "Please select a song before downloading.")
            self.append_log("Please select a song before downloading.")
            return

        driver = self.driver
        key_choice_text = self.key_choice_box.currentText()
        selected_song_text = self.song_choice_box.currentText()
        selected_song_title = selected_song_text.split('\n')[0]
        selected_song_artist = selected_song_text.split('\n')[1] if len(selected_song_text.split('\n')) > 1 else "Unknown Artist"
        paths = self.paths
        download_horn_only = self.horn_checkbox.isChecked()
        selected_instruments = self.selected_instruments.copy()

        self.download_and_process_images_thread = DownloadAndProcessThread(
            driver, key_choice_text, selected_song_title, selected_song_artist,
            paths, selected_instruments, download_horn_only,
            open_after_download=open_after_download)
        self.download_and_process_images_thread.log_updated.connect(self.update_log)
        self.download_and_process_images_thread.progress.connect(self.updateProgressBar)
        self.download_and_process_images_thread.status.connect(self.updateStatusLabel)
        self.download_and_process_images_thread.started.connect(self.disable_all_sections)
        self.download_and_process_images_thread.finished.connect(self.enable_all_sections)
        self.download_and_process_images_thread.finished.connect(self.download_completed)
        self.download_and_process_images_thread.start()

    def download_completed(self):
        self.selected_instruments.clear()


    @pyqtSlot(list)
    def update_button_elements(self, new_elements):
        self.button_elements = new_elements

    @pyqtSlot(str, str)
    def update_song_info(self, new_song_info, image_url):
        self.song_info.append({'text': new_song_info, 'image_url': image_url})

    @pyqtSlot(str, str)
    def update_song_choice_box(self, new_choice, image_url):
        # Fetch the image data
        try:
            response = requests.get(image_url)
            image_data = response.content
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
    
            # # Resize the image to the desired dimensions (e.g., 64x64)
            # pixmap = pixmap.scaled(1024, 1024, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    
            icon = QIcon(pixmap)
        except Exception as e:
            self.append_log(f"Failed to load image: {e}")
            icon = QIcon()
    
        self.song_choice_box.addItem(icon, new_choice)

    @pyqtSlot(str)
    def update_key_choice_box(self, new_choice):
        self.key_choice_box.blockSignals(True)
        self.key_choice_box.addItem(new_choice)
        self.key_choice_box.blockSignals(False)

    @pyqtSlot(list)
    def update_instrument_parts(self, instrument_parts):
        self.instrument_parts = instrument_parts
        self.selected_instruments.clear()  # Clear previously selected instruments

        # Update the instrument_choice_box
        self.instrument_choice_box.blockSignals(True)  # Prevent triggering update_transposition_suggestions
        self.instrument_choice_box.clear()

        # Exclude "Conductor's Score" and any empty instruments
        available_instruments = [
            instrument for instrument in self.instrument_parts
            if instrument.strip() and instrument.strip() != "Conductor's Score"
        ]

        # Populate the instrument_choice_box
        self.instrument_choice_box.addItems(available_instruments)

        # Set default instrument if available
        if self.default_instrument in available_instruments:
            index = self.instrument_choice_box.findText(self.default_instrument)
            self.instrument_choice_box.setCurrentIndex(index)
        elif available_instruments:
            # If default instrument is not available, select the first instrument
            self.instrument_choice_box.setCurrentIndex(0)
        else:
            self.append_log("No available instruments to select.")
    
        self.instrument_choice_box.blockSignals(False)  # Re-enable signals

        if not self.instrument_parts:
            self.append_log("No instruments found for the selected song.")
            self.select_instruments_button.setEnabled(False)
        else:
            self.select_instruments_button.setEnabled(True)
        self.update_transposition_suggestions()



    @pyqtSlot(str)
    def update_log(self, new_log):
        self.append_log(new_log)

    @pyqtSlot(int)
    def insert_separator_slot(self, index):
        self.song_choice_box.insertSeparator(index)

    @pyqtSlot()
    def clear_song_info(self):
        self.song_info.clear()

    @pyqtSlot()
    def clear_song_choice_box(self):
        self.song_choice_box.clear()

    @pyqtSlot()
    def clear_key_choice_box(self):
        self.key_choice_box.clear()

    @pyqtSlot()
    def clear_button_elements(self):
        self.button_elements.clear()

    @pyqtSlot()
    def send_song_choice_box_count(self):
        count = self.song_choice_box.count()
        self.find_songs_thread.receive_song_choice_box_count.emit(count)

    @pyqtSlot()
    def check_search_results(self):
        if self.song_choice_box.count() == 0:
            QMessageBox.information(self, "No Results", "No songs were found for your search.")

    @pyqtSlot()
    def checkbox_state_changed(self):
        state = self.horn_checkbox.isChecked()
        self.download_and_process_images_thread.download_horn_only = state

    def disable_all_sections(self):
        self.disable_search_section()
        self.disable_song_selection()
        self.disable_key_selection()
        self.select_instruments_button.setEnabled(False)
        self.download_and_process_button.setEnabled(False)
        self.horn_checkbox.setEnabled(False)

    def enable_all_sections(self):
        self.enable_search_section()
        
        # Enable song selection only if a song hasn't been selected yet
        if not self.is_song_selected:
            self.enable_song_selection()
        
        self.enable_key_selection()
        if self.instrument_parts:
            self.select_instruments_button.setEnabled(True)
        self.download_and_process_button.setEnabled(True)
        self.horn_checkbox.setEnabled(True)



# Initialize the application
app = QApplication(sys.argv)

# Initialize our class
app_window = App()

# Show the window
app_window.show()

# Execute the application
sys.exit(app.exec_())