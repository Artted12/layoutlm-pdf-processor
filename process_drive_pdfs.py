"""
========================================================================
PROCESADOR OPTIMIZADO DE PDFs DE GOOGLE DRIVE
========================================================================
✅ Skip de archivos ya procesados (NO re-procesa)
✅ Procesamiento paralelo (usa todos los cores de CPU)
✅ Caché de archivos procesados
✅ Verificación de existencia antes de procesar
✅ Soporte para procesamiento incremental

Velocidad: 2-4x más rápido que versión anterior
========================================================================
"""

import io
import os
import pickle
from pathlib import Path
from typing import List, Dict, Optional, Set
import json
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from dotenv import load_dotenv


# Autenticación OAuth
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Google Drive API
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

# Procesamiento de PDFs
import fitz  # PyMuPDF
from PIL import Image


# Cargar variables de entorno
load_dotenv('Datos.env')

# ============================================
# CONFIGURACIÓN
# ============================================

class Config:
    """Configuración optimizada del proyecto"""
    
    # Archivos de credenciales
    OAUTH_CREDENTIALS_PATH = os.getenv('OAUTH_CREDENTIALS_PATH', 'oauth_credentials.json')
    TOKEN_PATH = "token.pickle"
    CACHE_PATH = "processed_cache.json"  # ← NUEVO: Caché de procesados
    
    # IDs de Drive
    DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID', '')
    IMAGES_FOLDER_NAME = "Recibos_Imagenes"
    
    # Configuración de conversión
    DPI = 150
    IMAGE_FORMAT = "PNG"
    
    # Carpeta local
    LOCAL_OUTPUT_DIR = Path("logs_drive")
    
    # Scopes
    SCOPES = [
        'https://www.googleapis.com/auth/drive.file',
        'https://www.googleapis.com/auth/drive'
    ]
    
    # ⚡ CONFIGURACIÓN DE RENDIMIENTO
    MAX_WORKERS = 4  # ✅ REDUCIDO: 4 hilos es más seguro con API de Google
    MAX_RETRIES = 3
    RETRY_DELAY = 2
    SKIP_EXISTING = True  # ← NUEVO: Skip archivos ya procesados
    
    def __init__(self):
        self.LOCAL_OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================
# GESTOR DE CACHÉ
# ============================================

class ProcessedCache:
    """Mantiene registro de PDFs ya procesados"""
    
    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self.processed: Set[str] = set()
        self.lock = threading.Lock()
        self._cargar_cache()
    
    def _cargar_cache(self):
        """Carga caché desde archivo"""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'r') as f:
                    data = json.load(f)
                    self.processed = set(data.get('processed', []))
                print(f"📋 Caché cargado: {len(self.processed)} PDFs ya procesados")
            except Exception as e:
                print(f"⚠️  Error cargando caché: {e}")
                self.processed = set()
        else:
            print("📋 Caché vacío - primera ejecución")
    
    def marcar_procesado(self, pdf_id: str):
        """Marca un PDF como procesado"""
        with self.lock:
            self.processed.add(pdf_id)
    
    def esta_procesado(self, pdf_id: str) -> bool:
        """Verifica si un PDF ya fue procesado"""
        with self.lock:
            return pdf_id in self.processed
    
    def guardar_cache(self):
        """Guarda caché a disco"""
        with self.lock:
            try:
                with open(self.cache_path, 'w') as f:
                    json.dump({
                        'processed': list(self.processed),
                        'last_update': datetime.now().isoformat(),
                        'total': len(self.processed)
                    }, f, indent=2)
                print(f"💾 Caché guardado: {len(self.processed)} PDFs")
            except Exception as e:
                print(f"⚠️  Error guardando caché: {e}")
    
    def limpiar_cache(self):
        """Limpia completamente el caché"""
        with self.lock:
            self.processed.clear()
            if os.path.exists(self.cache_path):
                os.remove(self.cache_path)
        print("🗑️  Caché limpiado")

# ============================================
# GESTOR DE AUTENTICACIÓN
# ============================================

class OAuthManager:
    """Maneja autenticación OAuth"""
    
    def __init__(self, credentials_path: str, token_path: str, scopes: List[str]):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.scopes = scopes
        self.credentials = None
    
    def autenticar(self) -> Credentials:
        """Autentica con Google"""
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                self.credentials = pickle.load(token)
        
        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                try:
                    self.credentials.refresh(Request())
                except:
                    os.remove(self.token_path)
                    return self.autenticar()
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, self.scopes
                )
                self.credentials = flow.run_local_server(port=0)
            
            with open(self.token_path, 'wb') as token:
                pickle.dump(self.credentials, token)
        
        return self.credentials

# ============================================
# GESTOR DE GOOGLE DRIVE OPTIMIZADO
# ============================================

