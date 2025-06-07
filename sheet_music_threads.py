"""Thread classes used by the sheet music downloader GUI."""

import os
import re
import platform
import subprocess
import time
from collections import defaultdict
import threading

import requests
import torch
import torch.nn as nn
from PyQt5.QtCore import QThread, pyqtSignal
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from reportlab.pdfgen import canvas

from model_functions import UNet, VDSR, PIL_to_tensor, tensor_to_PIL, load_best_model
from selenium_utils import SeleniumHelper, xpaths

# Global lock to ensure file operations are thread-safe
file_lock = threading.Lock()


class FindSongsThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    song_info_updated = pyqtSignal(str, str)
    song_choice_box_updated = pyqtSignal(str, str)
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

        time.sleep(2)
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

            if text3:
                try:
                    text2 = child.find_element("xpath", xpaths['song_text2']).text.split("\n")[0]
                except NoSuchElementException:
                    pass

            if text3 == text2:
                text2 = ''

            element_text_parts = [p.strip() for p in (title, text2, text3) if p.strip()]
            element_text = '\n'.join(element_text_parts)
            if not element_text:
                continue

            try:
                image_element = child.find_element("xpath", xpaths['song_image'])
                image_url = image_element.get_attribute('src')
            except NoSuchElementException:
                image_url = ''

            is_song = False
            if text3:
                lower = text3.lower()
                if 'collection' not in lower and 'book' not in lower:
                    is_song = True

            if is_song:
                self.song_info_updated.emit(element_text, image_url)
                self.song_choice_box_updated.emit(element_text, image_url)
                songs_counter += 1
                self.request_song_choice_box_count.emit()
                if songs_counter >= 5:
                    break
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
    instrument_parts_signal = pyqtSignal(list)
    song_selection_failed = pyqtSignal()

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
            click_xpath_template = xpaths['click_song']
            if not SeleniumHelper.click_dynamic_element(self.driver, click_xpath_template, self.selected_song_index + 1, log_func=self.log_updated.emit):
                self.log_updated.emit("Error clicking the song.")
                raise Exception("Error clicking the song.")

            chords_click_xpath = xpaths['chords_button']
            if not SeleniumHelper.click_element(self.driver, chords_click_xpath, log_func=self.log_updated.emit):
                self.log_updated.emit("Error clicking 'Chords & Lyrics' button.")
                raise Exception("Error clicking 'Chords & Lyrics' button.")

            orch_click_xpath = xpaths['orchestration_header']
            if not SeleniumHelper.click_element(self.driver, orch_click_xpath, log_func=self.log_updated.emit):
                self.log_updated.emit("Orchestration not found for this song.")
                self.song_selection_failed.emit()
                return

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

            first_button = button_elements[0]
            first_button.click()
            formatted_keys = ', '.join(keys)
            self.log_updated.emit(f"Found keys: {formatted_keys}")
            self.log_updated.emit(f"Automatically selected key: {keys[0]}")
            self.button_elements_signal.emit(button_elements)
            self.find_parts()

        except Exception as e:
            self.log_updated.emit(f"Exception during song selection: {str(e)}")
            self.song_selection_failed.emit()

    def find_parts(self):
        print("[DEBUG] Finding instrument parts")
        parts_button_xpath = xpaths['parts_button']
        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error accessing parts menu.")
            return

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
                continue
            if 'cover' not in part_text.lower() and 'lead sheet' not in part_text.lower():
                instrument_parts.append(part_text)

        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error closing parts menu.")
            return

        self.instrument_parts_signal.emit(instrument_parts)


class SelectKeyThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    log_updated = pyqtSignal(str)
    instrument_parts_signal = pyqtSignal(list)

    def __init__(self, driver, selected_key, button_elements):
        super().__init__()
        self.driver = driver
        self.selected_key = selected_key
        self.button_elements = button_elements.copy()

    def run(self):
        key_click_xpath = xpaths['key_button']
        if not SeleniumHelper.click_element(self.driver, key_click_xpath, log_func=self.log_updated.emit):
            pass

        button_clicked = False
        for button in self.button_elements:
            if self.selected_key == button.text:
                button.click()
                button_clicked = True
                break

        if not button_clicked:
            SeleniumHelper.click_element(self.driver, key_click_xpath, log_func=self.log_updated.emit)

        self.log_updated.emit(f"Selected key: {self.selected_key}")
        self.find_parts()

    def find_parts(self):
        parts_button_xpath = xpaths['parts_button']
        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error accessing parts menu.")
            return

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

        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error closing parts menu.")
            return

        self.instrument_parts_signal.emit(instrument_parts)


class DownloadAndProcessThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    log_updated = pyqtSignal(str)

    def __init__(self, driver, key_choice_text, selected_song_title, selected_song_artist,
                 paths, selected_instruments, download_horn_only=False, open_after_download=True):
        super().__init__()
        self.driver = driver
        self.key_choice_text = key_choice_text
        self.selected_song_title = selected_song_title
        self.selected_song_artist = selected_song_artist
        self.paths = paths
        self.download_horn_only = download_horn_only
        self.selected_instruments = selected_instruments
        self.instrument_parts = []
        self.full_paths = []
        self.images_by_instrument = defaultdict(list)
        self.open_after_download = open_after_download
        print(f"[DEBUG] DownloadAndProcessThread initialized for '{self.selected_song_title}'")

    def run(self):
        try:
            print("[DEBUG] Starting download and processing thread")
            song_dir, temp_dir = self.initialize_directories()
            print(f"[DEBUG] Directories initialized: {song_dir}, {temp_dir}")
            self.find_parts()
            print("[DEBUG] Parts found")
            self.download_images(temp_dir)
            print("[DEBUG] Images downloaded")
            self.remove_watermarks()
            print("[DEBUG] Watermarks removed")
            self.upscale_images()
            print("[DEBUG] Images upscaled")
            torch.cuda.empty_cache()
            self.create_pdfs(song_dir, temp_dir)
            print("[DEBUG] PDFs created")
            self.cleanup(temp_dir)
            print("[DEBUG] Temporary files cleaned")
            if self.open_after_download:
                print(f"[DEBUG] Opening directory {song_dir}")
                self.open_directory(song_dir)
            else:
                print(f"[DEBUG] Skipping opening directory {song_dir}")
        except Exception as e:
            self.log_updated.emit(f"Exception in run: {str(e)}")
            print(f"[DEBUG] Exception in run: {str(e)}")

    def initialize_directories(self):
        key_dir = self.key_choice_text
        title_dir = re.sub(r'[<>:"\\|?* ]', '_', self.selected_song_title.replace("/", "-"))
        artist_dir = re.sub(r'[<>:"\\|?* ]', '_', self.selected_song_artist.replace("/", "-"))
        main_dir = self.paths['download_dir']
        song_dir = os.path.join(main_dir, title_dir, artist_dir, key_dir)
        with file_lock:
            os.makedirs(song_dir, exist_ok=True)
        temp_dir = os.path.join(main_dir, title_dir, artist_dir, self.paths['temp_sub_dir'])
        with file_lock:
            os.makedirs(temp_dir, exist_ok=True)
        print(f"[DEBUG] Created song directory {song_dir}")
        print(f"[DEBUG] Created temp directory {temp_dir}")
        return song_dir, temp_dir

    def find_parts(self):
        parts_button_xpath = xpaths['parts_button']
        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error accessing parts menu.")
            return

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

        if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
            self.log_updated.emit("Error closing parts menu.")
            return

    def download_images(self, temp_dir):
        print("[DEBUG] Downloading images")
        self.images_by_instrument = defaultdict(list)
        downloaded_urls = set()
        try:
            image_xpath = xpaths['image_element']
            next_button_xpath = xpaths['next_button']
            parts_button_xpath = xpaths['parts_button']
            parts_list_xpath = xpaths['parts_list']
            page_number_pattern = re.compile(r'_(\d{3})\.png$')

            instruments_to_process = []
            if self.download_horn_only:
                horn_instrument = None
                for part in self.instrument_parts:
                    if 'french horn' in part.lower():
                        horn_instrument = part
                        instruments_to_process.append(part)
                        break
                if not horn_instrument:
                    self.log_updated.emit("No instrument with 'French Horn' found.")
            elif self.selected_instruments:
                instruments_to_process = self.selected_instruments
            else:
                instruments_to_process = self.instrument_parts

            for instrument in instruments_to_process:
                if not SeleniumHelper.click_element(self.driver, parts_button_xpath, log_func=self.log_updated.emit):
                    self.log_updated.emit('Error clicking "Parts" button')
                    continue

                instrument_list_elements = SeleniumHelper.find_elements(self.driver, parts_list_xpath, log_func=self.log_updated.emit)
                if not instrument_list_elements:
                    self.log_updated.emit("Error finding instrument list elements.")
                    continue

                instrument_clicked = False
                for button in instrument_list_elements:
                    button_text = button.text.strip()
                    normalized_instrument = instrument.lower().replace(',', '').replace('-', ' ').strip()
                    normalized_button_text = button_text.lower().replace(',', '').replace('-', ' ').strip()
                    if normalized_instrument == normalized_button_text:
                        try:
                            button.click()
                            instrument_clicked = True
                            break
                        except Exception:
                            continue

                if not instrument_clicked:
                    self.log_updated.emit(f"Could not find instrument: {instrument} in the dropdown list.")
                    continue

                previous_page_number = None
                while True:
                    image_element = SeleniumHelper.find_element(self.driver, image_xpath, log_func=self.log_updated.emit)
                    if not image_element:
                        break

                    image_url = image_element.get_attribute('src')
                    if image_url in downloaded_urls:
                        if not self.click_next_button(next_button_xpath):
                            break
                        continue

                    match = page_number_pattern.search(image_url)
                    if match:
                        current_page_number = match.group(1)
                    else:
                        break

                    if previous_page_number and current_page_number == "001":
                        break

                    self.status.emit(f"Downloading {os.path.basename(image_url)}")
                    full_path = os.path.join(temp_dir, os.path.basename(image_url))
                    downloaded_urls.add(image_url)

                    try:
                        response = requests.get(image_url)
                        if response.status_code == 200:
                            with file_lock:
                                with open(full_path, 'wb') as f:
                                    f.write(response.content)
                            self.images_by_instrument[instrument].append(full_path)
                        if not self.click_next_button(next_button_xpath):
                            break
                    except Exception:
                        break

                    previous_page_number = current_page_number
        except Exception as e:
            self.log_updated.emit(f"Exception in download_images: {str(e)}")

    def click_next_button(self, next_button_xpath):
        return SeleniumHelper.click_element(self.driver, next_button_xpath, log_func=self.log_updated.emit)

    def remove_watermarks(self):
        print("[DEBUG] Removing watermarks")
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
                            processed_images += 1
                            progress_value = int((processed_images / total_images) * 100)
                            self.progress.emit(progress_value)
                        except Exception:
                            continue
        except Exception as e:
            self.log_updated.emit(f"Exception in remove_watermarks: {str(e)}")

    def upscale_images(self):
        print("[DEBUG] Upscaling images")
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
                            wm_output_upscaled = upsample(wm_output)
                            padding_size = 16
                            patch_height = 550
                            patch_width = 850
                            padding = (padding_size, padding_size, padding_size, padding_size)
                            wm_output_upscaled_padded = nn.functional.pad(wm_output_upscaled, padding, value=1.0)
                            us_output = torch.zeros_like(wm_output_upscaled).cpu()
                            for i in range(0, wm_output_upscaled.shape[-2], patch_height):
                                for j in range(0, wm_output_upscaled.shape[-1], patch_width):
                                    patch = wm_output_upscaled_padded[:, :, i:i + patch_height + padding_size * 2, j:j + patch_width + padding_size * 2].cpu()
                                    us_patch = us_model(patch.to(self.device))
                                    us_patch = us_patch[:, :, padding_size:-padding_size, padding_size:-padding_size]
                                    us_output[:, :, i:i + patch_height, j:j + patch_width] = us_patch.cpu()
                            self.us_outputs[instrument].append(us_output)
                            processed_images += 1
                            progress_value = int((processed_images / total_images) * 100)
                            self.progress.emit(progress_value)
                        except Exception:
                            continue
        except Exception as e:
            self.log_updated.emit(f"Exception in upscale_images: {str(e)}")

    def create_pdfs(self, song_dir, temp_dir):
        print("[DEBUG] Creating PDFs")
        try:
            img_width, img_height = 1700, 2200
            total_instruments = len(self.us_outputs)
            processed_instruments = 0
            for instrument, us_outputs in self.us_outputs.items():
                image_paths = self.images_by_instrument[instrument]
                first_image_path = image_paths[0]
                first_image_filename = os.path.basename(first_image_path)
                base_filename = re.sub(r'_\d{3}\.png$', '', first_image_filename)
                base_filename = os.path.splitext(base_filename)[0]
                pdf_filename = f"{base_filename}.pdf"
                pdf_path = os.path.join(song_dir, pdf_filename)
                with file_lock:
                    c = canvas.Canvas(pdf_path, pagesize=(img_width, img_height))
                self.status.emit(f"Creating {pdf_filename}")
                for idx, image_tensor in enumerate(us_outputs):
                    try:
                        image_pil = tensor_to_PIL(image_tensor.squeeze(0))
                        temp_image_name = f"temp_image_{base_filename}_{idx}.png"
                        temp_image_path = os.path.join(temp_dir, temp_image_name)
                        with file_lock:
                            image_pil.save(temp_image_path)
                            c.drawImage(temp_image_path, 0, 0, width=img_width, height=img_height)
                            c.showPage()
                            os.remove(temp_image_path)
                    except Exception:
                        continue
                with file_lock:
                    c.save()
                processed_instruments += 1
                progress_value = int((processed_instruments / total_instruments) * 100)
                self.progress.emit(progress_value)
        except Exception as e:
            self.log_updated.emit(f"Exception in create_pdfs: {str(e)}")

    def cleanup(self, temp_dir):
        print("[DEBUG] Cleaning up temporary files")
        try:
            for paths in self.images_by_instrument.values():
                for path in paths:
                    with file_lock:
                        os.remove(path)
            with file_lock:
                os.rmdir(temp_dir)
        except Exception as e:
            self.log_updated.emit(f"Exception in cleanup: {str(e)}")

    def open_directory(self, path):
        try:
            print(f"[DEBUG] Opening directory {path}")
            if not os.environ.get('DISPLAY') and platform.system() == 'Linux':
                return
            if platform.system() == "Windows":
                with file_lock:
                    subprocess.run(['explorer', path.replace('/', '\\')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif platform.system() == "Darwin":
                with file_lock:
                    subprocess.run(['open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif platform.system() == "Linux":
                with file_lock:
                    subprocess.run(['xdg-open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.log_updated.emit(f"Exception in open_directory: {str(e)}")
