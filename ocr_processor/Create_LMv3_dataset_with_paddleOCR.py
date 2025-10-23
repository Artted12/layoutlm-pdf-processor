"""
========================================================================
GENERADOR DE ANOTACIONES JSON PARA LABEL STUDIO
========================================================================
Procesa imágenes de Google Drive con PaddleOCR
Genera archivo JSON compatible con Label Studio
Optimizado para procesar miles de imágenes
========================================================================
"""

# ✅ FIX: Desactivar OneDNN para evitar errores
import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import io
import pickle
from pathlib import Path
from typing import List, Dict, Optional
import json
from datetime import datetime
from uuid import uuid4
import numpy as np
from tqdm.auto import tqdm

# Google Drive
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# PaddleOCR
from paddleocr import PaddleOCR
from PIL import Image
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv('Datos.env')

# ============================================
# CONFIGURACIÓN
# ============================================

class Config:
    """Configuración del procesador"""
    
    # Autenticación
    OAUTH_CREDENTIALS_PATH = os.getenv('OAUTH_CREDENTIALS_PATH', 'oauth_credentials.json')
    TOKEN_PATH = "token.pickle"
    
    # Google Drive
    DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID', '')
    IMAGES_FOLDER_NAME = "Recibos_Imagenes"  # Carpeta donde están las imágenes
    
    # Label Studio
    LABEL_STUDIO_URL_BASE = "http://localhost:8080"
    
    # PaddleOCR
    PADDLEOCR_LANG = 'es'
    USE_ANGLE_CLS = False
    USE_GPU = False
    
    # Procesamiento
    MAX_IMAGES = None  # None = todas, o número específico para testing
    BATCH_SIZE = 50  # Guardar progreso cada N imágenes
    AUTO_SAVE = True  # Guardar automáticamente cada BATCH_SIZE imágenes
    
    # Salida
    OUTPUT_DIR = Path(__file__).parent / "label_studio_data"
    OUTPUT_JSON = "recibos_label_studio.json"
    PROCESSED_IMAGES_LOG = "processed_images.json"  # Registro de imágenes procesadas
    INCREMENTAL_MODE = True  # Activar modo incremental
    
    # Scopes
    SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    
    def __init__(self):
        self.OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================
# GESTOR DE AUTENTICACIÓN
# ============================================

class OAuthManager:
    """Maneja autenticación OAuth"""
    
    def __init__(self, credentials_path: str, token_path: str, scopes: List[str]):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.scopes = scopes
    
    def autenticar(self) -> Credentials:
        """Autentica con Google"""
        credentials = None
        
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                credentials = pickle.load(token)
        
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except:
                    os.remove(self.token_path)
                    return self.autenticar()
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, self.scopes
                )
                credentials = flow.run_local_server(port=0)
            
            with open(self.token_path, 'wb') as token:
                pickle.dump(credentials, token)
        
        return credentials

# ============================================
# GESTOR DE GOOGLE DRIVE
# ============================================