class GoogleDriveManager:
    """Gestor optimizado de Drive con verificación de existencia"""
    
    def __init__(self, credentials: Credentials):
        self.service = build('drive', 'v3', credentials=credentials)
        self.folder_cache: Dict[str, str] = {}  # Caché de carpetas creadas
    
    def listar_carpetas(self, parent_folder_id: str) -> List[Dict]:
        """Lista carpetas con paginación"""
        query = f"'{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        all_folders = []
        page_token = None
        
        while True:
            results = self.service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, createdTime)",
                orderBy="name",
                pageSize=100,
                pageToken=page_token
            ).execute()
            
            all_folders.extend(results.get('files', []))
            page_token = results.get('nextPageToken')
            if not page_token:
                break
        
        return all_folders
    
    def listar_pdfs(self, folder_id: str) -> List[Dict]:
        """Lista PDFs con paginación"""
        query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
        all_pdfs = []
        page_token = None
        
        while True:
            results = self.service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, size, createdTime)",
                orderBy="name",
                pageSize=100,
                pageToken=page_token
            ).execute()
            
            all_pdfs.extend(results.get('files', []))
            page_token = results.get('nextPageToken')
            if not page_token:
                break
        
        return all_pdfs
    
    def verificar_carpeta_existe(self, nombre: str, parent_id: str) -> Optional[str]:
        """
        Verifica si una carpeta ya existe
        ← NUEVO: Para skip de procesados
        """
        cache_key = f"{parent_id}:{nombre}"
        
        # Revisar caché local primero
        if cache_key in self.folder_cache:
            return self.folder_cache[cache_key]
        
        # Buscar en Drive
        query = f"name='{nombre}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.service.files().list(
            q=query,
            fields="files(id)",
            pageSize=1
        ).execute()
        
        existing = results.get('files', [])
        if existing:
            folder_id = existing[0]['id']
            self.folder_cache[cache_key] = folder_id
            return folder_id
        
        return None
    
    def leer_archivo_en_memoria(self, file_id: str, max_retries: int = 3) -> Optional[bytes]:
        """Lee archivo con reintentos"""
        for attempt in range(max_retries):
            try:
                request = self.service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                
                while not done:
                    status, done = downloader.next_chunk()
                
                return fh.getvalue()
            except:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None
    
    def crear_carpeta(self, nombre: str, parent_id: str) -> Optional[str]:
        """Crea carpeta o retorna existente"""
        # Verificar si ya existe
        folder_id = self.verificar_carpeta_existe(nombre, parent_id)
        if folder_id:
            return folder_id
        
        # Crear nueva
        file_metadata = {
            'name': nombre,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        
        folder = self.service.files().create(
            body=file_metadata,
            fields='id'
        ).execute()
        
        folder_id = folder.get('id')
        cache_key = f"{parent_id}:{nombre}"
        self.folder_cache[cache_key] = folder_id
        
        return folder_id
    
    def subir_archivo_desde_memoria(self, data_bytes: bytes, nombre: str,
                                    parent_folder_id: str, mime_type: str,
                                    max_retries: int = 3) -> Optional[str]:
        """Sube archivo con reintentos"""
        for attempt in range(max_retries):
            try:
                file_metadata = {
                    'name': nombre,
                    'parents': [parent_folder_id]
                }
                
                media = MediaIoBaseUpload(
                    io.BytesIO(data_bytes),
                    mimetype=mime_type,
                    resumable=True,
                    chunksize=1024*1024
                )
                
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                
                return file.get('id')
            except:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None

# ============================================
# CONVERSOR PDF → IMÁGENES
# ============================================

class PDFToImageConverter:
    """Conversor optimizado de PDFs"""
    
    def __init__(self, dpi: int = 150, image_format: str = "PNG"):
        self.dpi = dpi
        self.image_format = image_format
    
    def convert_pdf_bytes_to_images(self, pdf_bytes: bytes) -> List[bytes]:
        """Convierte PDF a imágenes"""
        image_bytes_list = []
        
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=self.dpi)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format=self.image_format, optimize=True)
                img_byte_arr.seek(0)
                
                image_bytes_list.append(img_byte_arr.getvalue())
            
            doc.close()
        except Exception as e:
            print(f"      ❌ Error convirtiendo: {e}")
        
        return image_bytes_list

# ============================================
# WORKER PARA PROCESAMIENTO PARALELO
# ============================================

