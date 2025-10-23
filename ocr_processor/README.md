# 🔍 OCR Processor para Label Studio

Procesador automático de imágenes con PaddleOCR para generar anotaciones en formato Label Studio desde Google Drive.

## 📋 Características

- ✅ Procesamiento automático de imágenes desde Google Drive
- ✅ Modo incremental: solo procesa imágenes nuevas
- ✅ Auto-guardado cada N imágenes (resistente a interrupciones)
- ✅ Genera formato JSON compatible con Label Studio
- ✅ Soporte para estructuras de carpetas jerárquicas
- ✅ OCR en español con PaddleOCR

## 🚀 Instalación

### Requisitos

- Python 3.9+
- Pipenv (recomendado) o pip

### Instalación con Pipenv

```bash
# Clonar el repositorio
git clone <tu-repo>
cd LAYOUTLM_MOLDES

# Instalar dependencias
pipenv install

# Activar entorno virtual
pipenv shell
```

### Instalación con pip

```bash
pip install -r requirements.txt
```

### Dependencias principales

- `paddleocr==2.7.0.3`
- `paddlepaddle==2.6.0`
- `numpy==1.24.4`
- `google-auth-oauthlib`
- `google-api-python-client`
- `python-dotenv`
- `pillow`
- `tqdm`

## ⚙️ Configuración

### 1. Credenciales de Google Drive

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un proyecto nuevo
3. Habilita Google Drive API
4. Crea credenciales OAuth 2.0
5. Descarga el archivo JSON como `oauth_credentials.json`
6. Colócalo en la raíz del proyecto

### 2. Variables de entorno

Crea un archivo `.env`:

```bash
DRIVE_FOLDER_ID=tu_id_de_carpeta_de_google_drive
OAUTH_CREDENTIALS_PATH=oauth_credentials.json
```

**¿Cómo obtener el DRIVE_FOLDER_ID?**
- Abre la carpeta en Google Drive
- Copia el ID de la URL: `https://drive.google.com/drive/folders/[ESTE_ES_EL_ID]`

### 3. Estructura de carpetas esperada en Drive

```
Carpeta_Principal (DRIVE_FOLDER_ID)
└── Recibos_Imagenes/
    ├── 1. Enero/
    │   ├── 1335432/
    │   │   ├── 1335432_p1.png
    │   │   └── 1335432_p2.png
    │   └── 1411518/
    │       └── 1411518_p1.png
    ├── 2. Febrero/
    └── 3. Marzo/
```

## 🎮 Uso

### Ejecución básica

```bash
python Create_LMv3_dataset_with_paddleOCR.py
```

### Configuración personalizada

Edita las siguientes líneas en el código:

```python
# Línea ~62-68
class Config:
    # Procesamiento
    MAX_IMAGES = None      # None = todas, o número para testing
    BATCH_SIZE = 50        # Auto-guardar cada N imágenes
    AUTO_SAVE = True       # Activar auto-guardado
    
    # Modo incremental
    INCREMENTAL_MODE = True  # Solo procesar imágenes nuevas
    
    # OCR
    PADDLEOCR_LANG = 'es'   # 'es' o 'en'
```

### Ejemplos de uso

**Procesar 20 imágenes de prueba:**
```python
MAX_IMAGES = 20
```

**Procesar todas las imágenes:**
```python
MAX_IMAGES = None
```

**Cambiar frecuencia de auto-guardado:**
```python
BATCH_SIZE = 25  # Guarda cada 25 imágenes
```

## 🔄 Modo Incremental

El modo incremental permite continuar desde donde se quedó:

### Primera ejecución
```bash
python Create_LMv3_dataset_with_paddleOCR.py
```
- Procesa todas las imágenes
- Crea `recibos_label_studio.json`
- Crea `processed_images.json` (registro)

### Ejecuciones subsecuentes
```bash
python Create_LMv3_dataset_with_paddleOCR.py
```
- Lee el registro `processed_images.json`
- Salta imágenes ya procesadas
- Solo procesa las nuevas
- Actualiza el JSON principal

### Ventajas
- ⚡ **10-100x más rápido** en ejecuciones subsecuentes
- 💾 Ahorra API calls de Google Drive
- 🔄 Permite agregar imágenes nuevas sin reprocesar