class GoogleDriveImageReader:
    """Lee imágenes desde Google Drive"""
    
    def __init__(self, credentials: Credentials):
        self.service = build('drive', 'v3', credentials=credentials)
    
    def encontrar_carpeta_imagenes(self, parent_folder_id: str, carpeta_nombre: str) -> Optional[str]:
        """Encuentra la carpeta de imágenes"""
        query = f"name='{carpeta_nombre}' and '{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        
        try:
            results = self.service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=1
            ).execute()
            
            folders = results.get('files', [])
            if folders:
                return folders[0]['id']
            return None
        except HttpError as e:
            print(f"❌ Error buscando carpeta: {e}")
            return None
    
    def listar_carpetas(self, parent_folder_id: str) -> List[Dict]:
        """Lista todas las carpetas dentro de una carpeta"""
        query = f"'{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        all_folders = []
        page_token = None
        
        while True:
            try:
                results = self.service.files().list(
                    q=query,
                    fields="nextPageToken, files(id, name)",
                    orderBy="name",
                    pageSize=100,
                    pageToken=page_token
                ).execute()
                
                all_folders.extend(results.get('files', []))
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            except HttpError as e:
                print(f"❌ Error listando carpetas: {e}")
                break
        
        return all_folders
    
    def listar_imagenes(self, folder_id: str) -> List[Dict]:
        """Lista imágenes PNG/JPEG en una carpeta"""
        query = f"'{folder_id}' in parents and (mimeType='image/png' or mimeType='image/jpeg') and trashed=false"
        all_images = []
        page_token = None
        
        while True:
            try:
                results = self.service.files().list(
                    q=query,
                    fields="nextPageToken, files(id, name, webContentLink, webViewLink)",
                    orderBy="name",
                    pageSize=100,
                    pageToken=page_token
                ).execute()
                
                all_images.extend(results.get('files', []))
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            except HttpError as e:
                print(f"❌ Error listando imágenes: {e}")
                break
        
        return all_images
    
    def descargar_imagen_en_memoria(self, file_id: str) -> Optional[np.ndarray]:
        """Descarga imagen desde Drive a memoria como numpy array"""
        try:
            request = self.service.files().get_media(fileId=file_id)
            
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            
            while not done:
                status, done = downloader.next_chunk()
            
            fh.seek(0)
            img = Image.open(fh).convert('RGB')
            img_array = np.array(img)
            
            return img_array
        
        except Exception as e:
            print(f"      ❌ Error descargando imagen: {e}")
            return None

# ============================================
# PROCESADOR CON PADDLEOCR
# ============================================

class PaddleOCRProcessor:
    """Procesa imágenes con PaddleOCR"""
    
    def __init__(self, config: Config):
        self.config = config
        
        print("🔄 Inicializando PaddleOCR...")
        self.ocr = PaddleOCR(
            use_angle_cls=config.USE_ANGLE_CLS,
            lang=config.PADDLEOCR_LANG,
            use_gpu=config.USE_GPU,
            show_log=False
        )
        print("✅ PaddleOCR inicializado\n")
    
    def create_image_url(self, image_id: str, image_name: str) -> str:
        """Crea URL para Label Studio"""
        return f"https://drive.google.com/uc?id={image_id}&export=download"
    
    def procesar_imagen(self, img_array: np.ndarray, image_info: Dict) -> Dict:
        """Procesa una imagen con PaddleOCR y genera formato Label Studio"""
        output_json = {}
        annotation_result = []
        
        image_height, image_width = img_array.shape[:2]
        image_url = self.create_image_url(image_info['id'], image_info['name'])
        
        output_json['data'] = {"ocr": image_url}
        
        try:
            result = self.ocr.ocr(img_array, cls=False)
            
            if not result or not result[0]:
                output_json['predictions'] = [{"result": [], "score": 0.0}]
                return output_json
            
            for output in result:
                for item in output:
                    co_ord = item[0]
                    text_data = item[1]
                    text = text_data[0]
                    confidence = text_data[1]
                    
                    x1, y1 = co_ord[0]
                    x2, y2 = co_ord[2]
                    
                    width = x2 - x1
                    height = y2 - y1
                    
                    bbox = {
                        'x': 100 * x1 / image_width,
                        'y': 100 * y1 / image_height,
                        'width': 100 * width / image_width,
                        'height': 100 * height / image_height,
                        'rotation': 0
                    }
                    
                    if not text or not text.strip():
                        continue
                    
                    region_id = str(uuid4())[:10]
                    
                    bbox_result = {
                        'id': region_id,
                        'from_name': 'bbox',
                        'to_name': 'image',
                        'type': 'rectangle',
                        'value': bbox
                    }
                    
                    transcription_result = {
                        'id': region_id,
                        'from_name': 'transcription',
                        'to_name': 'image',
                        'type': 'textarea',
                        'value': dict(text=[text], **bbox),
                        'score': float(confidence)
                    }
                    
                    annotation_result.extend([bbox_result, transcription_result])
            
            if annotation_result:
                avg_score = np.mean([
                    r['score'] for r in annotation_result 
                    if 'score' in r
                ])
            else:
                avg_score = 0.0
            
            output_json['predictions'] = [{
                "result": annotation_result,
                "score": float(avg_score)
            }]
            
            output_json['meta'] = {
                'image_name': image_info['name'],
                'image_id': image_info['id'],
                'processed_at': datetime.now().isoformat(),
                'num_detections': len(annotation_result) // 2
            }
        
        except Exception as e:
            print(f"      ❌ Error en OCR: {e}")
            output_json['predictions'] = [{"result": [], "score": 0.0}]
            output_json['meta'] = {
                'error': str(e),
                'image_name': image_info['name']
            }
        
        return output_json

