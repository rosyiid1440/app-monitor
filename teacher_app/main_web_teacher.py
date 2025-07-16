# teacher_app/main_web_teacher.py

import sys
import asyncio
import json
import configparser
import uvicorn
import base64
import os
import secrets
from wakeonlan import send_magic_packet
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from starlette.websockets import WebSocketState
from fastapi.staticfiles import StaticFiles

sys.path.append('../')
from shared.protocol import *

config = configparser.ConfigParser()
config.read('config.ini')
SERVER_WEB_PORT = 8000 
STUDENT_DATA_FILE = "students.json"
FRONTEND_BUILD_DIR = "dist"

# Ambil kredensial dari environment variables, dengan nilai default jika tidak ada
ADMIN_USER = os.environ.get("ADMIN_USER", "guru")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "rahasia")

app = FastAPI()
security = HTTPBasic()

def load_student_registry():
    if os.path.exists(STUDENT_DATA_FILE):
        with open(STUDENT_DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_student_registry(registry):
    with open(STUDENT_DATA_FILE, 'w') as f:
        json.dump(registry, f, indent=4)

class ConnectionManager:
    # ... (Kelas ConnectionManager tidak ada perubahan dari versi sebelumnya) ...
    def __init__(self):
        self.student_registry = load_student_registry()
        self.active_student_connections: dict[str, WebSocket] = {}
        self.teacher_websocket: WebSocket | None = None
        for mac, data in self.student_registry.items():
            data['online'] = False
            data['frozen'] = False
    async def connect_teacher(self, websocket: WebSocket):
        await websocket.accept()
        self.teacher_websocket = websocket
    def disconnect_teacher(self):
        self.teacher_websocket = None
    async def connect_student(self, websocket: WebSocket, mac_address: str, name: str):
        client_id = f"{websocket.client.host}:{websocket.client.port}"
        self.active_student_connections[client_id] = websocket
        self.student_registry[mac_address] = { "name": name, "mac": mac_address, "online": True, "frozen": False, "client_id": client_id }
        save_student_registry(self.student_registry)
        await self.send_to_student(json.dumps({"type": MSG_REQUEST_SCREEN_START}), client_id)
        await self.notify_teacher_ui_update()
        return client_id
    async def disconnect_student(self, client_id: str):
        mac_to_update = None
        for mac, data in self.student_registry.items():
            if data.get("client_id") == client_id:
                data['online'] = False
                data['frozen'] = False
                mac_to_update = mac
                break
        if mac_to_update: save_student_registry(self.student_registry)
        if client_id in self.active_student_connections: del self.active_student_connections[client_id]
        await self.notify_teacher_ui_update()
    async def send_to_student(self, message: str | bytes, client_id: str):
        if client_id in self.active_student_connections:
            websocket = self.active_student_connections[client_id]
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    if isinstance(message, str): await websocket.send_text(message)
                    else: await websocket.send_bytes(message)
                except (RuntimeError, WebSocketDisconnect): print(f"Gagal mengirim ke {client_id}, koneksi sudah ditutup.")
    async def send_to_teacher(self, message: dict | bytes):
        if self.teacher_websocket and self.teacher_websocket.client_state == WebSocketState.CONNECTED:
            try:
                if isinstance(message, dict): await self.teacher_websocket.send_json(message)
                elif isinstance(message, bytes): await self.teacher_websocket.send_bytes(message)
            except (RuntimeError, WebSocketDisconnect): print("Gagal mengirim ke UI Guru, koneksi sudah ditutup.")
    async def notify_teacher_ui_update(self):
        await self.send_to_teacher({"type": "student_list_update", "students": list(self.student_registry.values())})
    async def broadcast_to_online_students(self, message: str | bytes):
        for student in self.student_registry.values():
            if student.get("online"): await self.send_to_student(message, student["client_id"])

manager = ConnectionManager()

# <<< ENDPOINT LOGIN DIPERBARUI >>>
@app.post("/api/login")
async def login(credentials: HTTPBasicCredentials = Depends(security)):
    is_user_ok = secrets.compare_digest(credentials.username, ADMIN_USER)
    is_pass_ok = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (is_user_ok and is_pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Basic"},
        )
    # Jika berhasil, cukup kembalikan status sukses
    return JSONResponse(content={"success": True, "message": "Login berhasil"})

# <<< ENDPOINT WEBSOCKET DIPERBARUI >>>
@app.websocket("/ws/teacher")
async def websocket_teacher_endpoint(websocket: WebSocket):
    # Tidak ada lagi validasi token di sini, koneksi langsung diterima
    await manager.connect_teacher(websocket)
    print("UI Guru terhubung.")
    await manager.notify_teacher_ui_update()
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            mac_address = data.get("client_id") 
            
            student_info = manager.student_registry.get(mac_address, {})
            active_client_id = student_info.get("client_id") if student_info.get("online") else None

            if action == "forward_to_student" and active_client_id:
                await manager.send_to_student(json.dumps(data.get("message", {})), active_client_id)
            
            elif action == "forward_binary_to_student" and active_client_id:
                binary_payload = base64.b64decode(data.get("payload", ""))
                await manager.send_to_student(binary_payload, active_client_id)
            
            elif action in ["power_shutdown", "power_restart", "power_ps_shutdown"] and active_client_id:
                cmd_type = {"power_shutdown": MSG_POWER_SHUTDOWN, "power_restart": MSG_POWER_RESTART, "power_ps_shutdown": MSG_POWER_PS_SHUTDOWN}.get(action)
                await manager.send_to_student(json.dumps({"type": cmd_type}), active_client_id)
            
            elif action == "power_wake" and mac_address:
                try: send_magic_packet(mac_address)
                except Exception as e: print(f"Gagal mengirim WoL ke {mac_address}: {e}")

            elif action in ["freeze_client", "unfreeze_client"] and active_client_id:
                is_freezing = action == "freeze_client"
                cmd_type = MSG_FREEZE_CLIENT if is_freezing else MSG_UNFREEZE_CLIENT
                await manager.send_to_student(json.dumps({"type": cmd_type}), active_client_id)
                if mac_address in manager.student_registry:
                    manager.student_registry[mac_address]['frozen'] = is_freezing
                    await manager.notify_teacher_ui_update()

            elif action == "batch_upload_start":
                await manager.broadcast_to_online_students(json.dumps(data.get("message", {})))
            
            elif action == "batch_upload_chunk":
                binary_payload = base64.b64decode(data.get("payload", ""))
                await manager.broadcast_to_online_students(binary_payload)

            elif action == "batch_upload_end":
                await manager.broadcast_to_online_students(json.dumps(data.get("message", {})))

            elif action == "batch_execute":
                await manager.broadcast_to_online_students(json.dumps(data.get("message", {})))

            elif action == "power_wake_all":
                for mac in manager.student_registry.keys():
                    try:
                        send_magic_packet(mac)
                        await asyncio.sleep(0.01)
                    except Exception as e: print(f"Gagal mengirim WoL ke {mac}: {e}")
            
            elif action in ["power_restart_all", "power_shutdown_all"]:
                cmd_type = MSG_POWER_RESTART if action == "power_restart_all" else MSG_POWER_SHUTDOWN
                await manager.broadcast_to_online_students(json.dumps({"type": cmd_type}))

    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.disconnect_teacher()
        print("UI Guru terputus.")

@app.websocket("/ws/student")
async def websocket_student_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = None
    mac_address = None
    try:
        message = await websocket.receive_json()
        if message.get("type") == MSG_IDENTIFY:
            payload = message.get("payload", {})
            mac = payload.get("mac")
            mac_address = mac
            name = payload.get("name")
            if not mac: raise WebSocketDisconnect(code=1008, reason="MAC address is required")
            client_id = await manager.connect_student(websocket, mac, name)
            print(f"Siswa {name} ({mac}) terhubung dengan client_id {client_id}")
        else:
            raise WebSocketDisconnect(code=1008, reason="Identification message required")

        while True:
            message = await websocket.receive()
            if "text" in message:
                data = json.loads(message["text"])
                await manager.send_to_teacher(data)
            elif "bytes" in message:
                binary_message = message["bytes"]
                try:
                    header_len = int.from_bytes(binary_message[:4], 'big')
                    metadata = json.loads(binary_message[4:4+header_len])
                    image_data = binary_message[4+header_len:]
                    metadata['mac'] = mac_address 
                    new_metadata_json = json.dumps(metadata).encode('utf-8')
                    new_header_len = len(new_metadata_json).to_bytes(4, 'big')
                    message_to_teacher = new_header_len + new_metadata_json + image_data
                    await manager.send_to_teacher(message_to_teacher)
                except Exception:
                    await manager.send_to_teacher(binary_message)

    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if client_id:
            await manager.disconnect_student(client_id)
            print(f"Siswa dengan client_id {client_id} terputus.")

if os.path.exists(FRONTEND_BUILD_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_BUILD_DIR, html=True), name="static")

if __name__ == "__main__":
    if not os.path.exists(FRONTEND_BUILD_DIR):
        print("="*50)
        print("PERINGATAN: Direktori 'dist' tidak ditemukan.")
        print("Backend akan berjalan, tetapi frontend tidak akan bisa diakses.")
        print("Untuk membuat frontend, jalankan perintah berikut di terminal terpisah:")
        print("cd teacher_app")
        print("npm install")
        print("npm run build")
        print("="*50)
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=SERVER_WEB_PORT, 
        ws_ping_interval=20, 
        ws_ping_timeout=20
    )