## 🛡️ Auto-guardado

El sistema guarda automáticamente cada `BATCH_SIZE` imágenes:

```
Procesando imagen 48... ✅
Procesando imagen 49... ✅
Procesando imagen 50... ✅
      💾 Auto-guardando progreso (50 imágenes)... ✅ (50 total)
```

### Archivos generados
```
label_studio_data/
├── recibos_label_studio.json    # JSON principal para Label Studio
├── processed_images.json         # Registro de imágenes procesadas
└── temp_progress_*.json          # Backups temporales (opcionales)
```

### Resistente a interrupciones

Si el proceso se interrumpe (Ctrl+C, error, etc.), el progreso se mantiene:

```bash
# Primera ejecución - procesó 150 imágenes
python Create_LMv3_dataset_with_paddleOCR.py
# [Interrumpido con Ctrl+C]

# Segunda ejecución - continúa desde 151
python Create_LMv3_dataset_with_paddleOCR.py
```

## 📊 Scripts de utilidad

### Verificar progreso

```bash
python verificar_progreso.py
```

Muestra:
- Total de tareas en JSON principal
- Total de imágenes en registro
- Estado de sincronización
- Archivos temporales

## 🏷️ Uso con Label Studio

### 1. Instalar Label Studio

```bash
pip install label-studio
```

### 2. Iniciar Label Studio

```bash
label-studio start
```

### 3. Crear proyecto

1. Abre http://localhost:8080
2. Crea un nuevo proyecto
3. Configura la interfaz de etiquetado:

```xml
<View>
  <Image name="image" value="$ocr"/>
  <Rectangle name="bbox" toName="image"/>
  <TextArea name="transcription" toName="image"/>
</View>
```

### 4. Importar datos

- Ve a "Import"
- Sube `label_studio_data/recibos_label_studio.json`
- Comienza a anotar

## 📈 Estadísticas

Ejemplo de salida:

```
======================================================================
PROCESAMIENTO COMPLETADO
======================================================================
📊 Total de imágenes NUEVAS procesadas: 356
⏭️  Imágenes saltadas (ya procesadas): 0
📄 Total de tareas generadas: 356
======================================================================

💾 Guardando dataset final...
✅ Dataset guardado: label_studio_data\recibos_label_studio.json
   📄 Total de tareas: 356
   🔍 Total de detecciones: 48,204
   📊 Promedio por imagen: 135.4
```

## 🐛 Solución de problemas

### Error: "No matching distribution for paddlepaddle"

```bash
# Instalar versión compatible con tu sistema
pip install paddlepaddle==2.6.0
pip install paddleocr==2.7.0.3
```

### Error: "numpy version incompatible"

```bash
# Forzar versión correcta
pip install --force-reinstall numpy==1.24.4
```

### Error: "DRIVE_FOLDER_ID no configurado"

Verifica que tu archivo `.env` exista y tenga:
```
DRIVE_FOLDER_ID=tu_id_aqui
```

### Proceso muy lento

- Reduce `BATCH_SIZE` a 25 para guardar más frecuente
- Verifica tu conexión a internet
- Considera usar `USE_GPU = True` si tienes GPU

## 📝 Versiones

### v2.0 - Modo Incremental (Actual)
- ✅ Modo incremental
- ✅ Auto-guardado cada N imágenes
- ✅ Resistente a interrupciones
- ✅ Skip de imágenes ya procesadas

### v1.0 - Básico
- ✅ Procesamiento completo
- ⚠️ Sin modo incremental
- ⚠️ Reprocesa todo en cada ejecución

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama (`git checkout -b feature/nueva-caracteristica`)
3. Commit tus cambios (`git commit -m 'Add: nueva característica'`)
4. Push a la rama (`git push origin feature/nueva-caracteristica`)
5. Abre un Pull Request

## 📄 Licencia

[Especificar licencia - ej. MIT, Apache 2.0, etc.]

## 👤 Autor

[Yhon Janampa]
- GitHub: [@Artted12](https://github.com/Artted12)

## 🙏 Agradecimientos

- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) por el motor OCR
- [Label Studio](https://labelstud.io/) por la herramienta de anotación