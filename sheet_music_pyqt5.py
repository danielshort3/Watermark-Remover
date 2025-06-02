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
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLineEdit, QProgressBar, QCheckBox,
                             QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QComboBox, QTextEdit, QGroupBox,
                             QDialog, QListWidget, QListWidgetItem, QDialogButtonBox)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (NoSuchElementException,
                                        StaleElementReferenceException, TimeoutException)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager
import requests
import torch
import torch.nn as nn
from torch.nn.functional import pad
from reportlab.pdfgen import canvas

# Local imports
# Assuming model_functions.py is available and contains required functions
from model_functions import UNet, VDSR, PIL_to_tensor, tensor_to_PIL, load_best_model


# Check if CUDA is available
cuda_available = torch.cuda.is_available()
print(f"CUDA available: {cuda_available}")


# XPath dictionary
xpaths = {
    'search_bar': '//*[@id="search-input-wrap"]/input',
    'songs_parent': '//*[@id="page-wrapper"]/ion-router-outlet/app-page-search/ion-content/div/div/div/app-search/div',
    'song_title': './div/a/div/h5',
    'song_text3': './div/a/div/span/span',
    'song_text2': './div/a/div/span',
    'song_image': './div/div[1]/div/app-product-audio-preview-image/div/img',
    'click_song': '//*[@id="page-wrapper"]/ion-router-outlet/app-page-search/ion-content/div/div/div/app-search/div/app-product-list-item[{index}]/div/a/div',
    'chords_button': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content/div/div/div[3]/div/div[1]/div[2]/div[1]/app-product-sheet-selector/div/div[1]/button',
    'orchestration_header': "//h3[contains(text(), 'Orchestration')]/ancestor::div[4]",
    'key_button': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content/div/div/div[3]/div/div[1]/div[2]/div[1]/app-product-sheet-selector/div/div[3]/app-product-selector-key/div/button',
    'key_parent': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content/div/div/div[3]/div/div[1]/div[2]/div[1]/app-product-sheet-selector/div/div[3]/app-product-selector-key/div/ul',
    'parts_button': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content/div/div/div[3]/div/div[1]/div[2]/div[1]/app-product-sheet-selector/div/div[2]/div/button',
    # 'parts_parent': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content//ul',
    'parts_parent': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content/div/div/div[3]/div/div[1]/div[2]/div[1]/app-product-sheet-selector/div/div[2]/div/ul',
    'parts_list': '//*[@id="page-wrapper"]/ion-router-outlet/app-product-page/ion-content//ul/li/button',
    'image_element': '//*[@id="preview-sheets"]/div/div[1]/div/img',
    'next_button': "//button[contains(@class, 'sheet-nav-gradient-button-right')]",
}

# Helper class for common Selenium operations
class SeleniumHelper:
    @staticmethod
    def click_element(driver, xpath, timeout=2, log_func=None):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            element.click()
            return True
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
            if log_func:
                log_func(f"Error clicking element at xpath: {xpath} - {str(e)}")
            return False

    @staticmethod
    def find_element(driver, xpath, timeout=2, log_func=None):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            return element
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
            if log_func:
                log_func(f"Error finding element at xpath: {xpath} - {str(e)}")
            return None

    @staticmethod
    def find_elements(driver, xpath, timeout=2, log_func=None):
        try:
            elements = WebDriverWait(driver, timeout).until(
                EC.presence_of_all_elements_located((By.XPATH, xpath))
            )
            return elements
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
            if log_func:
                log_func(f"Error finding elements at xpath: {xpath} - {str(e)}")
            return []

    @staticmethod
    def send_keys_to_element(driver, xpath, keys, timeout=2, log_func=None):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            element.clear()
            element.send_keys(keys)
            return True
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException) as e:
            if log_func:
                log_func(f"Error sending keys to element at xpath: {xpath} - {str(e)}")
            return False

    @staticmethod
    def click_dynamic_element(driver, xpath_template, index, timeout=2, log_func=None):
        xpath = xpath_template.format(index=index)
        return SeleniumHelper.click_element(driver, xpath, timeout=timeout, log_func=log_func)


class FindSongsThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    song_info_updated = pyqtSignal(str, str)  # Updated to emit song text and image URL
    song_choice_box_updated = pyqtSignal(str, str)  # Updated to emit song text and image URL
    log_updated = pyqtSignal(str)
    clear_song_info = pyqtSignal()
    clear_song_choice_box = pyqtSignal()
    clear_key_choice_box = pyqtSignal()
    request_song_choice_box_count = pyqtSignal()
    receive_song_choice_box_count = pyqtSignal(int)
    insert_separator_in_song_choice_box = pyqtSignal(int)

    def __init__(self, driver, user_song_choice):
        super().__init__()
        self.driver = driver
        self.user_song_choice = user_song_choice
        self.song_choice_box_count = 0
        self.receive_song_choice_box_count.connect(self.set_song_choice_box_count)

    def set_song_choice_box_count(self, count):
        self.song_choice_box_count = count

    def run(self):
        self.status.emit("")
        self.progress.emit(0)
        self.clear_song_info.emit()
        self.clear_song_choice_box.emit()
        self.clear_key_choice_box.emit()

        url = "https://www.praisecharts.com/search"
        self.driver.get(url)

        # Use SeleniumHelper to interact with elements
        search_bar_xpath = xpaths['search_bar']
        if not SeleniumHelper.send_keys_to_element(self.driver, search_bar_xpath, self.user_song_choice, log_func=self.log_updated.emit):
            self.log_updated.emit("Error interacting with the search bar.")
            return

        songs_counter = 0

        songs_parent_xpath = xpaths['songs_parent']
        songs_parent = SeleniumHelper.find_element(self.driver, songs_parent_xpath, timeout=10, log_func=self.log_updated.emit)
        if not songs_parent:
            self.log_updated.emit("Error finding songs parent element.")
            return

        time.sleep(2)  # Ensure elements are loaded
        songs_children = songs_parent.find_elements("xpath", './app-product-list-item')

        for idx, child in enumerate(songs_children, 1):
            title = ''
            text2 = ''
            text3 = ''
            image_url = ''
        
            try:
                title = child.find_element("xpath", xpaths['song_title']).text
            except NoSuchElementException:
                pass
        
            try:
                text3 = child.find_element("xpath", xpaths['song_text3']).text
            except NoSuchElementException:
                pass
        
            if text3 != '':
                try:
                    text2 = child.find_element("xpath", xpaths['song_text2']).text.split("\n")[0]
                except NoSuchElementException:
                    pass
        
            if text3 == text2:
                text2 = ''
        
            # Build element_text only from non-empty parts
            element_text_parts = []
            if title.strip():
                element_text_parts.append(title.strip())
            if text2.strip():
                element_text_parts.append(text2.strip())
            if text3.strip():
                element_text_parts.append(text3.strip())
            element_text = '\n'.join(element_text_parts)
        
            if not element_text:
                continue  # Skip this iteration if element_text is empty
        
            try:
                image_element = child.find_element("xpath", xpaths['song_image'])
                image_url = image_element.get_attribute('src')
            except NoSuchElementException:
                image_url = ''
        
            if text3 != '':
                self.song_info_updated.emit(element_text, image_url)
                self.song_choice_box_updated.emit(element_text, image_url)
                songs_counter += 1
                self.request_song_choice_box_count.emit()
            else:
                self.song_info_updated.emit(title, image_url)


        self.log_updated.emit(f"Found {songs_counter} songs for search: {self.user_song_choice}")


class SelectSongThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    button_elements_signal = pyqtSignal(list)
    log_updated = pyqtSignal(str)
    clear_key_choice_box = pyqtSignal()
    key_choice_box_updated = pyqtSignal(str)
    clear_button_elements = pyqtSignal()
    instrument_parts_signal = pyqtSignal(list)  # Signal to emit instrument parts
    song_selection_failed = pyqtSignal()  # New signal to handle selection failures

    def __init__(self, driver, selected_song, selected_song_index, selected_song_title, user_song_choice):
        super().__init__()
        self.driver = driver
        self.selected_song = selected_song
        self.user_song_choice = user_song_choice
        self.selected_song_index = selected_song_index
        self.selected_song_title = selected_song_title

    def run(self):
        try:
            self.log_updated.emit(f"Selected song: {self.selected_song_title}")

            # Click the selected song using SeleniumHelper
            click_xpath_template = xpaths['click_song']
            if not SeleniumHelper.click_dynamic_element(self.driver, click_xpath_template, self.selected_song_index + 1, log_func=self.log_updated.emit):
                self.log_updated.emit("Error clicking the song.")
                raise Exception("Error clicking the song.")

            # Click "Chords & Lyrics" button
            chords_click_xpath = xpaths['chords_button']
            if not SeleniumHelper.click_element(self.driver, chords_click_xpath, log_func=self.log_updated.emit):
                self.log_updated.emit("Error clicking 'Chords & Lyrics' button.")
                raise Exception("Error clicking 'Chords & Lyrics' button.")

            # Click "Orchestration" header
            orch_click_xpath = xpaths['orchestration_header']
            if not SeleniumHelper.click_element(self.driver, orch_click_xpath, log_func=self.log_updated.emit):
                self.log_updated.emit("Orchestration not found for this song.")
                self.song_selection_failed.emit()
                return

            # Access key menu
            key_click_xpath = xpaths['key_button']
            if not SeleniumHelper.click_element(self.driver, key_click_xpath, log_func=self.log_updated.emit):
                self.log_updated.emit("Error accessing key menu.")
                raise Exception("Error accessing key menu.")

            key_parent_xpath = xpaths['key_parent']
            key_parent_element = SeleniumHelper.find_element(self.driver, key_parent_xpath, log_func=self.log_updated.emit)
            if not key_parent_element:
                self.log_updated.emit("Error finding key parent element.")
                raise Exception("Error finding key parent element.")

            button_elements = key_parent_element.find_elements(by=By.TAG_NAME, value='button')
            if not button_elements:
                self.log_updated.emit("No key menu found.")
                raise Exception("No key menu found.")

            keys = []
            self.clear_key_choice_box.emit()

            for button in button_elements:
                keys.append(button.text)
                self.key_choice_box_updated.emit(button.text)

            # Automatically select the first key
            first_button = button_elements[0]
            first_button.click()

            formatted_keys = ', '.join(keys)
            self.log_updated.emit(f"Found keys: {formatted_keys}")
            self.log_updated.emit(f"Automatically selected key: {keys[0]}")
            self.button_elements_signal.emit(button_elements)

            # Call find_parts to get instrument parts
            self.find_parts()

        except Exception as e:
            self.log_updated.emit(f"Exception during song selection: {str(e)}")
            self.song_selection_failed.emit()



    def find_parts(self):
        # Click "Parts" button
        parts_button_xpath = xpaths['parts_button']
        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error accessing parts menu.")
            return

        # Find parts elements
        parts_parent_xpath = xpaths['parts_parent']
        parts_parent_element = SeleniumHelper.find_element(self.driver, parts_parent_xpath, log_func=self.log_updated.emit)
        if not parts_parent_element:
            self.log_updated.emit("Error finding parts parent element.")
            return

        parts_elements = parts_parent_element.find_elements(by=By.TAG_NAME, value='button')
        if not parts_elements:
            self.log_updated.emit("No parts menu found.")
            return

        instrument_parts = []

        for part in parts_elements:
            part_text = part.text.strip()
            if not part_text:
                continue  # Skip empty instrument names
            if 'cover' not in part_text.lower() and 'lead sheet' not in part_text.lower():
                instrument_parts.append(part_text)

        # Close the parts menu
        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error closing parts menu.")
            return

        self.instrument_parts_signal.emit(instrument_parts)



class SelectKeyThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    log_updated = pyqtSignal(str)
    instrument_parts_signal = pyqtSignal(list)  # Signal to emit instrument parts

    def __init__(self, driver, selected_key, button_elements):
        super().__init__()
        self.driver = driver
        self.selected_key = selected_key
        self.button_elements = button_elements.copy()

    def run(self):
        # Click the key button
        key_click_xpath = xpaths['key_button']
        if not SeleniumHelper.click_element(self.driver, key_click_xpath, log_func=self.log_updated.emit):
            pass

        # Click the selected key
        button_clicked = False

        for button in self.button_elements:
            if self.selected_key == button.text:
                button.click()
                button_clicked = True
                break

        if not button_clicked:
            # Close the key menu if the key was not found
            SeleniumHelper.click_element(self.driver, key_click_xpath, log_func=self.log_updated.emit)

        self.log_updated.emit(f"Selected key: {self.selected_key}")

        # Call find_parts to get instrument parts
        self.find_parts()

    def find_parts(self):
        # Click "Parts" button
        parts_button_xpath = xpaths['parts_button']
        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error accessing parts menu.")
            return

        # Find parts elements
        parts_list_xpath = xpaths['parts_list']
        parts_elements = SeleniumHelper.find_elements(self.driver, parts_list_xpath, log_func=self.log_updated.emit)
        if not parts_elements:
            self.log_updated.emit("No parts menu found.")
            return

        instrument_parts = []

        for part in parts_elements:
            part_text = part.text.lower()
            if 'cover' not in part_text and 'lead sheet' not in part_text:
                instrument_parts.append(part.text)

        # Close the parts menu
        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error closing parts menu.")
            return

        self.instrument_parts_signal.emit(instrument_parts)


class DownloadAndProcessThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    log_updated = pyqtSignal(str)

    def __init__(self, driver, key_choice_text, selected_song_title, selected_song_artist, paths, selected_instruments, download_horn_only=False):
        super().__init__()
        self.driver = driver
        self.key_choice_text = key_choice_text
        self.selected_song_title = selected_song_title
        self.selected_song_artist = selected_song_artist
        self.paths = paths
        self.download_horn_only = download_horn_only
        self.selected_instruments = selected_instruments
        self.instrument_parts = []  # Initialize here for debugging
        self.full_paths = []  # Initialize here for debugging
        self.images_by_instrument = defaultdict(list)  # Initialize here for debugging
        self.log_updated.emit("Initialized DownloadAndProcessThread")

    def run(self):
        self.log_updated.emit("Starting run method")
        try:
            song_dir, temp_dir = self.initialize_directories()
            self.log_updated.emit(f"Directories initialized: song_dir={song_dir}, temp_dir={temp_dir}")
            
            self.find_parts()
            self.download_images(temp_dir)
            self.remove_watermarks()
            self.upscale_images()
            
            torch.cuda.empty_cache()
            self.create_pdfs(song_dir, temp_dir)
            self.cleanup(temp_dir)
            self.open_directory(song_dir)
        except Exception as e:
            self.log_updated.emit(f"Exception in run: {str(e)}")

    def initialize_directories(self):
        self.log_updated.emit("Initializing directories")
        try:
            key_dir = self.key_choice_text
            title_dir = re.sub(r'[<>:"\\|?* ]', '_', self.selected_song_title.replace("/", "-"))
            artist_dir = re.sub(r'[<>:"\\|?* ]', '_', self.selected_song_artist.replace("/", "-"))
            main_dir = self.paths['download_dir']
            song_dir = os.path.join(main_dir, title_dir, artist_dir, key_dir)
            os.makedirs(song_dir, exist_ok=True)
            temp_dir = os.path.join(main_dir, title_dir, artist_dir, self.paths['temp_sub_dir'])
            os.makedirs(temp_dir, exist_ok=True)
            self.log_updated.emit(f"Directories created: song_dir={song_dir}, temp_dir={temp_dir}")
            return song_dir, temp_dir
        except Exception as e:
            self.log_updated.emit(f"Error in initialize_directories: {str(e)}")
            raise

    def find_parts(self):
        self.log_updated.emit("Finding parts")
        # Click "Parts" button
        parts_button_xpath = xpaths['parts_button']
        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error accessing parts menu.")
            return

        # Find parts elements
        parts_parent_xpath = xpaths['parts_parent']
        parts_parent_element = SeleniumHelper.find_element(self.driver, parts_parent_xpath, log_func=self.log_updated.emit)
        if not parts_parent_element:
            self.log_updated.emit("Error finding parts parent element.")
            return

        parts_elements = parts_parent_element.find_elements(by=By.TAG_NAME, value='button')
        if not parts_elements:
            self.log_updated.emit("No parts menu found.")
            return

        self.instrument_parts = []

        for part in parts_elements:
            part_text = part.text.lower()
            if 'cover' not in part_text and 'lead sheet' not in part_text:
                self.instrument_parts.append(part.text)

        # Close the parts menu
        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error closing parts menu.")
            return

        self.log_updated.emit(f"Instrument parts found: {self.instrument_parts}")

    def download_images(self, temp_dir):
        self.log_updated.emit("Starting download_images")

        # Define variables to track downloaded URLs and paths
        self.images_by_instrument = defaultdict(list)
        downloaded_urls = set()

        try:
            image_xpath = xpaths['image_element']
            next_button_xpath = xpaths['next_button']
            parts_button_xpath = xpaths['parts_button']
            parts_list_xpath = xpaths['parts_list']

            # Regex pattern to extract the page number (last 3 digits before .png)
            page_number_pattern = re.compile(r'_(\d{3})\.png$')

            instruments_to_process = []

            if self.download_horn_only:
                self.log_updated.emit("French horn only mode enabled.")
                # Directly select "French Horn" from the parts
                horn_instrument = None
                for part in self.instrument_parts:
                    if 'french horn' in part.lower():
                        horn_instrument = part
                        instruments_to_process.append(part)
                        self.log_updated.emit(f"Selected instrument for French horn only: {part}")
                        break
                if not horn_instrument:
                    self.log_updated.emit("No instrument with 'French Horn' found.")
            elif self.selected_instruments:
                instruments_to_process = self.selected_instruments
                self.log_updated.emit(f"Selected instruments to process: {instruments_to_process}")
            else:
                # No instruments selected; process all parts
                instruments_to_process = self.instrument_parts
                self.log_updated.emit(f"No instruments selected. Processing all parts: {instruments_to_process}")

            for instrument in instruments_to_process:
                self.log_updated.emit(f"Processing instrument: {instrument}")

                # Click the "Parts" button
                if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
                    self.log_updated.emit('Error clicking "Parts" button')
                    continue
                self.log_updated.emit('Clicked "Parts" button')

                # Find and click the instrument in the dropdown list
                instrument_list_elements = SeleniumHelper.find_elements(self.driver, parts_list_xpath, log_func=self.log_updated.emit)
                if not instrument_list_elements:
                    self.log_updated.emit("Error finding instrument list elements.")
                    continue

                instrument_clicked = False
                for button in instrument_list_elements:
                    button_text = button.text.strip()
                    normalized_instrument = instrument.lower().replace(",", "").replace("-", " ").strip()
                    normalized_button_text = button_text.lower().replace(",", "").replace("-", " ").strip()

                    if normalized_instrument == normalized_button_text:
                        try:
                            button.click()
                            instrument_clicked = True
                            self.log_updated.emit(f"Selected instrument: {instrument}")
                            break
                        except Exception as e:
                            self.log_updated.emit(f"Error clicking instrument '{instrument}': {str(e)}")
                            continue

                if not instrument_clicked:
                    self.log_updated.emit(f"Could not find instrument: {instrument} in the dropdown list.")
                    continue

                # Download images for the selected instrument
                previous_page_number = None

                while True:
                    # Locate the image element
                    image_element = SeleniumHelper.find_element(self.driver, image_xpath, log_func=self.log_updated.emit)
                    if not image_element:
                        self.log_updated.emit(f"No more images found for {instrument}.")
                        break

                    image_url = image_element.get_attribute('src')

                    # Avoid downloading duplicate URLs
                    if image_url in downloaded_urls:
                        self.log_updated.emit(f"URL already downloaded: {image_url}, skipping.")
                        if not self.click_next_button(next_button_xpath):
                            break
                        continue

                    # Extract the page number
                    match = page_number_pattern.search(image_url)
                    if match:
                        current_page_number = match.group(1)
                    else:
                        self.log_updated.emit(f"Could not extract page number from URL: {image_url}")
                        break

                    # If the page number resets to "001", stop downloading for this instrument
                    if previous_page_number and current_page_number == "001":
                        self.log_updated.emit(f"Page number reset to '001'. Stopping download for {instrument}.")
                        break

                    # Download the image
                    self.status.emit(f"Downloading {os.path.basename(image_url)}")
                    full_path = os.path.join(temp_dir, os.path.basename(image_url))
                    downloaded_urls.add(image_url)

                    try:
                        response = requests.get(image_url)
                        if response.status_code == 200:
                            with open(full_path, 'wb') as f:
                                f.write(response.content)
                            self.log_updated.emit(f"Downloaded image: {os.path.basename(image_url)}")
                            self.images_by_instrument[instrument].append(full_path)
                        else:
                            self.log_updated.emit(f"Failed to download image: {os.path.basename(image_url)} - Status code: {response.status_code}")

                        # Click the next button to move to the next image
                        if not self.click_next_button(next_button_xpath):
                            self.log_updated.emit(f"No next button available. Stopping download for {instrument}.")
                            break

                    except Exception as e:
                        self.log_updated.emit(f"An error occurred while downloading images: {e}")
                        break

                    # Update the previous page number
                    previous_page_number = current_page_number

        except Exception as e:
            self.log_updated.emit(f"Exception in download_images: {str(e)}")

    def click_next_button(self, next_button_xpath):
        """Clicks the 'Next' button to navigate through images."""
        self.log_updated.emit("Attempting to click next button")
        if SeleniumHelper.click_element(self.driver, next_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Clicked next button")
            return True
        else:
            self.log_updated.emit("Error clicking next button or no next button available.")
            return False
        return False

    def remove_watermarks(self):
        self.log_updated.emit("Starting remove_watermarks")
        try:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            wm_model = UNet().to(self.device)
            load_best_model(wm_model, self.paths['wm_model_path'])
            wm_model.eval()

            self.wm_outputs = defaultdict(list)
            total_images = sum(len(paths) for paths in self.images_by_instrument.values())
            processed_images = 0

            self.status.emit("Removing watermarks")
            self.progress.emit(0)

            with torch.inference_mode():
                for instrument, paths in self.images_by_instrument.items():
                    for path in paths:
                        try:
                            image_tensor = PIL_to_tensor(path).unsqueeze(0).to(self.device)
                            wm_output = wm_model(image_tensor)
                            self.wm_outputs[instrument].append(wm_output.cpu())
                            self.status.emit(f"Unwatermarking {os.path.basename(path)}")
                            processed_images += 1
                            progress_value = int((processed_images / total_images) * 100)
                            self.progress.emit(progress_value)
                        except Exception as e:
                            self.log_updated.emit(f"Error unwatermarking {path}: {str(e)}")

            self.log_updated.emit("Removed watermarks")
        except Exception as e:
            self.log_updated.emit(f"Exception in remove_watermarks: {str(e)}")

    def upscale_images(self):
        self.log_updated.emit("Starting upscale_images")
        try:
            image_base_width, image_base_height = 1700, 2200

            us_model = VDSR().to(self.device)
            load_best_model(us_model, self.paths['us_model_path'])
            us_model.eval()

            upsample = nn.Upsample(size=(image_base_height, image_base_width), mode='nearest')

            self.us_outputs = defaultdict(list)
            total_images = sum(len(outputs) for outputs in self.wm_outputs.values())
            processed_images = 0

            self.status.emit("Upscaling images")
            self.progress.emit(0)

            with torch.inference_mode():
                for instrument, wm_outputs in self.wm_outputs.items():
                    for wm_output in wm_outputs:
                        try:
                            # Upsample the image
                            wm_output_upscaled = upsample(wm_output)
                            padding_size = 16
                            patch_height = 550
                            patch_width = 850

                            padding = (padding_size, padding_size, padding_size, padding_size)
                            wm_output_upscaled_padded = nn.functional.pad(wm_output_upscaled, padding, value=1.0)
                            us_output = torch.zeros_like(wm_output_upscaled).cpu()

                            # Patch processing
                            for i in range(0, wm_output_upscaled.shape[-2], patch_height):
                                for j in range(0, wm_output_upscaled.shape[-1], patch_width):
                                    patch = wm_output_upscaled_padded[:, :, i:i + patch_height + padding_size * 2, j:j + patch_width + padding_size * 2].cpu()
                                    us_patch = us_model(patch.to(self.device))
                                    us_patch = us_patch[:, :, padding_size:-padding_size, padding_size:-padding_size]
                                    us_output[:, :, i:i + patch_height, j:j + patch_width] = us_patch.cpu()

                            self.us_outputs[instrument].append(us_output)
                            self.status.emit(f"Upscaled image for {instrument}")
                            processed_images += 1
                            progress_value = int((processed_images / total_images) * 100)
                            self.progress.emit(progress_value)
                        except Exception as e:
                            self.log_updated.emit(f"Error upscaling image for {instrument}: {str(e)}")

            self.log_updated.emit("Upscaled images")
        except Exception as e:
            self.log_updated.emit(f"Exception in upscale_images: {str(e)}")

    def create_pdfs(self, song_dir, temp_dir):
        self.log_updated.emit("Starting create_pdfs")
        try:
            img_width, img_height = 1700, 2200

            total_instruments = len(self.us_outputs)
            processed_instruments = 0

            for instrument, us_outputs in self.us_outputs.items():
                # Get the original filename from the first image path
                image_paths = self.images_by_instrument[instrument]
                first_image_path = image_paths[0]
                first_image_filename = os.path.basename(first_image_path)
                # Remove the page number from the filename
                base_filename = re.sub(r'_\d{3}\.png$', '', first_image_filename)
                # Also remove any extension
                base_filename = os.path.splitext(base_filename)[0]
                pdf_filename = f"{base_filename}.pdf"
                pdf_path = os.path.join(song_dir, pdf_filename)
                c = canvas.Canvas(pdf_path, pagesize=(img_width, img_height))
                self.status.emit(f"Creating {pdf_filename}")

                for idx, image_tensor in enumerate(us_outputs):
                    try:
                        # Convert tensor to PIL image
                        image_pil = tensor_to_PIL(image_tensor.squeeze(0))  # Remove batch dimension

                        # Create a sanitized filename for the temporary image
                        temp_image_name = f"temp_image_{base_filename}_{idx}.png"
                        temp_image_path = os.path.join(temp_dir, temp_image_name)
                        image_pil.save(temp_image_path)

                        # Draw image on PDF
                        c.drawImage(temp_image_path, 0, 0, width=img_width, height=img_height)
                        c.showPage()

                        # Remove temporary image
                        os.remove(temp_image_path)
                    except Exception as e:
                        self.log_updated.emit(f"Error creating PDF for {instrument}, image {idx}: {str(e)}")

                c.save()
                self.log_updated.emit(f"Created PDF: {pdf_path}")
                processed_instruments += 1
                progress_value = int((processed_instruments / total_instruments) * 100)
                self.progress.emit(progress_value)

            self.status.emit(f"Process completed for {self.selected_song_title}")
            self.progress.emit(0)
            self.log_updated.emit("Processed images and created PDFs")
        except Exception as e:
            self.log_updated.emit(f"Exception in create_pdfs: {str(e)}")
        
    def cleanup(self, temp_dir):
        self.log_updated.emit("Starting cleanup")
        try:
            for paths in self.images_by_instrument.values():
                for path in paths:
                    os.remove(path)
                    self.log_updated.emit(f"Removed file: {path}")
            os.rmdir(temp_dir)
            self.log_updated.emit(f"Removed temp directory: {temp_dir}")
            self.log_updated.emit(f"Process completed for song: {self.selected_song_title}")
        except Exception as e:
            self.log_updated.emit(f"Exception in cleanup: {str(e)}")

    def open_directory(self, path):
        self.log_updated.emit(f"Attempting to open directory: {path}")
        try:
            if not os.environ.get('DISPLAY') and platform.system() == 'Linux':
                self.log_updated.emit("No display server available. Skipping open directory.")
                return

            if platform.system() == "Windows":
                # Redirect stdout and stderr to suppress errors
                subprocess.run(['explorer', path.replace('/', '\\')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif platform.system() == "Darwin":
                # Redirect stdout and stderr to suppress errors
                subprocess.run(['open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif platform.system() == "Linux":
                # Redirect stdout and stderr to suppress errors
                subprocess.run(['xdg-open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                self.log_updated.emit(f"Unsupported platform: {platform.system()}")
        except Exception as e:
            self.log_updated.emit(f"Exception in open_directory: {str(e)}")
            self.log_updated.emit(f"Unsupported platform: {platform.system()}")


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


        self.setWindowTitle("Praise Charts Music Downloader")
        self.setMinimumWidth(600)
        self.setMaximumWidth(1200)
        self.setMinimumHeight(800)
        self.setMaximumHeight(1200)

        # Styling and Font
        self.setFont(QFont('Arial', 9))  # Reduced font size to make the text smaller
        self.setStyleSheet("""
            QWidget {
                background-color: #fafafa;
            }
            QLineEdit, QComboBox, QTextEdit, QProgressBar {
                background-color: white;
                color: #444444;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-size: 10pt;  /* Adjusted font size */
            }
            QPushButton {
                background-color: #ed3124;
                color: white;
                border-radius: 4px;
                padding: 5px 20px;
                min-height: 20px;
                font-size: 10pt;  /* Adjusted font size */
            }
            QPushButton:hover {
                background-color: #c7271d;
            }
            QPushButton:disabled {
                background-color: #AAAAAA;
            }
            QLabel {
                color: #333333;
                font-weight: bold;
                font-size: 10pt;  /* Adjusted font size */
            }
            QGroupBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                margin-top: 10px;
                padding: 10px;
                font-size: 9pt;  /* Adjusted font size */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 3px;
                background-color: #fafafa;
            }
            QProgressBar {
                text-align: center;
                font-size: 10pt;  /* Adjusted font size */
            }
            QProgressBar::chunk {
                background-color: #ed3124;
            }
            """)


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

    def open_instrument_selection_dialog(self):
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
        self.find_songs_thread.start()

        # Disable song selection UI until search completes
        self.disable_song_selection()

    @pyqtSlot()
    def select_song(self):
        selected_song = self.song_choice_box.currentText()
        if not selected_song:
            self.append_log("No song selected.")
            return
    
        selected_song_index = None
        for idx, song in enumerate(self.song_info):
            if song['text'] == selected_song:
                selected_song_index = idx
                break
    
        if selected_song_index is None:
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
        key = key.strip()
        if not key:
            return ""
        # If the key contains additional descriptors (e.g., "minor"), take only the first part.
        key = key.split()[0]
        # Ensure the note letter is uppercase.
        note = key[0].upper()
        # Preserve the accidental as entered, converting any uppercase "B" used for flats to lowercase.
        accidental = key[1:].replace("B", "b")
        return note + accidental

    def update_transposition_suggestions(self):
        target_key = self.target_key_input.text().strip()
        if not target_key:
            self.clear_transposition_suggestions()
            return

        available_keys = [self.key_choice_box.itemText(i) for i in range(self.key_choice_box.count())]
        if not available_keys:
            self.clear_transposition_suggestions()
            return

        instrument_parts = self.instrument_parts
        if not instrument_parts:
            self.clear_transposition_suggestions()
            return

        # Validate target key
        valid_keys = {'C', 'C#', 'Db', 'D', 'D#', 'Eb', 'E', 'F', 'F#', 'Gb',
                     'G', 'G#', 'Ab', 'A', 'A#', 'Bb', 'B'}
        normalized_target_key = self.normalize_key(target_key)
        if normalized_target_key not in valid_keys:
            self.append_log(f"Invalid target key: {target_key}. Please enter a valid key (e.g., C, D#, F).")
            self.clear_transposition_suggestions()
            return

        # Compute suggestions
        suggestions = self.get_transposition_suggestions(available_keys, instrument_parts, target_key)

        # Update the GUI with the suggestions
        self.show_transposition_suggestions(suggestions)


    def get_transposition_suggestions(self, available_keys, instrument_parts, target_key):
        key_to_semitone = {
            'C': 0, 'C#': 1, 'Db': 1,
            'D': 2, 'D#': 3, 'Eb': 3,
            'E': 4, 'F': 5, 'F#': 6, 'Gb': 6,
            'G': 7, 'G#': 8, 'Ab': 8,
            'A': 9, 'A#': 10, 'Bb': 10,
            'B': 11,
        }

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

        instrument_transpositions = {
            'Rhythm Chart': 0,
            'Acoustic Guitar': 0,
            'Flute 1/2': 0,
            'Flute/Oboe 1/2/3': 0,
            'Oboe': 0,
            'Clarinet 1/2': -2,
            'Bass Clarinet': -2,
            'Bassoon': 0,
            'French Horn 1/2': -7,
            'Trumpet 1,2': -2,
            'Trumpet 3': -2,
            'Trombone 1/2': 0,
            'Trombone 3/Tuba': 0,
            'Alto Sax': -9,
            'Tenor Sax 1/2': -2,
            'Bari Sax': -9,
            'Timpani': 0,
            'Percussion': 0,
            'Violin 1/2': 0,
            'Viola': 0,
            'Cello': 0,
            'Double Bass': 0,
            'String Reduction': 0,
            'String Bass': 0,
            'Lead Sheet (SAT)': 0,
        }

        # Normalize and validate the target key.
        target_key = self.normalize_key(target_key)
        if target_key not in key_to_semitone:
            self.append_log(f"Invalid target key: {target_key}. Please enter a valid key (e.g., C, D#, F).")
            return {'direct': [], 'closest': []}

        target_semitone = key_to_semitone[target_key]

        # Get the selected instrument from the dropdown.
        selected_instrument = self.instrument_choice_box.currentText().strip()

        if selected_instrument not in instrument_transpositions:
            self.append_log(f"Instrument '{selected_instrument}' not recognized for transposition.")
            return {'direct': [], 'closest': []}

        matches_direct = []
        matches_closest = []

        for instrument, T_O in instrument_transpositions.items():
            if instrument == selected_instrument:
                continue  # Skip the selected instrument itself.

            # Calculate the required written key for instrument O to sound in the target key.
            # K_O = (target_semitone - T_O) mod 12
            required_written_semitone = (target_semitone - T_O) % 12
            required_written_key = semitone_to_key.get(required_written_semitone, 'Unknown')

            if required_written_key in available_keys:
                matches_direct.append({
                    'instrument': instrument,
                    'key': required_written_key,
                    'difference': 0,
                    'interval_direction': 'none',
                    'interval': 'Perfect Unison'
                })
            else:
                # Find the closest available key.
                available_semitones = [key_to_semitone[k] for k in available_keys if k in key_to_semitone]
                if not available_semitones:
                    continue  # No available keys to compare.

                diffs = [(abs(semitone - required_written_semitone), semitone) for semitone in available_semitones]
                diffs.sort(key=lambda x: x[0])
                closest_diff, closest_semitone = diffs[0]
                closest_key = semitone_to_key.get(closest_semitone, 'Unknown')

                if closest_semitone > required_written_semitone:
                    interval_direction = 'above'
                elif closest_semitone < required_written_semitone:
                    interval_direction = 'below'
                else:
                    interval_direction = 'none'

                interval_name = self.get_interval_name(closest_diff)

                matches_closest.append({
                    'instrument': instrument,
                    'key': closest_key,
                    'difference': closest_diff,
                    'interval_direction': interval_direction,
                    'interval': interval_name
                })

        matches_closest.sort(key=lambda s: s['difference'])

        return {'direct': matches_direct, 'closest': matches_closest}





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
        intervals = {
            0: 'Perfect Unison',
            1: 'Minor Second',
            2: 'Major Second',
            3: 'Minor Third',
            4: 'Major Third',
            5: 'Perfect Fourth',
            6: 'Tritone',
            7: 'Perfect Fifth',
            8: 'Minor Sixth',
            9: 'Major Sixth',
            10: 'Minor Seventh',
            11: 'Major Seventh',
            12: 'Octave'
        }
        return intervals.get(semitones % 12, f'{semitones} semitones')



    @pyqtSlot()
    def download_and_process_images(self):
        if not self.key_choice_box.currentText():
            self.append_log("Please select a key before downloading.")
            return

        if not self.song_choice_box.currentText():
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
            driver, key_choice_text, selected_song_title, selected_song_artist, paths, selected_instruments, download_horn_only)
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