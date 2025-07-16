# shared/protocol.py

# --- Pesan Identifikasi & Obrolan ---
MSG_IDENTIFY = "identify"
MSG_CHAT_TO_TEACHER = "chat_to_teacher"
MSG_CHAT_TO_STUDENT = "chat_to_student"

# --- Pesan Remote Screen ---
MSG_REQUEST_SCREEN_START = "request_screen_start"
MSG_REQUEST_SCREEN_STOP = "request_screen_stop"
MSG_SCREEN_DATA = "screen_data"
MSG_REMOTE_MOUSE = "remote_mouse"
MSG_REMOTE_KEYBOARD = "remote_keyboard"

# --- Pesan File Explorer ---
MSG_REQUEST_FILE_LIST = "request_file_list"
MSG_FILE_LIST_RESPONSE = "file_list_response"
MSG_REQUEST_FILE_DOWNLOAD = "request_file_download"
MSG_FILE_DOWNLOAD_CHUNK = "file_download_chunk"
MSG_FILE_DOWNLOAD_END = "file_download_end"
MSG_FILE_UPLOAD_START = "file_upload_start"
MSG_FILE_UPLOAD_CHUNK = "file_upload_chunk"
MSG_FILE_UPLOAD_END = "file_upload_end"
MSG_FILE_UPLOAD_END_AND_EXTRACT = "file_upload_end_and_extract"

# --- Pesan Manajemen Daya ---
MSG_POWER_SHUTDOWN = "power_shutdown"
MSG_POWER_RESTART = "power_restart"
MSG_POWER_PS_SHUTDOWN = "power_ps_shutdown"

# --- Pesan Aksi Massal ---
MSG_BATCH_EXECUTE = "batch_execute"

# --- Pesan Freeze/Unfreeze ---
MSG_FREEZE_CLIENT = "freeze_client"
MSG_UNFREEZE_CLIENT = "unfreeze_client"
