# Gestor de Oficina Pro

**Gestor de archivos de oficina** con explorador, búsqueda avanzada, backups, sincronización offline y compresión de archivos. Compatible con **Linux, macOS y Windows**.

---

## Características

| Pestaña | Función |
|---|---|
| 📁 **Explorador** | Navegar carpetas, crear/eliminar/copiar archivos |
| 🔍 **Búsqueda** | Buscar por nombre, tipo o contenido de texto |
| 💾 **Backups** | Backup manual o automático (cada hora) con restauración |
| 🔄 **Sincronización** | Caché offline y sincronización de cambios |
| 🗜️ **Compresión** | Comprimir/descomprimir ZIP, TAR.GZ, TAR.BZ2 |

---

## Requisitos del sistema

| Requisito | Versión mínima |
|---|---|
| Python | 3.8 o superior |
| Tkinter | Incluido en Python estándar |
| Sistema operativo | Linux, macOS o Windows |

### Dependencia opcional (solo Windows)
- **win10toast** → notificaciones nativas de escritorio en Windows 10/11

---

## Instalación

### 1. Clonar o descargar el proyecto

```bash
# Con Git
git clone https://github.com/tu-usuario/GestorOficina.git
cd GestorOficina

# O descargar el ZIP y descomprimir manualmente
```

### 2. (Recomendado) Crear un entorno virtual

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Windows (CMD)
.venv\Scripts\activate.bat
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

> **Nota Linux/macOS:** Para recibir notificaciones de escritorio instala `libnotify`:
> ```bash
> # Debian / Ubuntu
> sudo apt install libnotify-bin
>
> # Fedora
> sudo dnf install libnotify
>
> # macOS (Homebrew)
> brew install libnotify
> ```

### 4. Verificar que Tkinter está disponible

```bash
python -c "import tkinter; print('Tkinter OK')"
```

Si ves un error en Linux, instala el paquete del sistema:

```bash
# Debian / Ubuntu
sudo apt install python3-tk

# Fedora
sudo dnf install python3-tkinter
```

---

## Uso

### Ejecución básica (asistente de configuración)

En la **primera ejecución** el programa mostrará un diálogo para elegir la carpeta de oficina. La elección se guarda en `~/.gestor_oficina.json` y no volverá a preguntar.

```bash
python gestor_oficina.py
```

### Especificar la ruta por argumento

```bash
# Linux / macOS
python gestor_oficina.py --ruta /home/usuario/oficina

# Windows (PowerShell)
python gestor_oficina.py --ruta "C:\Users\usuario\Documentos\oficina"

# Con ruta de red (Windows)
python gestor_oficina.py --ruta "\\192.168.1.10\oficina"

# Con carpeta de backup personalizada
python gestor_oficina.py --ruta /home/usuario/oficina --backup /mnt/nas/backup
```

### Argumentos disponibles

| Argumento | Alias | Descripción |
|---|---|---|
| `--ruta RUTA` | `-r RUTA` | Carpeta principal de oficina |
| `--backup RUTA` | `-b RUTA` | Carpeta de backups |
| `--reset-config` | — | Elimina la config guardada y muestra el asistente de nuevo |
| `--help` | `-h` | Muestra la ayuda |

### Restablecer configuración

```bash
python gestor_oficina.py --reset-config
```

---

## Estructura del proyecto

```
GestorOficina/
├── gestor_oficina.py   # Código principal de la aplicación
├── requirements.txt    # Dependencias Python
└── README.md           # Esta documentación
```

### Archivos generados en tiempo de ejecución

| Archivo / Carpeta | Descripción |
|---|---|
| `~/.gestor_oficina.json` | Configuración (rutas, hashes, archivos vigilados) |
| `~/oficina_backup/` | Backups (ruta por defecto, modificable) |
| `~/.oficina_sync/` | Caché de sincronización offline |

---

## Funcionamiento de las rutas

La aplicación aplica el siguiente orden de prioridad para determinar las rutas:

1. **Argumento CLI** (`--ruta`, `--backup`) — máxima prioridad
2. **Configuración guardada** en `~/.gestor_oficina.json`
3. **Asistente de primera ejecución** — diálogo gráfico al iniciar
4. **Valores por defecto** → `~/oficina` y `~/oficina_backup`

---

## Uso de las funciones principales

### Explorador de archivos
- Usa el **árbol de carpetas** (izquierda) para navegar
- Doble clic en una carpeta para abrirla
- Clic derecho sobre un archivo → menú contextual (abrir, copiar, eliminar, vigilar)
- Botones de la barra inferior para crear carpetas/archivos o subir archivos locales

### Búsqueda
- Ingresa el término y pulsa **Buscar** o `Enter`
- Activa **"Buscar en contenido"** para buscar dentro de archivos de texto (< 1 MB)
- Doble clic en un resultado para abrirlo o navegar a su carpeta

### Backups
- Pulsa **"Crear Backup Ahora"** para un backup manual inmediato
- Activa **"Backup Automático"** para crear un backup cada hora
- Selecciona un backup de la lista y pulsa **"Restaurar Backup"**

### Sincronización offline
1. Pulsa **"Descargar Todo (Offline)"** para guardar los archivos en caché local
2. Trabaja sin conexión modificando los archivos en caché (`~/.oficina_sync/`)
3. Cuando recuperes la conexión, pulsa **"Sincronizar Cambios"**

### Compresión
- Selecciona archivos en el explorador → pestaña Compresión → **"Comprimir Selección"**
- Elige el formato: `zip`, `tar.gz` o `tar.bz2`
- Para descomprimir, selecciona el archivo y pulsa **"Descomprimir Selección"**

---

## Solución de problemas

| Problema | Solución |
|---|---|
| `ModuleNotFoundError: No module named 'tkinter'` | Instala `python3-tk` con el gestor de paquetes del sistema |
| No aparecen notificaciones en Linux | Instala `libnotify-bin` (`sudo apt install libnotify-bin`) |
| No aparecen notificaciones en Windows | Instala `win10toast` (`pip install win10toast`) |
| La carpeta de red no aparece | Verifica la conexión y usa `--ruta \\servidor\recurso` o monta la unidad primero |
| Se muestra el asistente en cada ejecución | Verifica que `~/.gestor_oficina.json` tenga permisos de escritura |
| Quiero cambiar la carpeta de oficina | Ejecuta `python gestor_oficina.py --reset-config` o edita `~/.gestor_oficina.json` |

---

## Licencia

MIT — libre para uso personal y comercial.