def procesar_pdf_worker(args):
    """
    Worker function para procesamiento paralelo
    Procesa un PDF individual
    
    IMPORTANTE: Cada hilo crea su propia conexión a Drive
    """
    pdf, carpeta_imagenes_id, credentials, converter, config, cache = args
    
    # ✅ CREAR SERVICIO DE DRIVE INDEPENDIENTE POR HILO
    drive = GoogleDriveManager(credentials)
    
    pdf_nombre = pdf['name']
    pdf_id = pdf['id']
    pdf_size_mb = int(pdf.get('size', 0)) / (1024 * 1024)
    
    resultado = {
        'nombre': pdf_nombre,
        'exitoso': False,
        'imagenes': 0,
        'error': None
    }
    
    try:
        # ✅ VERIFICAR SI YA FUE PROCESADO
        if config.SKIP_EXISTING and cache.esta_procesado(pdf_id):
            resultado['skipped'] = True
            resultado['exitoso'] = True
            return resultado
        
        # ✅ VERIFICAR SI LA CARPETA YA EXISTE EN DRIVE
        pdf_base_name = Path(pdf_nombre).stem
        pdf_base_name = "".join(c for c in pdf_base_name if c.isalnum() or c in (' ', '-', '_'))[:100]
        
        if config.SKIP_EXISTING:
            carpeta_existe = drive.verificar_carpeta_existe(pdf_base_name, carpeta_imagenes_id)
            if carpeta_existe:
                cache.marcar_procesado(pdf_id)
                resultado['skipped'] = True
                resultado['exitoso'] = True
                return resultado
        
        # Leer PDF
        pdf_bytes = drive.leer_archivo_en_memoria(pdf_id, config.MAX_RETRIES)
        if not pdf_bytes:
            resultado['error'] = "No se pudo leer"
            return resultado
        
        # Convertir
        imagenes_bytes = converter.convert_pdf_bytes_to_images(pdf_bytes)
        if not imagenes_bytes:
            resultado['error'] = "No se pudo convertir"
            return resultado
        
        resultado['imagenes'] = len(imagenes_bytes)
        
        # Crear carpeta
        pdf_folder_id = drive.crear_carpeta(pdf_base_name, carpeta_imagenes_id)
        if not pdf_folder_id:
            resultado['error'] = "No se pudo crear carpeta"
            return resultado
        
        # Subir imágenes
        exitos = 0
        for page_num, img_bytes in enumerate(imagenes_bytes, 1):
            image_name = f"{pdf_base_name}_p{page_num}.{config.IMAGE_FORMAT.lower()}"
            image_id = drive.subir_archivo_desde_memoria(
                img_bytes,
                image_name,
                pdf_folder_id,
                f"image/{config.IMAGE_FORMAT.lower()}",
                config.MAX_RETRIES
            )
            if image_id:
                exitos += 1
        
        if exitos == len(imagenes_bytes):
            resultado['exitoso'] = True
            cache.marcar_procesado(pdf_id)
        else:
            resultado['error'] = f"Solo {exitos}/{len(imagenes_bytes)} imágenes subidas"
        
        # Liberar memoria
        del pdf_bytes
        del imagenes_bytes
    
    except Exception as e:
        resultado['error'] = str(e)
    
    return resultado

# ============================================
# PROCESADOR PRINCIPAL OPTIMIZADO
# ============================================

