import os
import re
import shutil
import threading
from datetime import datetime

from PyQt5.QtCore import QEventLoop, QObject
from PyQt5.QtWidgets import QInputDialog, QMessageBox, QDialog

from transposition_utils import get_transposition_suggestions
from pdf_selection_dialog import PdfSelectionDialog

# Lock to synchronize file system operations
fs_lock = threading.Lock()


class BatchProcessor(QObject):
    """Handle batch processing of song downloads."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    def _run_thread_and_wait(self, thread):
        print(f"[DEBUG] Starting thread {thread.__class__.__name__}")
        loop = QEventLoop()
        thread.finished.connect(loop.quit)
        thread.start()
        loop.exec_()
        print(f"[DEBUG] Thread {thread.__class__.__name__} finished")

    def _process_song(self, title, instrument, key, dest_root):
        app = self.app
        print(f"[DEBUG] Processing song '{title}' instrument '{instrument}' key '{key}'")
        app.append_log(f"Processing '{title}' - {instrument} in {key}")

        # Search for the song
        print("[DEBUG] Searching for song")
        app.song_search_box.setText(title)
        app.find_songs()
        self._run_thread_and_wait(app.find_songs_thread)

        options = [info["text"] for info in app.song_info[:5]]
        print(f"[DEBUG] Found {len(options)} options")
        if not options:
            app.append_log(f"No results for {title}")
            return True

        title_dir = re.sub(r'[<>:"\\|?* ]', "_", title.replace("/", "-"))
        dest_dir = os.path.join(dest_root, title_dir)
        with fs_lock:
            os.makedirs(dest_dir, exist_ok=True)

        pdf_paths = []
        labels = []
        for idx, item in enumerate(options):
            print(f"[DEBUG] Option {idx}: {item}")
            app.song_choice_box.setCurrentIndex(idx)
            app.select_song()
            self._run_thread_and_wait(app.select_song_thread)

            available_keys = [
                app.key_choice_box.itemText(i)
                for i in range(app.key_choice_box.count())
            ]
            if not available_keys:
                print(
                    f"[DEBUG] No orchestration found for option {idx}. Skipping."
                )
                continue
            chosen_key = key
            if key not in available_keys:
                print(f"[DEBUG] Requested key '{key}' not in available keys {available_keys}")
                msg = f"Requested key '{key}' not found. Choose from available keys:\n{', '.join(available_keys)}"
                suggestions = get_transposition_suggestions(
                    available_keys, instrument, key
                )
                if suggestions["direct"] or suggestions["closest"]:
                    msg += "\n\nSuggestions:\n"
                    for s in suggestions["direct"]:
                        msg += f"- {s['instrument']} in {s['key']} (direct)\n"
                    for s in suggestions["closest"][:3]:
                        msg += f"- {s['instrument']} in {s['key']} ({s['interval']} {s['interval_direction']})\n"
                chosen_key, ok = QInputDialog.getItem(
                    app, "Select Key", msg, available_keys, 0, False
                )
                if not ok:
                    continue

            print(f"[DEBUG] Using key '{chosen_key}'")
            app.key_choice_box.setCurrentText(chosen_key)
            app.select_key()
            self._run_thread_and_wait(app.select_key_thread)

            if instrument not in app.instrument_parts:
                print(f"[DEBUG] Instrument '{instrument}' not found in parts {app.instrument_parts}")
                instrument, ok = QInputDialog.getItem(
                    app,
                    "Select Instrument",
                    f"Instrument '{instrument}' not found. Choose one:",
                    app.instrument_parts,
                    0,
                    False,
                )
                if not ok:
                    continue
            app.selected_instruments = [instrument]

            app.download_and_process_images(open_after_download=False)
            self._run_thread_and_wait(app.download_and_process_images_thread)

            key_dir = chosen_key
            selected_song_text = app.song_choice_box.currentText()
            parts = selected_song_text.split("\n")
            selected_song_artist = parts[1] if len(parts) > 1 else "Unknown Artist"
            artist_dir = re.sub(r'[<>:"\\|?* ]', "_", selected_song_artist.replace("/", "-"))
            song_dir = os.path.join(
                app.paths["download_dir"], title_dir, artist_dir, key_dir
            )
            with fs_lock:
                if os.path.isdir(song_dir):
                    for fname in os.listdir(song_dir):
                        if fname.endswith(".pdf"):
                            dest_pdf = os.path.join(dest_dir, f"{idx}_{fname}")
                            print(f"[DEBUG] Moving {fname} to {dest_pdf}")
                            shutil.move(os.path.join(song_dir, fname), dest_pdf)
                            pdf_paths.append(dest_pdf)
                            labels.append(item)

            with fs_lock:
                shutil.rmtree(
                    os.path.join(app.paths["download_dir"], title_dir), ignore_errors=True
                )

        if pdf_paths:
            dialog = PdfSelectionDialog(pdf_paths, labels, app)
            if dialog.exec_() == QDialog.Accepted:
                chosen = dialog.selected_path()
            else:
                chosen = None
            with fs_lock:
                for path in pdf_paths:
                    if path != chosen:
                        os.remove(path)
            return chosen is not None

        return True

    def process_batch(self, entries):
        """Process a sequence of songs."""
        batch_dir = os.path.join(
            self.app.paths["download_dir"],
            "Batch_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        with fs_lock:
            os.makedirs(batch_dir, exist_ok=True)
        print(f"[DEBUG] Batch directory: {batch_dir}")

        for title, instrument, key in entries:
            print(f"[DEBUG] Starting song '{title}'")
            keep = self._process_song(title, instrument, key, batch_dir)
            print(f"[DEBUG] Finished song '{title}'")
            if not keep:
                break

        QMessageBox.information(
            self.app, "Batch Complete", "Finished processing song list."
        )
        print("[DEBUG] Batch processing complete")
