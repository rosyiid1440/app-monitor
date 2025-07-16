import { useState, useEffect, useRef, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import { useToast } from '@/hooks/use-toast';
import pako from 'pako';
import { 
  Power, 
  RotateCcw, 
  PowerOff, 
  FolderOpen, 
  Snowflake, 
  Upload, 
  Play, 
  Download,
  ArrowLeft,
  Wifi,
  WifiOff,
  Monitor,
  Terminal,
  Unplug,
  Expand
} from 'lucide-react';

// Interfaces to match Python backend data
interface Student {
  mac: string;
  name: string;
  online: boolean;
  frozen?: boolean;
  client_id?: string; // ip:port, only when online
}

interface FileItem {
  name: string;
  path: string;
  type: 'file' | 'folder';
}

// Helper function to send commands via WebSocket
const sendCommand = (ws: WebSocket | null, command: object) => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(command));
  } else {
    console.error("WebSocket is not connected.");
  }
};

export default function TeacherDashboard() {
  const [students, setStudents] = useState<Student[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected' | 'connecting'>('connecting');
  const [fileManagerOpen, setFileManagerOpen] = useState(false);
  const [batchUploadOpen, setBatchUploadOpen] = useState(false);
  const [batchExecuteOpen, setBatchExecuteOpen] = useState(false);
  const [currentPath, setCurrentPath] = useState('/');
  const [fileList, setFileList] = useState<FileItem[]>([]);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [fileManagerStudent, setFileManagerStudent] = useState<{mac: string, name: string} | null>(null);

  const { toast } = useToast();
  const canvasRefs = useRef<{ [key: string]: HTMLCanvasElement | null }>({});
  const ws = useRef<WebSocket | null>(null);
  const fileChunks = useRef<Blob[]>([]);
  const expectedFile = useRef<string | null>(null);

  const connect = useCallback(() => {
    const wsUrl = `ws://${window.location.hostname}:8000/ws/teacher`;
    ws.current = new WebSocket(wsUrl);
    ws.current.binaryType = 'blob';

    ws.current.onopen = () => {
      console.log("Connected to teacher websocket.");
      setConnectionStatus('connected');
    };

    ws.current.onmessage = (event) => {
      if (event.data instanceof Blob) {
        parseBinaryMessage(event.data);
      } else {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case 'student_list_update':
            setStudents(data.students);
            break;
          case 'file_list_response':
            setCurrentPath(data.path);
            setFileList(data.items);
            break;
          case 'file_download_end':
            handleFileEnd();
            break;
        }
      }
    };

    ws.current.onclose = () => {
      console.log("Teacher websocket disconnected. Reconnecting...");
      setConnectionStatus('disconnected');
      setTimeout(connect, 3000);
    };

    ws.current.onerror = (error) => {
      console.error("WebSocket error:", error);
      ws.current?.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      ws.current?.close();
    };
  }, [connect]);


  const parseBinaryMessage = async (blob: Blob) => {
    try {
        const buffer = await blob.arrayBuffer();
        const headerView = new DataView(buffer.slice(0, 4));
        const jsonLen = headerView.getUint32(0);
        const jsonText = new TextDecoder().decode(buffer.slice(4, 4 + jsonLen));
        const metadata = JSON.parse(jsonText);
        const payload = buffer.slice(4 + jsonLen);

        if (metadata.type === 'screen_data' && metadata.mac) {
            updateScreenCanvas(metadata.mac, metadata, payload);
        } else if (metadata.type === 'file_download_chunk') {
            handleFileChunk(new Blob([payload]));
        }
    } catch (e) {
        // console.error("Failed to parse binary message:", e);
    }
  };

  const updateScreenCanvas = (mac: string, metadata: any, payload: ArrayBuffer) => {
    const canvas = canvasRefs.current[mac];
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    try {
        const decompressedRgbData = pako.inflate(new Uint8Array(payload));
        canvas.width = metadata.width;
        canvas.height = metadata.height;
        const imageData = ctx.createImageData(metadata.width, metadata.height);
        let j = 0;
        for (let i = 0; i < decompressedRgbData.length; i += 3) {
            imageData.data[j] = decompressedRgbData[i];     // R
            imageData.data[j + 1] = decompressedRgbData[i + 1]; // G
            imageData.data[j + 2] = decompressedRgbData[i + 2]; // B
            imageData.data[j + 3] = 255;                      // A
            j += 4;
        }
        ctx.putImageData(imageData, 0, 0);
    } catch (e) {
        // console.error(`Failed to update screen for ${mac}:`, e);
    }
  };

  const handlePowerAction = (mac: string, action: string) => {
    const actionNames: { [key: string]: string } = {
      'power_wake': 'menghidupkan',
      'power_restart': 'restart',
      'power_shutdown': 'mematikan',
      'power_ps_shutdown': 'shutdown paksa'
    };
    if (confirm(`Apakah Anda yakin ingin ${actionNames[action]} komputer siswa ini?`)) {
        sendCommand(ws.current, { action, client_id: mac });
        toast({ title: "Perintah Terkirim", description: `Perintah ${actionNames[action]} telah dikirim.` });
    }
  };

  const handleBatchAction = (action: string) => {
    const actionNames: { [key: string]: string } = {
      'power_wake_all': 'menghidupkan semua',
      'power_restart_all': 'restart semua',
      'power_shutdown_all': 'mematikan semua',
    };
    if (confirm(`Apakah Anda yakin ingin ${actionNames[action]} siswa?`)) {
        sendCommand(ws.current, { action });
        toast({ title: "Perintah Massal Terkirim", description: `Perintah ${actionNames[action]} telah dikirim.` });
    }
  };

  const toggleFreeze = (mac: string, currentFrozen?: boolean) => {
    const action = currentFrozen ? 'unfreeze_client' : 'freeze_client';
    sendCommand(ws.current, { action, client_id: mac });
    toast({ title: currentFrozen ? "Siswa Dibebaskan" : "Siswa Dibekukan" });
  };

  const openFileManager = (student: Student) => {
    setFileManagerStudent(student);
    setFileManagerOpen(true);
    sendCommand(ws.current, { action: 'forward_to_student', client_id: student.mac, message: { type: 'request_file_list', payload: { path: '/' } } });
  };

  const requestFileList = (clientId: string, path: string) => {
    if (!clientId) return;
    sendCommand(ws.current, {
        action: 'forward_to_student',
        client_id: clientId,
        message: { type: 'request_file_list', payload: { path: path } }
    });
  }

  const requestFileDownload = (clientId: string, path: string, filename: string) => {
    toast({ title: `Meminta unduhan untuk: ${filename}` });
    expectedFile.current = filename;
    fileChunks.current = [];
    sendCommand(ws.current, {
        action: 'forward_to_student',
        client_id: clientId,
        message: { type: 'request_file_download', payload: { path: path } }
    });
  }

  const handleFileChunk = (payloadBlob: Blob) => {
      fileChunks.current.push(payloadBlob);
  }

  const handleFileEnd = () => {
      if (fileChunks.current.length > 0 && expectedFile.current) {
          const fileBlob = new Blob(fileChunks.current);
          const link = document.createElement('a');
          link.href = URL.createObjectURL(fileBlob);
          link.download = expectedFile.current;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          toast({ title: "Unduhan Selesai", description: `${expectedFile.current} telah berhasil diunduh.` });
      }
      fileChunks.current = [];
      expectedFile.current = null;
  }

  const blobToBase64 = (blob: Blob): Promise<string> => {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve((reader.result as string).split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
  }

  const handleFileUpload = async (file: File) => {
    if (!fileManagerStudent) return;
    const destPath = currentPath;
    if (destPath === '/') {
        toast({ variant: 'destructive', title: 'Error', description: 'Silakan pilih drive atau folder tujuan terlebih dahulu.' });
        return;
    }
    toast({ title: `Mengunggah ${file.name} ke ${destPath}...` });
    
    const CHUNK_SIZE = 64 * 1024;
    
    sendCommand(ws.current, {
        action: 'forward_to_student',
        client_id: fileManagerStudent.mac,
        message: { type: 'file_upload_start', payload: { filename: file.name, destination_path: destPath } }
    });
    await new Promise(resolve => setTimeout(resolve, 100));

    for (let offset = 0; offset < file.size; offset += CHUNK_SIZE) {
        const chunk = file.slice(offset, offset + CHUNK_SIZE);
        const header = { type: 'file_upload_chunk' };
        const headerJson = JSON.stringify(header);
        const headerBytes = new TextEncoder().encode(headerJson);
        const headerLen = new DataView(new ArrayBuffer(4));
        headerLen.setUint32(0, headerBytes.byteLength);
        const messageBlob = new Blob([headerLen.buffer, headerBytes, chunk]);
        
        sendCommand(ws.current, {
            action: 'forward_binary_to_student',
            client_id: fileManagerStudent.mac,
            payload: await blobToBase64(messageBlob)
        });
        await new Promise(resolve => setTimeout(resolve, 5));
    }

    sendCommand(ws.current, {
        action: 'forward_to_student',
        client_id: fileManagerStudent.mac,
        message: { type: 'file_upload_end', payload: { filename: file.name } }
    });
    
    toast({ title: "Unggah Selesai", description: `${file.name} telah dikirim.` });
  };

  const handleBatchUpload = async (file: File, destPath: string, extract: boolean) => {
    toast({ title: `Memulai unggah massal untuk file: ${file.name}` });
    setIsUploading(true);
    setUploadProgress(0);

    const CHUNK_SIZE = 64 * 1024;
    
    sendCommand(ws.current, {
        action: 'batch_upload_start',
        message: { type: 'file_upload_start', payload: { filename: file.name, destination_path: destPath } }
    });
    await new Promise(resolve => setTimeout(resolve, 100));

    for (let offset = 0; offset < file.size; offset += CHUNK_SIZE) {
        const chunk = file.slice(offset, offset + CHUNK_SIZE);
        const header = { type: 'file_upload_chunk' };
        const headerJson = JSON.stringify(header);
        const headerBytes = new TextEncoder().encode(headerJson);
        const headerLen = new DataView(new ArrayBuffer(4));
        headerLen.setUint32(0, headerBytes.byteLength);
        const messageBlob = new Blob([headerLen.buffer, headerBytes, chunk]);
        
        sendCommand(ws.current, {
            action: 'batch_upload_chunk',
            payload: await blobToBase64(messageBlob)
        });
        
        const progress = Math.round(((offset + chunk.size) / file.size) * 100);
        setUploadProgress(progress);
        await new Promise(resolve => setTimeout(resolve, 5));
    }

    const endMessageType = extract ? 'file_upload_end_and_extract' : 'file_upload_end';

    sendCommand(ws.current, {
        action: 'batch_upload_end',
        message: { type: endMessageType, payload: { filename: file.name } }
    });
    
    toast({ title: "Proses Selesai", description: `Unggah massal untuk ${file.name} telah selesai dikirim.` });
    setIsUploading(false);
    setBatchUploadOpen(false);
  }

  const handleBatchExecute = (executePath: string) => {
      if (confirm(`Apakah Anda yakin ingin menjalankan "${executePath}" di SEMUA siswa online?`)) {
          sendCommand(ws.current, {
              action: 'batch_execute',
              message: { type: 'batch_execute', payload: { path: executePath } }
          });
          toast({ title: "Perintah Terkirim", description: `Perintah eksekusi untuk ${executePath} telah dikirim.` });
          setBatchExecuteOpen(false);
      }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-surface">
      <header className="glass sticky top-0 z-50 border-b border-glass-border">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Monitor className="h-8 w-8 text-primary" />
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent">
                  Dasbor Guru
                </h1>
                <p className="text-sm text-muted-foreground">Pemantauan Siswa Real-time</p>
              </div>
            </div>
            
            <div className="flex items-center space-x-3">
              <div className="flex items-center space-x-2 px-4 py-2 bg-surface rounded-xl border">
                <span className="text-sm font-medium text-muted-foreground">Aksi Massal:</span>
                <Button size="sm" variant="ghost" className="h-8 w-8 p-0 hover:bg-success/10 hover:text-success" onClick={() => handleBatchAction('power_wake_all')}><Power className="h-4 w-4" /></Button>
                <Button size="sm" variant="ghost" className="h-8 w-8 p-0 hover:bg-warning/10 hover:text-warning" onClick={() => handleBatchAction('power_restart_all')}><RotateCcw className="h-4 w-4" /></Button>
                <Button size="sm" variant="ghost" className="h-8 w-8 p-0 hover:bg-destructive/10 hover:text-destructive" onClick={() => handleBatchAction('power_shutdown_all')}><PowerOff className="h-4 w-4" /></Button>
                <Button size="sm" variant="ghost" className="h-8 w-8 p-0 hover:bg-primary/10 hover:text-primary" onClick={() => setBatchUploadOpen(true)}><Upload className="h-4 w-4" /></Button>
                <Button size="sm" variant="ghost" className="h-8 w-8 p-0 hover:bg-primary/10 hover:text-primary" onClick={() => setBatchExecuteOpen(true)}><Play className="h-4 w-4" /></Button>
              </div>
              
              <div className="flex items-center space-x-2 px-3 py-2 bg-surface rounded-xl border">
                {connectionStatus === 'connected' ? (
                  <><div className="w-2 h-2 bg-success rounded-full animate-pulse" /><Wifi className="h-4 w-4 text-success" /><span className="text-sm font-medium text-success">Terhubung</span></>
                ) : (
                  <><div className="w-2 h-2 bg-destructive rounded-full" /><WifiOff className="h-4 w-4 text-destructive" /><span className="text-sm font-medium text-destructive">Terputus</span></>
                )}
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-6 py-8">
        {students.length === 0 ? (
          <div className="text-center py-20">
            <Monitor className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-xl font-medium text-muted-foreground mb-2">Belum ada siswa terhubung</h3>
            <p className="text-muted-foreground">Siswa akan muncul di sini ketika mereka terhubung ke sistem.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-6">
            {students.map((student) => (
              <StudentCard
                key={student.mac}
                student={student}
                onPowerAction={handlePowerAction}
                onToggleFreeze={toggleFreeze}
                onOpenFileManager={openFileManager}
                canvasRef={(el) => (canvasRefs.current[student.mac] = el)}
              />
            ))}
          </div>
        )}
      </main>

      <Dialog open={fileManagerOpen} onOpenChange={setFileManagerOpen}>
        <DialogContent className="max-w-4xl max-h-[80vh] flex flex-col">
          <DialogHeader><DialogTitle className="flex items-center space-x-2"><FolderOpen className="h-5 w-5" /><span>Penjelajah File - {fileManagerStudent?.name}</span></DialogTitle></DialogHeader>
          <div className="flex-1 flex flex-col space-y-4"><div className="flex items-center space-x-2 p-3 bg-surface rounded-lg"><Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => { const parentPath = currentPath.substring(0, currentPath.lastIndexOf('/')) || '/'; requestFileList(fileManagerStudent!.mac, parentPath); }}><ArrowLeft className="h-4 w-4" /></Button><span className="flex-1 font-mono text-sm bg-background px-3 py-1 rounded border">{currentPath}</span><Button size="sm" variant="default" onClick={() => document.getElementById('modal-file-upload-input')?.click()}><Upload className="h-4 w-4 mr-2" />Upload</Button><input type="file" id="modal-file-upload-input" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; if (file) handleFileUpload(file); }} /></div><div className="flex-1 border rounded-lg p-4 bg-surface min-h-[300px] overflow-y-auto"><div className="space-y-2">{fileList.map((item, index) => (<div key={index} className="flex items-center space-x-3 p-2 hover:bg-background rounded-lg cursor-pointer transition-colors" onClick={() => { if (item.type === 'folder') requestFileList(fileManagerStudent!.mac, item.path); }}>{item.type === 'folder' ? (<FolderOpen className="h-5 w-5 text-warning" />) : (<div className="h-5 w-5 bg-muted rounded border" />)}<span className="flex-1">{item.name}</span>{item.type === 'file' && (<Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={(e) => { e.stopPropagation(); requestFileDownload(fileManagerStudent!.mac, item.path, item.name); }}><Download className="h-4 w-4" /></Button>)}</div>))}</div></div></div>
        </DialogContent>
      </Dialog>

      <Dialog open={batchUploadOpen} onOpenChange={setBatchUploadOpen}>
        <DialogContent className="max-w-md"><DialogHeader><DialogTitle>Upload File Massal</DialogTitle></DialogHeader><div className="space-y-4"><p className="text-sm text-muted-foreground">Fitur ini akan mengunggah file ke semua siswa yang sedang online.</p><div className="space-y-2"><Label htmlFor="batch-file">Pilih File</Label><Input id="batch-file" type="file" className="cursor-pointer"/></div><div className="space-y-2"><Label htmlFor="dest-path">Path Tujuan</Label><Input id="dest-path" defaultValue="%USERPROFILE%\Desktop" /></div><div className="flex items-center space-x-2"><Checkbox id="extract-zip" /><Label htmlFor="extract-zip" className="text-sm">Ekstrak file .zip secara otomatis</Label></div>{isUploading && (<div className="space-y-2"><div className="flex justify-between text-sm"><span>Mengunggah...</span><span>{uploadProgress}%</span></div><Progress value={uploadProgress} /></div>)}<Button className="w-full" disabled={isUploading} onClick={() => { const file = (document.getElementById('batch-file') as HTMLInputElement).files?.[0]; const destPath = (document.getElementById('dest-path') as HTMLInputElement).value; const extract = (document.getElementById('extract-zip') as HTMLInputElement).checked; if (file && destPath) handleBatchUpload(file, destPath, extract); }}>{isUploading ? 'Mengunggah...' : 'Mulai Upload Massal'}</Button></div></DialogContent>
      </Dialog>

      <Dialog open={batchExecuteOpen} onOpenChange={setBatchExecuteOpen}>
        <DialogContent className="max-w-md"><DialogHeader><DialogTitle>Eksekusi Perintah Massal</DialogTitle></DialogHeader><div className="space-y-4"><p className="text-sm text-muted-foreground">Fitur ini akan menjalankan file di semua komputer siswa yang online.</p><div className="space-y-2"><Label htmlFor="execute-path">Path Lengkap File</Label><Input id="execute-path" placeholder="Contoh: C:\Temp\ExamBrowser.exe"/></div><Button className="w-full" onClick={() => { const path = (document.getElementById('execute-path') as HTMLInputElement).value; if(path) handleBatchExecute(path); }}>Jalankan di Semua Siswa</Button></div></DialogContent>
      </Dialog>
    </div>
  );
}

