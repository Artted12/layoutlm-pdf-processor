# 🎯 Procesador de PDFs con LayoutLM

Sistema automatizado para convertir PDFs de Google Drive a imágenes, optimizado para entrenar modelos LayoutLMv3.

## ✨ Características

- ✅ Procesamiento paralelo (4 hilos)
- ✅ Skip automático de archivos ya procesados
- ✅ Sin uso de espacio local (todo en Drive)
- ✅ Soporte para 1000+ PDFs
- ✅ Autenticación OAuth segura
- ✅ Sistema de caché para ejecuciones incrementales

## 📋 Requisitos

- Python 3.8+
- Cuenta de Google
- Google Drive con los PDFs a procesar

## 🚀 Instalación

### 1. Clonar repositorio
```bash
git clone https://github.com/Artted12/layoutlm-pdf-processor.git
cd layoutlm-pdf-processor
```

### 2. Crear entorno virtual
```bash
# Con pipenv (recomendado)
pipenv install

# O con venv
python -m venv env
source env/bin/activate  # Linux/Mac
.\env\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 3. Configurar variables de entorno
```bash
# Copiar template
cp .env.example .env

# Editar .env con tus datos
# .env
DRIVE_FOLDER_ID=tu_folder_id_de_google_drive
OAUTH_CREDENTIALS_PATH=oauth_credentials.json
```

### 4. Obtener credenciales OAuth de Google

1. Ve a [Google Cloud Console](https://console.cloud.google.com)
2. Crea un nuevo proyecto o selecciona uno existente
3. **APIs & Services** → **Credentials**
4. **+ CREATE CREDENTIALS** → **OAuth 2.0 Client ID**
5. Application type: **Desktop app**
6. Descarga el JSON
7. Guárdalo como `oauth_credentials.json` en la raíz del proyecto

### 5. Habilitar Google Drive API

1. En Google Cloud Console
2. **APIs & Services** → **Library**
3. Busca "Google Drive API"
4. Click **ENABLE**

## 📖 Uso

### Ejecución básica
```bash
python process_drive_pdfs.py
```

### Primera ejecución

En la primera ejecución:
1. Se abrirá tu navegador
2. Autoriza la aplicación
3. Se creará `token.pickle` automáticamente
4. El procesamiento iniciará

### Ejecuciones subsiguientes

- Usa automáticamente el `token.pickle` guardado
- Solo procesa PDFs nuevos (skip de ya procesados)
- Mucho más rápido (solo 2-3 minutos para 50 PDFs nuevos)

## ⚙️ Configuración

Edita `process_drive_pdfs.py` en la clase `Config`:
```python
class Config:
    MAX_WORKERS = 4        # Hilos paralelos (ajusta según tu CPU)
    DPI = 150             # Calidad de imagen (120-300)
    IMAGE_FORMAT = "PNG"  # Formato: PNG o JPEG
    SKIP_EXISTING = True  # Skip de archivos procesados
```

## 📊 Estructura del Proyecto
```
layoutlm-pdf-processor/
├── process_drive_pdfs.py    # Script principal
├── .env                      # Variables de entorno (NO SUBIR)
├── .env.example             # Template de variables
├── .gitignore               # Archivos a ignorar
├── README.md                # Este archivo
├── requirements.txt         # Dependencias Python
├── oauth_credentials.json   # Credenciales OAuth (NO SUBIR)
├── token.pickle            # Token de sesión (NO SUBIR)
├── processed_cache.json    # Caché de procesados (NO SUBIR)
├── logs_drive/             # Logs y estadísticas
├── ocr_processor/                     
│   ├── README.md                      # README específico del OCR
│   ├── .gitignore                     # .gitignore específico 
│   ├── requirements.txt               # Dependencias del OCR
│   ├── Create_LMv3_dataset_with_paddleOCR.py
│   ├── verificar_progreso.py
│   ├── Datos.env.example
│   ├── oauth_credentials.json.example
│   └── label_studio_data/            # Carpeta de salida
```

### `/ocr_processor`
Procesador automático de OCR con PaddleOCR para generar anotaciones en formato Label Studio.

**Características:**
- ✅ Procesamiento incremental de imágenes desde Google Drive
- ✅ Auto-guardado resistente a interrupciones
- ✅ Formato JSON compatible con Label Studio

👉 [Ver documentación detallada](./ocr_processor/README.md)


## 🔐 Seguridad

**NUNCA subas estos archivos:**
- `.env` o `Datos.env`
- `oauth_credentials.json`
- `token.pickle`
- `processed_cache.json`

Todos están incluidos en `.gitignore`

## 📈 Rendimiento

| Escenario | Tiempo |
|-----------|--------|
| Primera ejecución (3000 PDFs) | ~45 minutos |
| Agregar 50 PDFs nuevos | ~3 minutos |
| Re-ejecución sin cambios | ~30 segundos |

## 🐛 Solución de Problemas

### Error: "DRIVE_FOLDER_ID is empty"
```bash
# Verificar que .env tiene el ID correcto
cat .env

# Debe mostrar:
# DRIVE_FOLDER_ID=13LWdjQRbR8VQOiE5IeeormRKrznQ2Th9
```

### Error: "SSL: WRONG_VERSION_NUMBER"

Reducir número de hilos:
```python
MAX_WORKERS = 2
```

### Error: "Rate limit exceeded"

- Esperar 24 horas
- O reducir `MAX_WORKERS` a 2

## 📝 Licencia

MIT License

## 👤 Autor

Yhon Janampa - [@Artted12](https://github.com/Artted12)

## 🤝 Contribuciones

Pull requests son bienvenidos. Para cambios mayores, abre un issue primero.