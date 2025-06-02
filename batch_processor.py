import os
import re
import shutil
from datetime import datetime

from PyQt5.QtCore import QEventLoop, QObject
from PyQt5.QtWidgets import QInputDialog, QMessageBox


class BatchProcessor(QObject):
    """Handle batch processing of song downloads."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    def _run_thread_and_wait(self, thread):
        loop = QEventLoop()
        thread.finished.connect(loop.quit)
        thread.start()
        loop.exec_()

    def _process_song(self, title, instrument, key, dest_root):
        app = self.app
        app.append_log(f"Processing '{title}' - {instrument} in {key}")

        # Search for the song
        app.song_search_box.setText(title)
        app.find_songs()
        self._run_thread_and_wait(app.find_songs_thread)

        options = [info['text'] for info in app.song_info[:5]]
        if not options:
            app.append_log(f"No results for {title}")
            return True

        item, ok = QInputDialog.getItem(app, "Select Song", f"Select version for {title}", options, 0, False)
        if not ok:
            return False
        index = options.index(item)
        app.song_choice_box.setCurrentIndex(index)
        app.select_song()
        self._run_thread_and_wait(app.select_song_thread)

        available_keys = [app.key_choice_box.itemText(i) for i in range(app.key_choice_box.count())]
        if key not in available_keys:
            msg = f"Requested key '{key}' not found. Choose from available keys:\n{', '.join(available_keys)}"
            key, ok = QInputDialog.getItem(app, "Select Key", msg, available_keys, 0, False)
            if not ok:
                return False

        app.key_choice_box.setCurrentText(key)
        app.select_key()
        self._run_thread_and_wait(app.select_key_thread)

        if instrument not in app.instrument_parts:
            instrument, ok = QInputDialog.getItem(
                app,
                "Select Instrument",
                f"Instrument '{instrument}' not found. Choose one:",
                app.instrument_parts,
                0,
                False,
            )
            if not ok:
                return False
        app.selected_instruments = [instrument]

        app.download_and_process_images()
        self._run_thread_and_wait(app.download_and_process_images_thread)

        key_dir = key
        title_dir = re.sub(r'[<>:"\\|?* ]', '_', title.replace('/', '-'))
        artist_dir = re.sub(r'[<>:"\\|?* ]', '_', 'artist')
        song_dir = os.path.join(app.paths['download_dir'], title_dir, artist_dir, key_dir)
        dest_dir = os.path.join(dest_root, title_dir)
        os.makedirs(dest_dir, exist_ok=True)
        for fname in os.listdir(song_dir):
            if fname.endswith('.pdf'):
                shutil.move(os.path.join(song_dir, fname), os.path.join(dest_dir, fname))

        shutil.rmtree(os.path.join(app.paths['download_dir'], title_dir), ignore_errors=True)
        return True

    def process_batch(self, entries):
        """Process a sequence of songs."""
        batch_dir = os.path.join(
            self.app.paths['download_dir'],
            'Batch_' + datetime.now().strftime('%Y%m%d_%H%M%S'),
        )
        os.makedirs(batch_dir, exist_ok=True)

        for title, instrument, key in entries:
            keep = self._process_song(title, instrument, key, batch_dir)
            if not keep:
                break

        QMessageBox.information(self.app, "Batch Complete", "Finished processing song list.")