interface StudentCardProps {
  student: Student;
  onPowerAction: (mac: string, action: string) => void;
  onToggleFreeze: (mac: string, frozen?: boolean) => void;
  onOpenFileManager: (student: Student) => void;
  canvasRef: (el: HTMLCanvasElement | null) => void;
}

function StudentCard({ student, onPowerAction, onToggleFreeze, onOpenFileManager, canvasRef }: StudentCardProps) {
  const handleFullscreen = () => {
    const cardElement = document.getElementById(`student-container-${student.mac}`);
    if (cardElement && student.online) {
        if (cardElement.requestFullscreen) {
            cardElement.requestFullscreen();
        }
    }
  };

  return (
    <Card id={`student-container-${student.mac}`} className={`overflow-hidden transition-all duration-300 ease-out group ${student.online ? 'card-hover shadow-soft hover:shadow-strong border-border' : 'opacity-60 border-border/50'}`}>
      <div className="aspect-video bg-surface-elevated relative cursor-pointer overflow-hidden" onClick={handleFullscreen}>
        {student.online ? (
          <canvas ref={canvasRef} className="w-full h-full object-contain" />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-muted"><Monitor className="h-12 w-12 text-muted-foreground" /></div>
        )}
        {student.online && (
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors duration-200 flex items-center justify-center">
            <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200"><Badge variant="secondary" className="bg-background/90 backdrop-blur-sm">Klik untuk fullscreen</Badge></div>
          </div>
        )}
      </div>
      <div className="p-4 space-y-3">
        <div className="flex items-center space-x-2">
          <div className={`w-2 h-2 rounded-full ${student.online ? 'bg-success' : 'bg-destructive'}`} />
          <span className="font-medium text-sm truncate flex-1">{student.name}</span>
          {student.frozen && (<Snowflake className="h-4 w-4 text-primary" />)}
        </div>
        <div className="flex items-center justify-between">
          {student.online ? (
            <>
              <Button size="sm" variant="ghost" className={`h-8 w-8 p-0 ${student.frozen ? 'text-primary hover:bg-primary/10' : 'hover:bg-primary/10 hover:text-primary'}`} onClick={() => onToggleFreeze(student.mac, student.frozen)}><Snowflake className="h-4 w-4" /></Button>
              <Button size="sm" variant="ghost" className="h-8 w-8 p-0 hover:bg-warning/10 hover:text-warning" onClick={() => onOpenFileManager(student)}><FolderOpen className="h-4 w-4" /></Button>
              <Button size="sm" variant="ghost" className="h-8 w-8 p-0 hover:bg-warning/10 hover:text-warning" onClick={() => onPowerAction(student.mac, 'power_restart')}><RotateCcw className="h-4 w-4" /></Button>
              <Button size="sm" variant="ghost" className="h-8 w-8 p-0 hover:bg-destructive/10 hover:text-destructive" onClick={() => onPowerAction(student.mac, 'power_shutdown')}><PowerOff className="h-4 w-4" /></Button>
              <Button size="sm" variant="ghost" className="h-8 w-8 p-0 hover:bg-destructive/10 hover:text-destructive" onClick={() => onPowerAction(student.mac, 'power_ps_shutdown')}><Terminal className="h-4 w-4" /></Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" className="h-8 w-8 p-0 hover:bg-success/10 hover:text-success mx-auto" onClick={() => onPowerAction(student.mac, 'power_wake')}><Unplug className="h-4 w-4" /></Button>
          )}
        </div>
      </div>
    </Card>
  );
}