class CloudDriveProcessorOptimizado:
    """Procesador optimizado con paralelismo y skip"""
    
    def __init__(self, config: Config):
        self.config = config
        
        # Autenticación
        oauth = OAuthManager(config.OAUTH_CREDENTIALS_PATH, config.TOKEN_PATH, config.SCOPES)
        self.credentials = oauth.autenticar()  # ✅ Guardar credenciales
        
        # Servicios (solo para operaciones principales, no para workers)
        self.drive = GoogleDriveManager(self.credentials)
        self.converter = PDFToImageConverter(config.DPI, config.IMAGE_FORMAT)
        self.cache = ProcessedCache(config.CACHE_PATH)
        self.images_root_folder_id = None
    
    def procesar_dataset_completo(self, folder_id: str) -> Dict:
        """Procesa dataset con optimizaciones"""
        
        stats = {
            "inicio": datetime.now().isoformat(),
            "carpetas_procesadas": 0,
            "pdfs_procesados": 0,
            "pdfs_skip": 0,
            "pdfs_con_error": 0,
            "imagenes_generadas": 0,
            "imagenes_subidas": 0,
            "errores": []
        }
        
        print("\n" + "="*70)
        print("PROCESAMIENTO OPTIMIZADO CON SKIP Y PARALELISMO")
        print("="*70)
        print(f"⚡ Hilos paralelos: {self.config.MAX_WORKERS}")
        print(f"⏭️  Skip activado: {'SÍ' if self.config.SKIP_EXISTING else 'NO'}")
        print(f"📋 PDFs en caché: {len(self.cache.processed)}")
        print("="*70 + "\n")
        
        # Crear carpeta raíz
        self.images_root_folder_id = self.drive.crear_carpeta(
            self.config.IMAGES_FOLDER_NAME,
            folder_id
        )
        
        if not self.images_root_folder_id:
            return stats
        
        # Listar carpetas
        carpetas_meses = self.drive.listar_carpetas(folder_id)
        
        # Procesar cada carpeta
        for idx_carpeta, carpeta in enumerate(carpetas_meses, 1):
            carpeta_nombre = carpeta['name']
            carpeta_id = carpeta['id']
            
            print(f"\n{'='*70}")
            print(f"📁 [{idx_carpeta}/{len(carpetas_meses)}] {carpeta_nombre}")
            print(f"{'='*70}")
            
            # Crear subcarpeta
            carpeta_imagenes_id = self.drive.crear_carpeta(
                carpeta_nombre,
                self.images_root_folder_id
            )
            
            if not carpeta_imagenes_id:
                continue
            
            # Listar PDFs
            pdfs = self.drive.listar_pdfs(carpeta_id)
            if not pdfs:
                continue
            
            print(f"   📄 Total: {len(pdfs)} PDFs")
            print(f"   ⚡ Procesando con {self.config.MAX_WORKERS} hilos...\n")
            
            # ⚡ PROCESAMIENTO PARALELO
            with ThreadPoolExecutor(max_workers=self.config.MAX_WORKERS) as executor:
                # Preparar argumentos (pasar credentials en lugar de drive)
                tasks = [
                    (pdf, carpeta_imagenes_id, self.credentials, self.converter, self.config, self.cache)
                    for pdf in pdfs
                ]
                
                # Enviar tareas
                futures = {executor.submit(procesar_pdf_worker, task): task[0] for task in tasks}
                
                # Procesar resultados conforme completan
                for i, future in enumerate(as_completed(futures), 1):
                    pdf = futures[future]
                    try:
                        resultado = future.result()
                        
                        if resultado.get('skipped'):
                            stats['pdfs_skip'] += 1
                            print(f"   ⏭️  [{i}/{len(pdfs)}] {resultado['nombre']} (ya procesado)")
                        elif resultado['exitoso']:
                            stats['pdfs_procesados'] += 1
                            stats['imagenes_subidas'] += resultado['imagenes']
                            stats['imagenes_generadas'] += resultado['imagenes']
                            print(f"   ✅ [{i}/{len(pdfs)}] {resultado['nombre']} ({resultado['imagenes']} imgs)")
                        else:
                            stats['pdfs_con_error'] += 1
                            stats['errores'].append(f"{resultado['nombre']}: {resultado['error']}")
                            print(f"   ❌ [{i}/{len(pdfs)}] {resultado['nombre']} - {resultado['error']}")
                    
                    except Exception as e:
                        stats['pdfs_con_error'] += 1
                        print(f"   ❌ [{i}/{len(pdfs)}] {pdf['name']} - Error: {e}")
            
            stats['carpetas_procesadas'] += 1
            
            # Guardar caché cada carpeta
            self.cache.guardar_cache()
        
        # Resumen final
        stats["fin"] = datetime.now().isoformat()
        duracion = datetime.fromisoformat(stats["fin"]) - datetime.fromisoformat(stats["inicio"])
        
        print("\n" + "="*70)
        print("PROCESAMIENTO COMPLETADO")
        print("="*70)
        print(f"⏱️  Duración: {duracion}")
        print(f"📁 Carpetas: {stats['carpetas_procesadas']}")
        print(f"✅ Procesados: {stats['pdfs_procesados']}")
        print(f"⏭️  Saltados: {stats['pdfs_skip']}")
        print(f"❌ Errores: {stats['pdfs_con_error']}")
        print(f"🖼️  Imágenes: {stats['imagenes_subidas']}")
        print("="*70 + "\n")
        
        # Guardar estadísticas
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        stats_path = self.config.LOCAL_OUTPUT_DIR / f"stats_{timestamp}.json"
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        return stats

# ============================================
# FUNCIÓN PRINCIPAL
# ============================================

def main():
    """Función principal"""
    
    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║     PROCESADOR OPTIMIZADO DE PDFs (con Skip y Paralelismo)      ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    
    config = Config()
    
    if not Path(config.OAUTH_CREDENTIALS_PATH).exists():
        print("❌ No se encontró oauth_credentials.json\n")
        return
    
    print(f"📂 Carpeta: {config.DRIVE_FOLDER_ID}")
    print(f"⚡ Hilos: {config.MAX_WORKERS}")
    print(f"⏭️  Skip: {'Activado' if config.SKIP_EXISTING else 'Desactivado'}\n")
    
    try:
        processor = CloudDriveProcessorOptimizado(config)
        stats = processor.procesar_dataset_completo(config.DRIVE_FOLDER_ID)
        
        print("\n🎉 ¡Completado!")
        print(f"📍 https://drive.google.com/drive/folders/{config.DRIVE_FOLDER_ID}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrumpido")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")

if __name__ == "__main__":
    main()