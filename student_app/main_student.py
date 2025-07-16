# student_app/main_student.py

import sys
import asyncio
import json
import configparser
import websockets
import socket
import mss
import zlib
import pyautogui
import os
import string
import subprocess
import shutil
import ctypes
from getmac import get_mac_address
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit, QLineEdit, QPushButton, QMessageBox, QWidget, QLabel
from PyQt5.QtGui import QFont

# PERBAIKAN: Baris 'sys.path.append('../')' dihapus dari sini.
# Import di bawah ini sekarang akan berfungsi dengan benar karena 'shared' adalah subdirektori.
from shared.protocol import *

config = configparser.ConfigParser()
# PyInstaller akan menempatkan config.ini di direktori yang sama dengan .exe
# Jadi kita tidak perlu path folder 'app/' lagi.
config.read('config.ini')
HOST = config['server']['host'] 
SERVER_PORT = 8000 

def block_input(block: bool):
    """Fungsi untuk memblokir atau membuka blokir input mouse dan keyboard (khusus Windows)."""
    try:
        ctypes.windll.user32.BlockInput(block)
    except Exception as e:
        print(f"Gagal mengubah status blokir input (mungkin bukan Windows): {e}")

class InputBlockerThread(QThread):
    """Thread untuk terus-menerus memindahkan kursor ke tengah layar untuk memperkuat blokir input."""
    def __init__(self):
        super().__init__()
        self.is_running = False
        self.screen_width, self.screen_height = pyautogui.size()
        self.center_x, self.center_y = self.screen_width // 2, self.screen_height // 2

    def run(self):
        self.is_running = True
        pyautogui.FAILSAFE = False
        while self.is_running:
            pyautogui.moveTo(self.center_x, self.center_y, duration=0)
            self.msleep(10) # Cukup sering untuk mencegah input lolos
        pyautogui.FAILSAFE = True

    def stop(self):
        self.is_running = False


class FreezeWindow(QWidget):
    """Jendela overlay transparan untuk menutupi seluruh layar saat dibekukan."""
    def __init__(self):
        super().__init__()
        # Atur window agar tanpa bingkai, selalu di atas, dan transparan
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 150);") # Hitam semi-transparan
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        self.message_label = QLabel("KOMPUTER INI TELAH DIBEKUKAN OLEH GURU")
        font = QFont("Arial", 32, QFont.Bold)
        self.message_label.setFont(font)
        self.message_label.setStyleSheet("color: white; background-color: transparent;")
        layout.addWidget(self.message_label)

    def showEvent(self, event):
        # Pastikan jendela menutupi seluruh layar saat ditampilkan
        desktop = QApplication.desktop()
        self.setGeometry(desktop.geometry())
        super().showEvent(event)

    # Abaikan semua event input untuk mencegah interaksi
    def keyPressEvent(self, event): event.ignore()
    def mousePressEvent(self, event): event.ignore()
    def mouseMoveEvent(self, event): event.ignore()
    def mouseReleaseEvent(self, event): event.ignore()

class ChatWindow(QDialog):
    """Jendela obrolan antara siswa dan guru."""
    message_sent = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Obrolan dengan Guru")
        self.setFixedSize(400, 500)
        
        layout = QVBoxLayout(self)
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_input = QLineEdit()
        self.send_button = QPushButton("Kirim")
        
        layout.addWidget(self.chat_display)
        layout.addWidget(self.chat_input)
        layout.addWidget(self.send_button)
        
        self.send_button.clicked.connect(self.send_message)
        self.chat_input.returnPressed.connect(self.send_message)

    def send_message(self):
        """Mengirim pesan ketika tombol diklik atau Enter ditekan."""
        text = self.chat_input.text().strip()
        if text:
            self.message_sent.emit(text)
            self.append_message("Saya", text)
            self.chat_input.clear()

    def append_message(self, sender, text):
        """Menambahkan pesan ke tampilan obrolan."""
        self.chat_display.append(f"<b>{sender}:</b> {text}")

    def closeEvent(self, event):
        """Mencegah jendela ditutup, hanya disembunyikan."""
        event.ignore()
        self.hide()

