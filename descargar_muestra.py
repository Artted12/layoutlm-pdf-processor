"""
Script para descargar solo una muestra de imágenes (100 primeras) para prueba
"""
import json
import io
import os
from pathlib import Path
from tqdm import tqdm
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

class ImageDownloader:
    """Descarga imágenes de Google Drive"""
    
    def __init__(self, token_path="token.pickle"):
        # Cargar credenciales
        print("🔐 Cargando credenciales...")
        with open(token_path, 'rb') as token:
            credentials = pickle.load(token)
        
        self.service = build('drive', 'v3', credentials=credentials)
        print("✅ Conectado a Google Drive\n")
    
    def descargar_imagen(self, file_id, output_path):
        """Descarga una imagen de Drive"""
        try:
            request = self.service.files().get_media(fileId=file_id)
            
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            
            while not done:
                status, done = downloader.next_chunk()
            
            # Guardar archivo
            fh.seek(0)
            with open(output_path, 'wb') as f:
                f.write(fh.read())
            
            return True
        except Exception as e:
            return False, str(e)

def descargar_muestra(
    batches_dir="ocr_processor/label_studio_data/batches",
    images_dir="ocr_processor/label_studio_data/images_sample",
    num_batches=2,  # 2 batches = ~100 imágenes
    base_url="http://localhost:8081"
):
    """
    Descarga solo los primeros N batches como muestra
    """
    batches_path = Path(batches_dir)
    images_path = Path(images_dir)
    
    # Crear carpeta de imágenes
    images_path.mkdir(parents=True, exist_ok=True)
    
    print(f"{'='*70}")
    print("DESCARGA DE MUESTRA PARA PRUEBA")
    print(f"{'='*70}\n")
    
    # Listar batches
    batch_files = sorted(batches_path.glob("recibos_batch_*.json"))
    
    if not batch_files:
        print("❌ No se encontraron archivos batch")
        print(f"   Verifica que existan en: {batches_dir}")
        return
    
    print(f"📁 Total de batches disponibles: {len(batch_files)}")
    print(f"🎯 Se descargarán solo los primeros {num_batches} batches\n")
    
    # Seleccionar solo los primeros batches
    batches_a_procesar = batch_files[:num_batches]
    
    print(f"📦 Batches seleccionados:")
    for bf in batches_a_procesar:
        print(f"   - {bf.name}")
    print()
    
    # Inicializar descargador
    downloader = ImageDownloader()
    
    # Procesar cada batch
    imagenes_descargadas = 0
    imagenes_saltadas = 0
    errores = 0
    
    for batch_file in batches_a_procesar:
        print(f"📄 Procesando: {batch_file.name}")
        
        # Leer batch
        with open(batch_file, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
        
        print(f"   Imágenes en este batch: {len(tasks)}")
        
        # Procesar cada tarea
        for task in tqdm(tasks, desc="   Descargando", leave=False):
            # Extraer ID de la URL de Drive
            url = task['data']['ocr']
            
            if 'drive.google.com/uc?id=' in url:
                # Extraer ID
                file_id = url.split('id=')[1].split('&')[0]
                
                # Nombre del archivo
                image_name = task['meta']['image_name']
                output_path = images_path / image_name
                
                # Descargar si no existe
                if not output_path.exists():
                    result = downloader.descargar_imagen(file_id, output_path)
                    if result == True:
                        imagenes_descargadas += 1
                    else:
                        errores += 1
                        tqdm.write(f"      ❌ Error con {image_name}")
                else:
                    imagenes_saltadas += 1
                
                # Actualizar URL a localhost
                nueva_url = f"{base_url}/{image_name}"
                task['data']['ocr'] = nueva_url
        
        # Guardar batch actualizado (con nuevo nombre para no sobrescribir)
        batch_actualizado = batches_path.parent / "batches_sample" / batch_file.name
        batch_actualizado.parent.mkdir(exist_ok=True)
        
        with open(batch_actualizado, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)
        
        print(f"   ✅ Batch actualizado guardado\n")
    
    # Resumen
    print(f"\n{'='*70}")
    print("RESUMEN DE LA DESCARGA")
    print(f"{'='*70}")
    print(f"✅ Imágenes descargadas: {imagenes_descargadas}")
    print(f"⏭️  Imágenes ya existentes: {imagenes_saltadas}")
    print(f"❌ Errores: {errores}")
    print(f"📁 Total de imágenes: {imagenes_descargadas + imagenes_saltadas}")
    print(f"💾 Guardadas en: {images_path}")
    print(f"📦 Batches actualizados en: {batches_path.parent / 'batches_sample'}")
    print(f"{'='*70}\n")
    
    # Instrucciones
    print("📝 PRÓXIMOS PASOS:")
    print()
    print("1️⃣  Inicia el servidor de imágenes (en otra terminal):")
    print(f"   cd {images_path}")
    print(f"   python -m http.server 8081")
    print()
    print("   O con CORS:")
    print(f"   cd {images_path}")
    print(f"   python cors_server.py 8081")
    print()
    print("2️⃣  Verifica que el servidor funciona:")
    print("   Abre en navegador: http://localhost:8081")
    print("   Deberías ver la lista de imágenes")
    print()
    print("3️⃣  En Label Studio:")
    print("   a) Settings → Danger Zone → Delete All Tasks")
    print("   b) Import → Upload Files")
    print(f"   c) Importa SOLO los batches de: {batches_path.parent / 'batches_sample'}")
    print()
    print("4️⃣  ¡Empieza a etiquetar!")
    print()
    print("💡 Si todo funciona bien, ejecuta el script completo para")
    print("   descargar todas las imágenes.\n")

def main():
    """Función principal"""
    
    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║        DESCARGA DE MUESTRA - 100 IMÁGENES PARA PRUEBA          ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # Verificar archivos necesarios
    if not Path("token.pickle").exists():
        print("❌ No se encontró token.pickle")
        print("   Ejecuta primero el script de OCR para autenticarte con Drive")
        return
    
    batches_dir = Path("ocr_processor/label_studio_data/batches")
    if not batches_dir.exists():
        print(f"❌ No se encontró la carpeta: {batches_dir}")
        print("   Verifica la ruta de los batches")
        return
    
    try:
        # Preguntar cuántos batches descargar
        print("¿Cuántos batches quieres descargar para la prueba?")
        print("   1 batch  = ~50 imágenes  (~5 min)")
        print("   2 batches = ~100 imágenes (~10 min)")
        print("   3 batches = ~150 imágenes (~15 min)")
        
        num_batches = input("\nNúmero de batches (default: 2): ").strip()
        num_batches = int(num_batches) if num_batches else 2
        
        print()
        descargar_muestra(num_batches=num_batches)
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
    except KeyboardInterrupt:
        print("\n\n⚠️  Descarga interrumpida por el usuario")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()