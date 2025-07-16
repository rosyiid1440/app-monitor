# --- Tahap 1: Build Frontend React ---
    FROM node:20-alpine AS build-stage

    # Atur direktori kerja di dalam container
    WORKDIR /app
    
    # Salin file package.json dan package-lock.json
    COPY package*.json ./
    
    # Instal dependensi frontend
    RUN npm install
    
    # Salin semua sisa kode frontend
    COPY . .
    
    # Build aplikasi frontend untuk produksi
    RUN npm run build
    
    # --- Tahap 2: Setup Backend Python ---
    FROM python:3.11-slim
    
    # Atur direktori kerja
    WORKDIR /app
    
    # Instal dependensi sistem yang mungkin diperlukan
    RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
    
    # Salin file requirements dari proyek Anda
    COPY requirements.txt .
    
    # Instal dependensi Python
    RUN pip install --no-cache-dir -r requirements.txt
    
    # Salin file backend dan file bersama
    COPY main_web_teacher.py .
    COPY students.json .
    COPY /shared/ ./shared/
    
    # Salin hasil build frontend dari tahap sebelumnya ke direktori 'dist'
    COPY --from=build-stage /app/dist ./dist
    
    # Ekspos port yang digunakan oleh Uvicorn
    EXPOSE 8000
    
    # Perintah untuk menjalankan aplikasi saat container dimulai
    CMD ["uvicorn", "main_web_teacher:app", "--host", "0.0.0.0", "--port", "8000"]