# ============================================
# PROCESADOR PRINCIPAL
# ============================================

class LabelStudioDatasetGenerator:
    """Generador principal de dataset para Label Studio"""
    
    def __init__(self, config: Config):
        self.config = config
        
        print("🔐 Autenticando con Google Drive...")
        oauth = OAuthManager(
            config.OAUTH_CREDENTIALS_PATH,
            config.TOKEN_PATH,
            config.SCOPES
        )
        credentials = oauth.autenticar()
        
        self.drive = GoogleDriveImageReader(credentials)
        self.ocr_processor = PaddleOCRProcessor(config)
        
        # Cargar imágenes ya procesadas
        self.processed_images = self._cargar_registro_procesadas()
    
    def _cargar_registro_procesadas(self) -> set:
        """Carga el registro de imágenes ya procesadas"""
        log_file = self.config.OUTPUT_DIR / self.config.PROCESSED_IMAGES_LOG
        
        if not self.config.INCREMENTAL_MODE or not log_file.exists():
            return set()
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get('processed_image_ids', []))
        except Exception as e:
            print(f"⚠️  No se pudo cargar el registro de procesadas: {e}")
            return set()
    
    def _guardar_registro_procesadas(self, image_ids: set):
        """Guarda el registro de imágenes procesadas"""
        log_file = self.config.OUTPUT_DIR / self.config.PROCESSED_IMAGES_LOG
        
        try:
            data = {
                'processed_image_ids': list(image_ids),
                'last_updated': datetime.now().isoformat(),
                'total_count': len(image_ids)
            }
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  No se pudo guardar el registro: {e}")
    
    def generar_dataset(self) -> List[Dict]:
        """Genera dataset completo para Label Studio"""
        print("="*70)
        print("GENERANDO DATASET PARA LABEL STUDIO")
        if self.config.INCREMENTAL_MODE:
            print("🔄 MODO INCREMENTAL ACTIVADO")
            print(f"   📋 Imágenes ya procesadas: {len(self.processed_images)}")
        print("="*70 + "\n")
        
        # Encontrar carpeta de imágenes
        print(f"🔍 Buscando carpeta '{self.config.IMAGES_FOLDER_NAME}'...")
        images_root_id = self.drive.encontrar_carpeta_imagenes(
            self.config.DRIVE_FOLDER_ID,
            self.config.IMAGES_FOLDER_NAME
        )
        
        if not images_root_id:
            print(f"❌ No se encontró la carpeta '{self.config.IMAGES_FOLDER_NAME}'")
            return []
        
        print(f"✅ Carpeta encontrada: {images_root_id}\n")
        
        # Listar carpetas de meses
        print("📁 Listando carpetas de meses...")
        carpetas_meses = self.drive.listar_carpetas(images_root_id)
        print(f"   Encontradas {len(carpetas_meses)} carpetas\n")
        
        label_studio_tasks = []
        total_imagenes = 0
        imagenes_saltadas = 0
        nuevas_procesadas = set()
        
        # Procesar cada mes
        for idx_mes, carpeta_mes in enumerate(carpetas_meses, 1):
            mes_nombre = carpeta_mes['name']
            mes_id = carpeta_mes['id']
            
            print(f"{'='*70}")
            print(f"📁 [{idx_mes}/{len(carpetas_meses)}] {mes_nombre}")
            print(f"{'='*70}")
            
            # Listar carpetas con números dentro del mes
            carpetas_numeros = self.drive.listar_carpetas(mes_id)
            print(f"   📂 {len(carpetas_numeros)} carpetas encontradas")
            
            # Procesar cada carpeta con número
            for idx_num, carpeta_num in enumerate(carpetas_numeros, 1):
                num_nombre = carpeta_num['name']
                num_id = carpeta_num['id']
                
                # Listar imágenes en esta carpeta
                imagenes = self.drive.listar_imagenes(num_id)
                
                if not imagenes:
                    continue
                
                print(f"\n   [{idx_num}/{len(carpetas_numeros)}] {num_nombre}: {len(imagenes)} imagen(es)")
                
                # Procesar cada imagen
                for idx_img, imagen in enumerate(imagenes, 1):
                    # Verificar si ya fue procesada
                    if self.config.INCREMENTAL_MODE and imagen['id'] in self.processed_images:
                        imagenes_saltadas += 1
                        continue
                    
                    if self.config.MAX_IMAGES and total_imagenes >= self.config.MAX_IMAGES:
                        print(f"\n⚠️  Límite de {self.config.MAX_IMAGES} imágenes alcanzado")
                        break
                    
                    print(f"      [{idx_img}/{len(imagenes)}] {imagen['name']}...", end=" ")
                    
                    # Descargar imagen
                    img_array = self.drive.descargar_imagen_en_memoria(imagen['id'])
                    
                    if img_array is None:
                        print("❌ Error descargando")
                        continue
                    
                    # Procesar con OCR
                    task = self.ocr_processor.procesar_imagen(img_array, imagen)
                    
                    # Agregar metadata adicional
                    task['meta']['carpeta_mes'] = mes_nombre
                    task['meta']['carpeta_numero'] = num_nombre
                    
                    label_studio_tasks.append(task)
                    nuevas_procesadas.add(imagen['id'])
                    total_imagenes += 1
                    
                    num_detections = task['meta'].get('num_detections', 0)
                    print(f"✅ {num_detections} detecciones")
                    
                    # Guardar progreso automático cada BATCH_SIZE
                    if self.config.AUTO_SAVE and total_imagenes % self.config.BATCH_SIZE == 0:
                        self._guardar_progreso_completo(
                            label_studio_tasks, 
                            nuevas_procesadas,
                            total_imagenes
                        )
                
                if self.config.MAX_IMAGES and total_imagenes >= self.config.MAX_IMAGES:
                    break
            
            if self.config.MAX_IMAGES and total_imagenes >= self.config.MAX_IMAGES:
                break
        
        print(f"\n{'='*70}")
        print("PROCESAMIENTO COMPLETADO")
        print(f"{'='*70}")
        print(f"📊 Total de imágenes NUEVAS procesadas: {total_imagenes}")
        if self.config.INCREMENTAL_MODE:
            print(f"⏭️  Imágenes saltadas (ya procesadas): {imagenes_saltadas}")
        print(f"📄 Total de tareas generadas: {len(label_studio_tasks)}")
        print(f"{'='*70}\n")
        
        # Actualizar registro de procesadas (guardado final)
        if self.config.INCREMENTAL_MODE:
            self.processed_images.update(nuevas_procesadas)
            self._guardar_registro_procesadas(self.processed_images)
            print(f"📝 Registro actualizado: {len(self.processed_images)} imágenes totales")
        
        return label_studio_tasks
    
    def _guardar_progreso(self, tasks: List[Dict], num_processed: int):
        """Guarda progreso intermedio (solo temporal)"""
        temp_file = self.config.OUTPUT_DIR / f"temp_progress_{num_processed}.json"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)
        print(f"\n      💾 Progreso temporal guardado: {num_processed} imágenes")
    
    def _guardar_progreso_completo(self, tasks: List[Dict], nuevas_procesadas: set, num_processed: int):
        """
        Guarda progreso completo (registro + JSON) - resistente a interrupciones
        """
        print(f"\n      💾 Auto-guardando progreso ({num_processed} imágenes)...", end=" ")
        
        try:
            # 1. Actualizar registro de procesadas
            procesadas_hasta_ahora = self.processed_images.union(nuevas_procesadas)
            self._guardar_registro_procesadas(procesadas_hasta_ahora)
            
            # 2. Guardar/actualizar JSON principal
            output_file = self.config.OUTPUT_DIR / self.config.OUTPUT_JSON
            
            # Cargar tareas existentes si existen
            existing_tasks = []
            if output_file.exists():
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        existing_tasks = json.load(f)
                except:
                    pass
            
            # Combinar con nuevas (evitar duplicados por image_id)
            existing_ids = {t['meta']['image_id'] for t in existing_tasks if 'meta' in t and 'image_id' in t['meta']}
            nuevas_tareas = [t for t in tasks if t['meta']['image_id'] not in existing_ids]
            
            all_tasks = existing_tasks + nuevas_tareas
            
            # Guardar
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_tasks, f, indent=2, ensure_ascii=False)
            
            print(f"✅ ({len(all_tasks)} total)")
        
        except Exception as e:
            print(f"❌ Error: {e}")
    
    def guardar_dataset(self, tasks: List[Dict]):
        """Guarda dataset final (modo incremental: append)"""
        output_file = self.config.OUTPUT_DIR / self.config.OUTPUT_JSON
        
        # En modo incremental, cargar tareas existentes
        existing_tasks = []
        if self.config.INCREMENTAL_MODE and output_file.exists():
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    existing_tasks = json.load(f)
                print(f"📂 Cargadas {len(existing_tasks)} tareas existentes")
            except Exception as e:
                print(f"⚠️  No se pudieron cargar tareas existentes: {e}")
        
        # Combinar tareas
        all_tasks = existing_tasks + tasks
        
        print(f"💾 Guardando dataset final...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_tasks, f, indent=2, ensure_ascii=False)
        
        total_detections = sum(
            task['meta'].get('num_detections', 0) 
            for task in all_tasks
        )
        
        print(f"✅ Dataset guardado: {output_file}")
        print(f"   📄 Total de tareas: {len(all_tasks)}")
        if self.config.INCREMENTAL_MODE and existing_tasks:
            print(f"   🆕 Tareas nuevas agregadas: {len(tasks)}")
        print(f"   🔍 Total de detecciones: {total_detections}")
        if all_tasks:
            print(f"   📊 Promedio por imagen: {total_detections / len(all_tasks):.1f}")
        
        return output_file

# ============================================
# FUNCIÓN PRINCIPAL
# ============================================

def main():
    """Función principal"""
    
    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║     GENERADOR DE DATASET PARA LABEL STUDIO CON PADDLEOCR        ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    
    config = Config()
    
    if not Path(config.OAUTH_CREDENTIALS_PATH).exists():
        print("❌ No se encontró oauth_credentials.json\n")
        return
    
    if not config.DRIVE_FOLDER_ID:
        print("❌ DRIVE_FOLDER_ID no configurado en .env\n")
        return
    
    print(f"📂 Carpeta de Drive: {config.DRIVE_FOLDER_ID}")
    print(f"🖼️  Carpeta de imágenes: {config.IMAGES_FOLDER_NAME}")
    print(f"🌐 Idioma OCR: {config.PADDLEOCR_LANG}")
    print(f"📊 Límite de imágenes: {config.MAX_IMAGES or 'Sin límite'}")
    print(f"💾 Salida: {config.OUTPUT_DIR / config.OUTPUT_JSON}\n")
    
    try:
        generator = LabelStudioDatasetGenerator(config)
        tasks = generator.generar_dataset()
        
        if not tasks:
            print("⚠️  No se generaron tareas")
            return
        
        output_file = generator.guardar_dataset(tasks)
        
        print(f"\n🎉 ¡Completado!")
        print(f"\n📝 Próximos pasos:")
        print(f"   1. Abre Label Studio")
        print(f"   2. Crea un nuevo proyecto")
        print(f"   3. Importa: {output_file}")
        print(f"   4. Comienza a anotar\n")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso interrumpido")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()