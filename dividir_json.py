"""
Script para dividir un JSON grande en archivos más pequeños
"""
import json
from pathlib import Path

def dividir_json(input_file, output_dir, tasks_por_archivo=50):
    """
    Divide un JSON grande en archivos más pequeños
    
    Args:
        input_file: Ruta al JSON grande
        output_dir: Carpeta donde guardar los archivos divididos
        tasks_por_archivo: Número de tareas por archivo
    """
    print(f"📖 Leyendo {input_file}...")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        tasks = json.load(f)
    
    total_tasks = len(tasks)
    print(f"📊 Total de tareas: {total_tasks}")
    
    # Crear carpeta de salida
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Dividir en archivos
    num_archivos = (total_tasks + tasks_por_archivo - 1) // tasks_por_archivo
    
    for i in range(num_archivos):
        start_idx = i * tasks_por_archivo
        end_idx = min((i + 1) * tasks_por_archivo, total_tasks)
        
        batch = tasks[start_idx:end_idx]
        
        output_file = output_path / f"recibos_batch_{i+1:03d}_of_{num_archivos:03d}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(batch, f, indent=2, ensure_ascii=False)
        
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"✅ [{i+1}/{num_archivos}] {output_file.name} - {len(batch)} tareas ({size_mb:.1f} MB)")
    
    print(f"\n🎉 Proceso completado!")
    print(f"📁 {num_archivos} archivos guardados en: {output_path}")
    print(f"\n💡 Importa cada archivo por separado en Label Studio:")
    print(f"   Import → Upload Files → Seleccionar recibos_batch_001_of_{num_archivos:03d}.json")

if __name__ == "__main__":
    # Configuración
    input_file = "ocr_processor/label_studio_data/recibos_label_studio.json"
    output_dir = "ocr_processor/label_studio_data/batches"
    tasks_por_archivo = 50  # 50 imágenes por archivo (ajusta según necesites)
    
    try:
        dividir_json(input_file, output_dir, tasks_por_archivo)
    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo {input_file}")
        print(f"   Verifica la ruta del archivo")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()