class ScreenCaptureThread(QThread):
    """Thread untuk menangkap dan mengirim gambar layar secara terus-menerus."""
    def __init__(self, websocket, loop, client_id):
        super().__init__()
        self.websocket = websocket
        self.loop = loop
        self.client_id = client_id
        self.is_running = False

    def run(self):
        self.is_running = True
        with mss.mss() as sct:
            monitor = sct.monitors[1] # Monitor utama
            while self.is_running:
                try:
                    sct_img = sct.grab(monitor)
                    # Kompresi gambar untuk mengurangi ukuran data
                    img_bytes = zlib.compress(sct_img.rgb, level=6)
                    
                    metadata = {"type": MSG_SCREEN_DATA, "width": sct_img.width, "height": sct_img.height}
                    json_meta = json.dumps(metadata).encode('utf-8')
                    json_len = len(json_meta).to_bytes(4, 'big')
                    
                    message = json_len + json_meta + img_bytes
                    # Kirim data ke server secara asynchronous
                    asyncio.run_coroutine_threadsafe(self.websocket.send(message), self.loop)
                    self.msleep(100) # Delay untuk mengurangi beban CPU
                except Exception as e:
                    print(f"Error di screen capture: {e}")
                    self.is_running = False

    def stop(self):
        self.is_running = False

class ClientThread(QThread):
    """Thread utama yang menangani koneksi WebSocket dan logika klien."""
    show_chat_signal = pyqtSignal(str)
    show_alert_signal = pyqtSignal(str, str)
    freeze_signal = pyqtSignal()
    unfreeze_signal = pyqtSignal()

    def __init__(self, chat_window, freeze_window):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.screen_capture_thread = None
        self.client_id = None
        self.websocket = None
        self.chat_window = chat_window
        self.freeze_window = freeze_window
        self.input_blocker_thread = InputBlockerThread()
        self.current_upload_file = None
        self.current_upload_file_path = None
        
        # Hubungkan sinyal ke slot (handler)
        self.show_chat_signal.connect(self.handle_show_chat)
        self.show_alert_signal.connect(self.handle_show_alert)
        self.chat_window.message_sent.connect(self.handle_send_chat)
        self.freeze_signal.connect(self.handle_freeze)
        self.unfreeze_signal.connect(self.handle_unfreeze)

    def handle_show_alert(self, title, text):
        QMessageBox.information(None, title, text)

    def handle_show_chat(self, text):
        self.chat_window.append_message("Guru", text)
        self.chat_window.show()
        self.chat_window.activateWindow()

    def handle_send_chat(self, text):
        if self.websocket:
            msg = {"type": MSG_CHAT_TO_TEACHER, "payload": {"text": text}}
            asyncio.run_coroutine_threadsafe(self.websocket.send(json.dumps(msg)), self.loop)

    def handle_freeze(self):
        self.freeze_window.show()
        block_input(True)
        if not self.input_blocker_thread.isRunning():
            self.input_blocker_thread.start()

    def handle_unfreeze(self):
        if self.input_blocker_thread.isRunning():
            self.input_blocker_thread.stop()
        block_input(False)
        self.freeze_window.hide()

    async def connect_and_listen(self):
        """Fungsi utama untuk terhubung ke server dan mendengarkan pesan."""
        uri = f"ws://{HOST}:{SERVER_PORT}/ws/student"
        while True:
            try:
                # Menambahkan ping_interval untuk menjaga koneksi tetap hidup
                async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as websocket:
                    self.websocket = websocket
                    self.client_id = f"{websocket.local_address[0]}:{websocket.local_address[1]}"
                    print("Terhubung ke server guru.")
                    
                    mac_address = get_mac_address()
                    # Kirim pesan identifikasi saat pertama kali terhubung
                    await websocket.send(json.dumps({
                        "type": MSG_IDENTIFY,
                        "payload": {
                            "name": socket.gethostname(),
                            "mac": mac_address
                        }
                    }))

                    async for message in websocket:
                        if isinstance(message, str):
                            data = json.loads(message)
                            msg_type = data.get("type")
                            
                            # Jika layar dibekukan, abaikan semua pesan kecuali unfreeze
                            if self.freeze_window.isVisible() and msg_type != MSG_UNFREEZE_CLIENT:
                                continue
                            
                            payload = data.get("payload", {})
                            
                            if msg_type == MSG_FREEZE_CLIENT:
                                print("Menerima perintah freeze!")
                                self.freeze_signal.emit()
                            
                            elif msg_type == MSG_UNFREEZE_CLIENT:
                                print("Menerima perintah unfreeze!")
                                self.unfreeze_signal.emit()

                            elif msg_type == MSG_CHAT_TO_STUDENT:
                                self.show_chat_signal.emit(payload.get('text', ''))
                            
                            elif msg_type == MSG_REQUEST_SCREEN_START:
                                if not self.screen_capture_thread or not self.screen_capture_thread.isRunning():
                                    self.screen_capture_thread = ScreenCaptureThread(websocket, self.loop, self.client_id)
                                    self.screen_capture_thread.start()

                            elif msg_type == MSG_REQUEST_SCREEN_STOP:
                                if self.screen_capture_thread:
                                    self.screen_capture_thread.stop()
                                    self.screen_capture_thread = None
                            
                            elif msg_type == MSG_REMOTE_MOUSE:
                                pyautogui.click(x=payload.get('x'), y=payload.get('y'), button=payload.get('button'))

                            elif msg_type == MSG_REMOTE_KEYBOARD:
                                pyautogui.write(payload.get('key', ''))

                            elif msg_type == MSG_REQUEST_FILE_LIST:
                                path = payload.get('path')
                                try:
                                    items = []
                                    if path == '/':
                                        # List semua drive yang tersedia (C:, D:, dll.)
                                        available_drives = [f'{d}:/' for d in string.ascii_uppercase if os.path.exists(f'{d}:')]
                                        for drive in available_drives:
                                            items.append({"name": f"Drive Lokal ({drive[:2]})", "type": "folder", "path": drive})
                                        response = {"type": MSG_FILE_LIST_RESPONSE, "path": "/", "items": items}
                                    else:
                                        for item_name in os.listdir(path):
                                            item_path = os.path.join(path, item_name)
                                            if os.path.isdir(item_path):
                                                items.append({"name": item_name, "type": "folder", "path": item_path.replace('\\', '/')})
                                            else:
                                                items.append({"name": item_name, "type": "file", "path": item_path.replace('\\', '/')})
                                        response = {"type": MSG_FILE_LIST_RESPONSE, "path": path, "items": items}
                                    await websocket.send(json.dumps(response))
                                except Exception as e:
                                    response = {"type": MSG_FILE_LIST_RESPONSE, "path": path, "items": [], "error": str(e)}
                                    await websocket.send(json.dumps(response))

                            elif msg_type == MSG_REQUEST_FILE_DOWNLOAD:
                                path = payload.get('path')
                                try:
                                    with open(path, 'rb') as f:
                                        while True:
                                            chunk = f.read(1024 * 64) # Baca per 64KB
                                            if not chunk: break
                                            header = json.dumps({"type": MSG_FILE_DOWNLOAD_CHUNK}).encode('utf-8')
                                            header_len = len(header).to_bytes(4, 'big')
                                            await websocket.send(header_len + header + chunk)
                                    await websocket.send(json.dumps({"type": MSG_FILE_DOWNLOAD_END}))
                                except Exception as e:
                                    print(f"Gagal mengunduh file {path}: {e}")
                            
                            elif msg_type == MSG_POWER_SHUTDOWN:
                                print("Menerima perintah shutdown!")
                                os.system("shutdown /s /t 1")
                            
                            elif msg_type == MSG_POWER_RESTART:
                                print("Menerima perintah restart!")
                                os.system("shutdown /r /t 1")

                            elif msg_type == MSG_POWER_PS_SHUTDOWN:
                                print("Menerima perintah shutdown paksa (PowerShell)!")
                                os.system("powershell.exe -Command \"Stop-Computer -Force\"")

                            elif msg_type == MSG_FILE_UPLOAD_START:
                                filename = payload.get("filename", "file_baru.dat")
                                raw_dest_path = payload.get("destination_path", "%USERPROFILE%\\Desktop")
                                dest_path = os.path.expandvars(raw_dest_path)
                                
                                if not os.path.exists(dest_path):
                                    os.makedirs(dest_path, exist_ok=True)

                                self.current_upload_file_path = os.path.join(dest_path, filename)
                                self.current_upload_file = open(self.current_upload_file_path, "wb")
                                print(f"Mulai menerima file: {filename} di {self.current_upload_file_path}")

                            elif msg_type == MSG_FILE_UPLOAD_END:
                                if self.current_upload_file:
                                    self.current_upload_file.close()
                                    self.current_upload_file = None
                                    print(f"Selesai menerima file: {payload.get('filename')}")
                            
                            elif msg_type == MSG_FILE_UPLOAD_END_AND_EXTRACT:
                                if self.current_upload_file:
                                    filename = payload.get('filename')
                                    self.current_upload_file.close()
                                    self.current_upload_file = None
                                    print(f"Selesai menerima file zip: {filename}")

                                    if self.current_upload_file_path and self.current_upload_file_path.lower().endswith('.zip'):
                                        try:
                                            extract_path = os.path.dirname(self.current_upload_file_path)
                                            shutil.unpack_archive(self.current_upload_file_path, extract_path)
                                            os.remove(self.current_upload_file_path)
                                            print(f"File {filename} berhasil diekstrak ke {extract_path}")
                                        except Exception as e:
                                            print(f"Gagal mengekstrak file: {e}")

                            elif msg_type == MSG_BATCH_EXECUTE:
                                raw_path_to_execute = payload.get("path")
                                if raw_path_to_execute:
                                    path_to_execute = os.path.expandvars(raw_path_to_execute)
                                    if os.path.exists(path_to_execute):
                                        print(f"Menerima perintah eksekusi untuk: {path_to_execute}")
                                        try:
                                            subprocess.Popen([path_to_execute])
                                        except Exception as e:
                                            print(f"Gagal mengeksekusi file: {e}")
                        
                        elif isinstance(message, bytes):
                            # Menangani chunk file yang diterima
                            if self.current_upload_file:
                                try:
                                    header_len = int.from_bytes(message[:4], 'big')
                                    header_json = json.loads(message[4:4+header_len])
                                    if header_json.get("type") == MSG_FILE_UPLOAD_CHUNK:
                                        file_chunk = message[4+header_len:]
                                        self.current_upload_file.write(file_chunk)
                                except Exception as e:
                                    print(f"Gagal memproses chunk file: {e}")

            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError):
                print(f"Koneksi terputus. Mencoba lagi dalam 5 detik...")
                if self.screen_capture_thread: self.screen_capture_thread.stop()
                self.unfreeze_signal.emit() # Pastikan unfreeze jika koneksi putus
                await asyncio.sleep(5)
            except Exception as e:
                print(f"Error: {e}")
                self.unfreeze_signal.emit()
                await asyncio.sleep(5)

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.connect_and_listen())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    chat_win = ChatWindow()
    freeze_win = FreezeWindow()
    client_thread = ClientThread(chat_win, freeze_win)
    client_thread.start()
    print("Aplikasi siswa berjalan di latar belakang.")
    # exec_() diperlukan agar aplikasi Qt tetap berjalan dan bisa menampilkan jendela
    sys.exit(app.exec_())
