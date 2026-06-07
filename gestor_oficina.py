# -*- coding: utf-8 -*-
"""
Gestor de Oficina Pro
====================
Aplicación de gestión de archivos para carpetas de oficina locales o en red.
Compatible con Linux, macOS y Windows.

Uso:
    python gestor_oficina.py [--ruta /ruta/oficina] [--backup /ruta/backup]

@author: flony
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import shutil
import platform
from pathlib import Path
import threading
import json
from datetime import datetime
import hashlib
import time
import zipfile
import tarfile
import argparse
import sys

# Para notificaciones del sistema
try:
    if platform.system() == "Linux":
        import subprocess
    elif platform.system() == "Windows":
        from win10toast import ToastNotifier
        toast = ToastNotifier()
except ImportError:
    pass

class GestorOficina:
    def __init__(self, root, ruta_oficina_arg=None, ruta_backup_arg=None):
        self.root = root
        self.root.title("Gestor de Oficina Pro - v1.0")
        self.root.geometry("1100x700")
        
        # Detectar sistema operativo
        self.sistema = platform.system()
        
        # Archivo de configuración para sync offline
        self.config_file = os.path.join(os.path.expanduser("~"), ".gestor_oficina.json")
        
        # Cargar configuración existente primero
        self.load_config()
        
        # Configurar rutas: prioridad → argumento CLI > config guardada > asistente
        self.setup_paths(ruta_oficina_arg, ruta_backup_arg)
        
        # Variables de control
        self.sync_active = tk.BooleanVar(value=False)
        self.auto_backup = tk.BooleanVar(value=False)
        self.notifications_enabled = tk.BooleanVar(value=True)
        self.current_path = self.ruta_oficina
        self.search_results = []
        
        # Crear interfaz
        self.create_widgets()
        
        # Cargar archivos iniciales
        self.refresh_files()
        
        # Iniciar monitor de sincronización
        self.start_sync_monitor()
        
        # Iniciar monitor de notificaciones
        self.start_notification_monitor()
    
    def _default_oficina(self):
        """Retorna la ruta por defecto de la carpeta de oficina según el SO"""
        home = os.path.expanduser("~")
        return os.path.join(home, "oficina")

    def _default_backup(self):
        """Retorna la ruta por defecto de backup según el SO"""
        home = os.path.expanduser("~")
        return os.path.join(home, "oficina_backup")

    def _default_cache(self):
        """Retorna la ruta por defecto del cache de sincronización"""
        home = os.path.expanduser("~")
        return os.path.join(home, ".oficina_sync")

    def setup_paths(self, ruta_oficina_arg=None, ruta_backup_arg=None):
        """Configura las rutas de forma genérica y configurable.
        
        Orden de prioridad:
          1. Argumentos pasados por línea de comandos
          2. Rutas guardadas en el archivo de configuración JSON
          3. Asistente de primera ejecución (diálogo gráfico)
          4. Valores por defecto: ~/oficina  y  ~/oficina_backup
        """
        # 1. Intentar obtener rutas desde argumentos CLI
        if ruta_oficina_arg:
            self.ruta_oficina = ruta_oficina_arg
        elif self.config.get('ruta_oficina'):
            self.ruta_oficina = self.config['ruta_oficina']
        else:
            # 3. Asistente de primera ejecución
            self.ruta_oficina = self._ask_first_run_config()

        if ruta_backup_arg:
            self.ruta_backup = ruta_backup_arg
        elif self.config.get('ruta_backup'):
            self.ruta_backup = self.config['ruta_backup']
        else:
            self.ruta_backup = self._default_backup()

        # Cache siempre en el home del usuario
        self.ruta_sync_cache = self.config.get('ruta_sync_cache', self._default_cache())

        # Persistir las rutas elegidas
        self.config['ruta_oficina'] = self.ruta_oficina
        self.config['ruta_backup'] = self.ruta_backup
        self.config['ruta_sync_cache'] = self.ruta_sync_cache
        self._save_config_data()

        # Crear carpetas necesarias
        for ruta in [self.ruta_backup, self.ruta_sync_cache]:
            if not os.path.exists(ruta):
                try:
                    os.makedirs(ruta, exist_ok=True)
                except Exception as e:
                    print(f"Error creando {ruta}: {e}")

    def _ask_first_run_config(self):
        """Muestra un diálogo para configurar la carpeta de oficina en la primera ejecución."""
        default = self._default_oficina()

        dialog = tk.Toplevel(self.root)
        dialog.title("Configuración Inicial - Gestor de Oficina")
        dialog.geometry("520x200")
        dialog.resizable(False, False)
        dialog.grab_set()  # Modal

        tk.Label(dialog,
                 text="¡Bienvenido a Gestor de Oficina Pro!\n"
                      "Por favor, elige la carpeta principal donde se guardarán los archivos de oficina.",
                 wraplength=480, justify='left', pady=10).pack(padx=20)

        frame = tk.Frame(dialog)
        frame.pack(fill=tk.X, padx=20, pady=5)

        tk.Label(frame, text="Carpeta de oficina:").pack(side=tk.LEFT)
        entry_var = tk.StringVar(value=default)
        entry = tk.Entry(frame, textvariable=entry_var, width=40)
        entry.pack(side=tk.LEFT, padx=5)

        def browse():
            chosen = filedialog.askdirectory(initialdir=os.path.expanduser("~"),
                                             title="Selecciona la carpeta de oficina")
            if chosen:
                entry_var.set(chosen)

        tk.Button(frame, text="Examinar...", command=browse).pack(side=tk.LEFT)

        result = [default]

        def confirm():
            path = entry_var.get().strip()
            if not path:
                messagebox.showwarning("Advertencia", "Debes especificar una ruta.", parent=dialog)
                return
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo crear la carpeta:\n{e}", parent=dialog)
                return
            result[0] = path
            dialog.destroy()

        tk.Button(dialog, text="Aceptar", command=confirm, width=12).pack(pady=10)
        self.root.wait_window(dialog)
        return result[0]
    
    def load_config(self):
        """Carga la configuración guardada (rutas, hashes, archivos vigilados)"""
        self.config = {}
        self.file_hashes = {}
        self.last_sync = {}
        self.watched_files = set()

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config = data  # guardar todo el dict
                    self.file_hashes = data.get('hashes', {})
                    self.last_sync = data.get('last_sync', {})
                    self.watched_files = set(data.get('watched_files', []))
            except Exception:
                pass

    def _save_config_data(self):
        """Persiste el dict self.config completo al disco."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando config: {e}")

    def save_config(self):
        """Guarda hashes y archivos vigilados en la configuración"""
        self.config['hashes'] = self.file_hashes
        self.config['last_sync'] = self.last_sync
        self.config['watched_files'] = list(self.watched_files)
        self._save_config_data()
    
    def create_widgets(self):
        """Crea la interfaz gráfica mejorada"""
        # Estilos
        style = ttk.Style()
        style.theme_use('clam')
        
        # Frame principal con notebook (pestañas)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Pestaña 1: Explorador
        self.create_explorer_tab()
        
        # Pestaña 2: Búsqueda
        self.create_search_tab()
        
        # Pestaña 3: Backups
        self.create_backup_tab()
        
        # Pestaña 4: Sincronización
        self.create_sync_tab()
        
        # Pestaña 5: Compresión
        self.create_compression_tab()
        
        # Barra de estado general
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_bar = ttk.Label(status_frame, text="Listo", relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.sync_indicator = ttk.Label(status_frame, text="⚫ Sync: OFF", 
                                       relief=tk.SUNKEN, width=15)
        self.sync_indicator.pack(side=tk.RIGHT, padx=5)
        
        self.notif_indicator = ttk.Label(status_frame, text="🔔 ON", 
                                        relief=tk.SUNKEN, width=10)
        self.notif_indicator.pack(side=tk.RIGHT, padx=5)
    
    def create_explorer_tab(self):
        """Crea la pestaña del explorador de archivos"""
        explorer_frame = ttk.Frame(self.notebook)
        self.notebook.add(explorer_frame, text="📁 Explorador")
        
        # Toolbar
        toolbar = ttk.Frame(explorer_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # Barra de ruta
        ttk.Label(toolbar, text="Ruta:").pack(side=tk.LEFT, padx=5)
        self.path_entry = ttk.Entry(toolbar, width=50)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.path_entry.insert(0, self.current_path)
        self.path_entry.bind('<Return>', lambda e: self.navigate_to_path())
        
        ttk.Button(toolbar, text="↑ Arriba", 
                  command=self.go_up).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🏠 Inicio", 
                  command=self.go_home).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🔄", 
                  command=self.refresh_files).pack(side=tk.LEFT, padx=2)
        
        # Frame principal con dos paneles
        paned = ttk.PanedWindow(explorer_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Panel izquierdo: Árbol de carpetas
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="Carpetas", font=('Arial', 10, 'bold')).pack()
        
        # Treeview para carpetas
        tree_scroll = ttk.Scrollbar(left_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.folder_tree = ttk.Treeview(left_frame, yscrollcommand=tree_scroll.set)
        self.folder_tree.pack(fill=tk.BOTH, expand=True)
        tree_scroll.config(command=self.folder_tree.yview)
        
        self.folder_tree.bind('<<TreeviewSelect>>', self.on_folder_select)
        self.populate_folder_tree()
        
        # Panel derecho: Lista de archivos
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)
        
        ttk.Label(right_frame, text="Archivos", font=('Arial', 10, 'bold')).pack()
        
        # Treeview para archivos con columnas
        columns = ('Nombre', 'Tamaño', 'Tipo', 'Modificado')
        self.file_tree = ttk.Treeview(right_frame, columns=columns, show='tree headings')
        
        # Configurar columnas
        self.file_tree.heading('#0', text='')
        self.file_tree.column('#0', width=30)
        self.file_tree.heading('Nombre', text='Nombre')
        self.file_tree.column('Nombre', width=300)
        self.file_tree.heading('Tamaño', text='Tamaño')
        self.file_tree.column('Tamaño', width=100)
        self.file_tree.heading('Tipo', text='Tipo')
        self.file_tree.column('Tipo', width=100)
        self.file_tree.heading('Modificado', text='Modificado')
        self.file_tree.column('Modificado', width=150)
        
        file_scroll = ttk.Scrollbar(right_frame, command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=file_scroll.set)
        
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        file_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Doble clic para abrir carpetas
        self.file_tree.bind('<Double-1>', self.on_file_double_click)
        
        # Menú contextual
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Abrir", command=self.open_file)
        self.context_menu.add_command(label="Copiar", command=self.copy_file)
        self.context_menu.add_command(label="Eliminar", command=self.delete_file)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🔔 Activar notificación", command=self.watch_file)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Propiedades", command=self.show_properties)
        
        self.file_tree.bind('<Button-3>', self.show_context_menu)
        
        # Botones de acción
        button_frame = ttk.Frame(explorer_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(button_frame, text="➕ Nueva Carpeta", 
                  command=self.new_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="📄 Nuevo Archivo", 
                  command=self.new_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="📥 Subir Archivo", 
                  command=self.upload_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="🗑️ Eliminar", 
                  command=self.delete_file).pack(side=tk.LEFT, padx=2)
    
    def create_search_tab(self):
        """Crea la pestaña de búsqueda"""
        search_frame = ttk.Frame(self.notebook)
        self.notebook.add(search_frame, text="🔍 Búsqueda")
        
        # Panel de búsqueda
        search_panel = ttk.LabelFrame(search_frame, text="Buscar Archivos", padding=10)
        search_panel.pack(fill=tk.X, padx=10, pady=10)
        
        # Campo de búsqueda
        search_row = ttk.Frame(search_panel)
        search_row.pack(fill=tk.X, pady=5)
        
        ttk.Label(search_row, text="Buscar:").pack(side=tk.LEFT, padx=5)
        self.search_entry = ttk.Entry(search_row, width=40)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.search_entry.bind('<Return>', lambda e: self.search_files())
        
        ttk.Button(search_row, text="🔍 Buscar", 
                  command=self.search_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(search_row, text="🗑️ Limpiar", 
                  command=self.clear_search).pack(side=tk.LEFT, padx=5)
        
        # Opciones de búsqueda
        options_row = ttk.Frame(search_panel)
        options_row.pack(fill=tk.X, pady=5)
        
        self.search_case_sensitive = tk.BooleanVar(value=False)
        self.search_exact_match = tk.BooleanVar(value=False)
        self.search_in_content = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(options_row, text="Mayúsculas/minúsculas", 
                       variable=self.search_case_sensitive).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(options_row, text="Coincidencia exacta", 
                       variable=self.search_exact_match).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(options_row, text="Buscar en contenido", 
                       variable=self.search_in_content).pack(side=tk.LEFT, padx=5)
        
        # Filtros
        filter_row = ttk.Frame(search_panel)
        filter_row.pack(fill=tk.X, pady=5)
        
        ttk.Label(filter_row, text="Tipo:").pack(side=tk.LEFT, padx=5)
        self.search_type = ttk.Combobox(filter_row, width=15, 
                                        values=["Todos", "Carpetas", "Archivos", 
                                               ".txt", ".pdf", ".doc", ".xls", 
                                               ".jpg", ".png", ".zip"])
        self.search_type.set("Todos")
        self.search_type.pack(side=tk.LEFT, padx=5)
        
        # Resultados
        results_frame = ttk.LabelFrame(search_frame, text="Resultados", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        columns = ('Nombre', 'Ruta', 'Tamaño', 'Modificado')
        self.search_tree = ttk.Treeview(results_frame, columns=columns, show='headings')
        
        self.search_tree.heading('Nombre', text='Nombre')
        self.search_tree.heading('Ruta', text='Ruta')
        self.search_tree.heading('Tamaño', text='Tamaño')
        self.search_tree.heading('Modificado', text='Modificado')
        
        self.search_tree.column('Nombre', width=200)
        self.search_tree.column('Ruta', width=400)
        self.search_tree.column('Tamaño', width=100)
        self.search_tree.column('Modificado', width=150)
        
        search_scroll = ttk.Scrollbar(results_frame, command=self.search_tree.yview)
        self.search_tree.configure(yscrollcommand=search_scroll.set)
        
        self.search_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        search_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Doble clic para abrir
        self.search_tree.bind('<Double-1>', self.open_search_result)
        
        # Etiqueta de resultados
        self.search_status = ttk.Label(results_frame, text="")
        self.search_status.pack(pady=5)
    
    def create_backup_tab(self):
        """Crea la pestaña de backups"""
        backup_frame = ttk.Frame(self.notebook)
        self.notebook.add(backup_frame, text="💾 Backups")
        
        # Panel de control
        control_frame = ttk.LabelFrame(backup_frame, text="Control de Backups", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Checkbutton(control_frame, text="Backup Automático (cada hora)", 
                       variable=self.auto_backup,
                       command=self.toggle_auto_backup).pack(anchor=tk.W)
        
        ttk.Label(control_frame, text=f"Carpeta de backup: {self.ruta_backup}").pack(anchor=tk.W, pady=5)
        
        button_row = ttk.Frame(control_frame)
        button_row.pack(fill=tk.X, pady=5)
        
        ttk.Button(button_row, text="💾 Crear Backup Ahora", 
                  command=self.create_backup).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_row, text="♻️ Restaurar Backup", 
                  command=self.restore_backup).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_row, text="📂 Abrir Carpeta Backup", 
                  command=lambda: self.open_folder(self.ruta_backup)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_row, text="🗑️ Eliminar Backup", 
                  command=self.delete_backup).pack(side=tk.LEFT, padx=5)
        
        # Lista de backups
        list_frame = ttk.LabelFrame(backup_frame, text="Backups Disponibles", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        columns = ('Fecha', 'Tamaño', 'Archivos')
        self.backup_tree = ttk.Treeview(list_frame, columns=columns, show='headings')
        
        self.backup_tree.heading('Fecha', text='Fecha y Hora')
        self.backup_tree.heading('Tamaño', text='Tamaño Total')
        self.backup_tree.heading('Archivos', text='N° Archivos')
        
        self.backup_tree.column('Fecha', width=200)
        self.backup_tree.column('Tamaño', width=150)
        self.backup_tree.column('Archivos', width=150)
        
        backup_scroll = ttk.Scrollbar(list_frame, command=self.backup_tree.yview)
        self.backup_tree.configure(yscrollcommand=backup_scroll.set)
        
        self.backup_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        backup_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Refrescar lista de backups
        self.refresh_backups()
    
    def create_sync_tab(self):
        """Crea la pestaña de sincronización offline"""
        sync_frame = ttk.Frame(self.notebook)
        self.notebook.add(sync_frame, text="🔄 Sincronización")
        
        # Panel de control
        control_frame = ttk.LabelFrame(sync_frame, text="Sincronización Offline", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        info_text = """La sincronización offline permite trabajar sin conexión a la red.
Los cambios se guardan localmente y se sincronizan cuando la red esté disponible."""
        
        ttk.Label(control_frame, text=info_text, wraplength=800).pack(pady=5)
        
        check_frame = ttk.Frame(control_frame)
        check_frame.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(check_frame, text="Activar Sincronización Automática", 
                       variable=self.sync_active,
                       command=self.toggle_sync).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(check_frame, text="Notificaciones Activadas", 
                       variable=self.notifications_enabled,
                       command=self.toggle_notifications).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(control_frame, text=f"Cache local: {self.ruta_sync_cache}").pack(anchor=tk.W)
        
        button_row = ttk.Frame(control_frame)
        button_row.pack(fill=tk.X, pady=10)
        
        ttk.Button(button_row, text="⬇️ Descargar Todo (Offline)", 
                  command=self.download_for_offline).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_row, text="⬆️ Sincronizar Cambios", 
                  command=self.sync_changes).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_row, text="🗑️ Limpiar Cache", 
                  command=self.clear_cache).pack(side=tk.LEFT, padx=5)
        
        # Archivos vigilados
        watched_frame = ttk.LabelFrame(sync_frame, text="Archivos con Notificación", padding=10)
        watched_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.watched_listbox = tk.Listbox(watched_frame, height=5)
        self.watched_listbox.pack(fill=tk.X, pady=5)
        
        ttk.Button(watched_frame, text="Eliminar de vigilancia", 
                  command=self.unwatch_file).pack()
        
        self.refresh_watched_files()
        
        # Log de sincronización
        log_frame = ttk.LabelFrame(sync_frame, text="Log de Sincronización", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.sync_log = tk.Text(log_frame, height=10, wrap=tk.WORD)
        log_scroll = ttk.Scrollbar(log_frame, command=self.sync_log.yview)
        self.sync_log.configure(yscrollcommand=log_scroll.set)
        
        self.sync_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log("Sistema de sincronización iniciado")
    
    def create_compression_tab(self):
        """Crea la pestaña de compresión"""
        compress_frame = ttk.Frame(self.notebook)
        self.notebook.add(compress_frame, text="🗜️ Compresión")
        
        # Panel de compresión
        compress_panel = ttk.LabelFrame(compress_frame, text="Comprimir Archivos", padding=10)
        compress_panel.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(compress_panel, 
                 text="Selecciona archivos/carpetas del explorador y luego usa esta pestaña").pack(pady=5)
        
        format_frame = ttk.Frame(compress_panel)
        format_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(format_frame, text="Formato:").pack(side=tk.LEFT, padx=5)
        self.compress_format = ttk.Combobox(format_frame, width=15, 
                                           values=["zip", "tar.gz", "tar.bz2"],
                                           state="readonly")
        self.compress_format.set("zip")
        self.compress_format.pack(side=tk.LEFT, padx=5)
        
        button_row = ttk.Frame(compress_panel)
        button_row.pack(fill=tk.X, pady=5)
        
        ttk.Button(button_row, text="📦 Comprimir Selección", 
                  command=self.compress_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_row, text="📂 Comprimir Carpeta Completa", 
                  command=self.compress_folder).pack(side=tk.LEFT, padx=5)
        
        # Panel de descompresión
        decompress_panel = ttk.LabelFrame(compress_frame, text="Descomprimir Archivos", padding=10)
        decompress_panel.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(decompress_panel, 
                 text="Selecciona un archivo comprimido del explorador").pack(pady=5)
        
        ttk.Button(decompress_panel, text="📂 Descomprimir Selección", 
                  command=self.decompress_selected).pack(pady=5)
        
        ttk.Button(decompress_panel, text="📂 Descomprimir Archivo...", 
                  command=self.decompress_file).pack(pady=5)
        
        # Lista de archivos comprimidos
        list_frame = ttk.LabelFrame(compress_frame, text="Archivos Comprimidos Disponibles", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        columns = ('Nombre', 'Tamaño', 'Ruta')
        self.compress_tree = ttk.Treeview(list_frame, columns=columns, show='headings')
        
        self.compress_tree.heading('Nombre', text='Nombre')
        self.compress_tree.heading('Tamaño', text='Tamaño')
        self.compress_tree.heading('Ruta', text='Ruta')
        
        self.compress_tree.column('Nombre', width=200)
        self.compress_tree.column('Tamaño', width=100)
        self.compress_tree.column('Ruta', width=400)
        
        compress_scroll = ttk.Scrollbar(list_frame, command=self.compress_tree.yview)
        self.compress_tree.configure(yscrollcommand=compress_scroll.set)
        
        self.compress_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        compress_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Doble clic para descomprimir
        self.compress_tree.bind('<Double-1>', lambda e: self.decompress_selected())
        
        # Refrescar lista
        ttk.Button(compress_frame, text="🔄 Actualizar Lista", 
                  command=self.refresh_compressed_files).pack(pady=5)
        
        self.refresh_compressed_files()
    
    def populate_folder_tree(self):
        """Pobla el árbol de carpetas"""
        for item in self.folder_tree.get_children():
            self.folder_tree.delete(item)
        
        try:
            if os.path.exists(self.ruta_oficina):
                root_node = self.folder_tree.insert('', 'end', text=os.path.basename(self.ruta_oficina), 
                                                    values=[self.ruta_oficina])
                self.add_folder_children(root_node, self.ruta_oficina)
        except Exception as e:
            print(f"Error poblando árbol: {e}")
    
    def add_folder_children(self, parent, path, level=0):
        """Añade carpetas hijas al árbol"""
        if level > 3:  # Limitar profundidad
            return
        
        try:
            items = sorted([d for d in os.listdir(path) 
                          if os.path.isdir(os.path.join(path, d))])
            
            for item in items:
                item_path = os.path.join(path, item)
                node = self.folder_tree.insert(parent, 'end', text=item, values=[item_path])
                # Añadir placeholder para carpetas con subcarpetas
                try:
                    if any(os.path.isdir(os.path.join(item_path, f)) for f in os.listdir(item_path)):
                        self.folder_tree.insert(node, 'end', text='...')
                except:
                    pass
        except Exception as e:
            print(f"Error añadiendo hijos: {e}")
    
    def on_folder_select(self, event):
        """Maneja selección en árbol de carpetas"""
        selection = self.folder_tree.selection()
        if selection:
            item = self.folder_tree.item(selection[0])
            if item['values']:
                self.current_path = item['values'][0]
                self.refresh_files()
    
    def navigate_to_path(self):
        """Navega a la ruta especificada"""
        path = self.path_entry.get()
        if os.path.exists(path):
            self.current_path = path
            self.refresh_files()
        else:
            messagebox.showerror("Error", "La ruta no existe")
    
    def refresh_files(self):
        """Actualiza la vista de archivos"""
        try:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, self.current_path)
            
            # Limpiar árboles
            for item in self.file_tree.get_children():
                self.file_tree.delete(item)
            
            if not os.path.exists(self.current_path):
                messagebox.showerror("Error", f"La ruta no existe: {self.current_path}")
                return
            
            # Listar archivos y carpetas
            items = sorted(os.listdir(self.current_path))
            
            for item in items:
                ruta_completa = os.path.join(self.current_path, item)
                
                try:
                    if os.path.isdir(ruta_completa):
                        # Es carpeta
                        self.file_tree.insert('', tk.END, text='📁', 
                                            values=(item, '', 'Carpeta', ''))
                    else:
                        # Es archivo
                        tamaño = os.path.getsize(ruta_completa)
                        modificado = datetime.fromtimestamp(
                            os.path.getmtime(ruta_completa)
                        ).strftime('%Y-%m-%d %H:%M')
                        tipo = os.path.splitext(item)[1] or 'Archivo'
                        
                        self.file_tree.insert('', tk.END, text='📄',
                                            values=(item, self.format_size(tamaño), 
                                                   tipo, modificado))
                except Exception as e:
                    print(f"Error con {item}: {e}")
            
            self.status_bar.config(text=f"Mostrando {len(items)} elementos")
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar archivos: {e}")
    
    def format_size(self, size):
        """Formatea el tamaño del archivo"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
    
    # FUNCIONES DE BÚSQUEDA
    
    def search_files(self):
        """Busca archivos según criterios"""
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning("Advertencia", "Ingresa un término de búsqueda")
            return
        
        def do_search():
            self.search_results = []
            
            # Limpiar resultados anteriores
            for item in self.search_tree.get_children():
                self.search_tree.delete(item)
            
            self.search_status.config(text="Buscando...")
            self.root.update()
            
            # Configurar búsqueda
            if not self.search_case_sensitive.get():
                query_lower = query.lower()
            
            file_type = self.search_type.get()
            count = 0
            
            try:
                for root, dirs, files in os.walk(self.ruta_oficina):
                    # Buscar en carpetas
                    if file_type in ["Todos", "Carpetas"]:
                        for d in dirs:
                            if self.matches_search(d, query):
                                dir_path = os.path.join(root, d)
                                self.search_tree.insert('', tk.END, 
                                    values=(d, dir_path, 'Carpeta', ''))
                                count += 1
                    
                    # Buscar en archivos
                    if file_type != "Carpetas":
                        for f in files:
                            # Filtrar por tipo
                            if file_type != "Todos" and not f.endswith(file_type):
                                continue
                            
                            if self.matches_search(f, query):
                                file_path = os.path.join(root, f)
                                try:
                                    tamaño = os.path.getsize(file_path)
                                    modificado = datetime.fromtimestamp(
                                        os.path.getmtime(file_path)
                                    ).strftime('%Y-%m-%d %H:%M')
                                    
                                    self.search_tree.insert('', tk.END, 
                                        values=(f, file_path, self.format_size(tamaño), modificado))
                                    count += 1
                                except:
                                    pass
                            
                            # Buscar en contenido si está activado
                            elif self.search_in_content.get():
                                if self.search_in_file_content(os.path.join(root, f), query):
                                    file_path = os.path.join(root, f)
                                    try:
                                        tamaño = os.path.getsize(file_path)
                                        modificado = datetime.fromtimestamp(
                                            os.path.getmtime(file_path)
                                        ).strftime('%Y-%m-%d %H:%M')
                                        
                                        self.search_tree.insert('', tk.END, 
                                            values=(f"📝 {f}", file_path, self.format_size(tamaño), modificado))
                                        count += 1
                                    except:
                                        pass
                
                self.search_status.config(text=f"Se encontraron {count} resultados")
            except Exception as e:
                messagebox.showerror("Error", f"Error en búsqueda: {e}")
                self.search_status.config(text="Error en búsqueda")
        
        threading.Thread(target=do_search, daemon=True).start()
    
    def matches_search(self, filename, query):
        """Verifica si el nombre coincide con la búsqueda"""
        if self.search_case_sensitive.get():
            text = filename
            search_term = query
        else:
            text = filename.lower()
            search_term = query.lower()
        
        if self.search_exact_match.get():
            return text == search_term
        else:
            return search_term in text
    
    def search_in_file_content(self, filepath, query):
        """Busca en el contenido del archivo (solo archivos de texto)"""
        try:
            # Solo buscar en archivos de texto pequeños (< 1MB)
            if os.path.getsize(filepath) > 1024 * 1024:
                return False
            
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                if self.search_case_sensitive.get():
                    return query in content
                else:
                    return query.lower() in content.lower()
        except:
            return False
    
    def clear_search(self):
        """Limpia la búsqueda"""
        self.search_entry.delete(0, tk.END)
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)
        self.search_status.config(text="")
    
    def open_search_result(self, event):
        """Abre el resultado de búsqueda seleccionado"""
        selection = self.search_tree.selection()
        if not selection:
            return
        
        item = self.search_tree.item(selection[0])
        filepath = item['values'][1]
        
        if os.path.isdir(filepath):
            self.current_path = filepath
            self.notebook.select(0)  # Cambiar a pestaña explorador
            self.refresh_files()
        else:
            try:
                if self.sistema == "Linux":
                    os.system(f'xdg-open "{filepath}"')
                else:
                    os.startfile(filepath)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo abrir: {e}")
    
    # FUNCIONES DE COMPRESIÓN
    
    def compress_selected(self):
        """Comprime los archivos seleccionados"""
        selection = self.file_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Selecciona archivos/carpetas")
            return
        
        # Obtener archivos seleccionados
        files = []
        for s in selection:
            item = self.file_tree.item(s)
            nombre = item['values'][0]
            files.append(os.path.join(self.current_path, nombre))
        
        # Pedir nombre del archivo
        default_name = f"archivo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        compress_name = simpledialog.askstring("Comprimir", 
            "Nombre del archivo comprimido:", initialvalue=default_name)
        
        if not compress_name:
            return
        
        fmt = self.compress_format.get()
        
        def do_compress():
            try:
                self.status_bar.config(text="Comprimiendo...")
                self.root.update()
                
                if fmt == "zip":
                    output_file = os.path.join(self.current_path, f"{compress_name}.zip")
                    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for file in files:
                            if os.path.isdir(file):
                                for root, dirs, filenames in os.walk(file):
                                    for filename in filenames:
                                        filepath = os.path.join(root, filename)
                                        arcname = os.path.relpath(filepath, self.current_path)
                                        zipf.write(filepath, arcname)
                            else:
                                zipf.write(file, os.path.basename(file))
                
                elif fmt in ["tar.gz", "tar.bz2"]:
                    mode = 'w:gz' if fmt == "tar.gz" else 'w:bz2'
                    output_file = os.path.join(self.current_path, f"{compress_name}.{fmt}")
                    with tarfile.open(output_file, mode) as tarf:
                        for file in files:
                            tarf.add(file, arcname=os.path.basename(file))
                
                self.status_bar.config(text="Compresión completada")
                self.log(f"Archivo comprimido: {output_file}")
                self.refresh_files()
                self.refresh_compressed_files()
                messagebox.showinfo("Éxito", f"Archivo creado:\n{output_file}")
            except Exception as e:
                messagebox.showerror("Error", f"Error al comprimir: {e}")
                self.status_bar.config(text="Error en compresión")
        
        threading.Thread(target=do_compress, daemon=True).start()
    
    def compress_folder(self):
        """Comprime toda la carpeta actual"""
        if not messagebox.askyesno("Confirmar", 
                                   "¿Comprimir toda la carpeta actual?"):
            return
        
        folder_name = os.path.basename(self.current_path)
        compress_name = simpledialog.askstring("Comprimir Carpeta", 
            "Nombre del archivo:", initialvalue=f"{folder_name}_backup")
        
        if not compress_name:
            return
        
        fmt = self.compress_format.get()
        
        def do_compress():
            try:
                self.status_bar.config(text="Comprimiendo carpeta completa...")
                self.root.update()
                
                if fmt == "zip":
                    output_file = os.path.join(os.path.dirname(self.current_path), 
                                              f"{compress_name}.zip")
                    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(self.current_path):
                            for file in files:
                                filepath = os.path.join(root, file)
                                arcname = os.path.relpath(filepath, 
                                                         os.path.dirname(self.current_path))
                                zipf.write(filepath, arcname)
                
                elif fmt in ["tar.gz", "tar.bz2"]:
                    mode = 'w:gz' if fmt == "tar.gz" else 'w:bz2'
                    output_file = os.path.join(os.path.dirname(self.current_path), 
                                              f"{compress_name}.{fmt}")
                    with tarfile.open(output_file, mode) as tarf:
                        tarf.add(self.current_path, arcname=folder_name)
                
                self.status_bar.config(text="Compresión completada")
                self.log(f"Carpeta comprimida: {output_file}")
                self.refresh_compressed_files()
                messagebox.showinfo("Éxito", f"Carpeta comprimida:\n{output_file}")
            except Exception as e:
                messagebox.showerror("Error", f"Error al comprimir: {e}")
                self.status_bar.config(text="Error en compresión")
        
        threading.Thread(target=do_compress, daemon=True).start()
    
    def decompress_selected(self):
        """Descomprime el archivo seleccionado del explorador"""
        selection = self.file_tree.selection()
        if not selection:
            # Intentar desde la lista de comprimidos
            selection = self.compress_tree.selection()
            if not selection:
                messagebox.showwarning("Advertencia", "Selecciona un archivo comprimido")
                return
            
            item = self.compress_tree.item(selection[0])
            filepath = item['values'][2]
        else:
            item = self.file_tree.item(selection[0])
            nombre = item['values'][0]
            filepath = os.path.join(self.current_path, nombre)
        
        if not (filepath.endswith('.zip') or filepath.endswith('.tar.gz') or 
                filepath.endswith('.tar.bz2')):
            messagebox.showwarning("Advertencia", "Selecciona un archivo comprimido válido")
            return
        
        # Pedir carpeta de destino
        dest_folder = filedialog.askdirectory(initialdir=self.current_path,
                                             title="Selecciona carpeta de destino")
        if not dest_folder:
            dest_folder = self.current_path
        
        self.decompress_file_to(filepath, dest_folder)
    
    def decompress_file(self):
        """Selecciona y descomprime un archivo"""
        filepath = filedialog.askopenfilename(
            title="Seleccionar archivo comprimido",
            filetypes=[("Archivos comprimidos", "*.zip *.tar.gz *.tar.bz2"),
                      ("Todos los archivos", "*.*")])
        
        if not filepath:
            return
        
        dest_folder = filedialog.askdirectory(initialdir=self.current_path,
                                             title="Selecciona carpeta de destino")
        if not dest_folder:
            dest_folder = self.current_path
        
        self.decompress_file_to(filepath, dest_folder)
    
    def decompress_file_to(self, filepath, dest_folder):
        """Descomprime un archivo a la carpeta destino"""
        def do_decompress():
            try:
                self.status_bar.config(text="Descomprimiendo...")
                self.root.update()
                
                if filepath.endswith('.zip'):
                    with zipfile.ZipFile(filepath, 'r') as zipf:
                        zipf.extractall(dest_folder)
                
                elif filepath.endswith('.tar.gz') or filepath.endswith('.tar.bz2'):
                    with tarfile.open(filepath, 'r:*') as tarf:
                        tarf.extractall(dest_folder)
                
                self.status_bar.config(text="Descompresión completada")
                self.log(f"Archivo descomprimido: {os.path.basename(filepath)}")
                self.refresh_files()
                messagebox.showinfo("Éxito", f"Archivo descomprimido en:\n{dest_folder}")
            except Exception as e:
                messagebox.showerror("Error", f"Error al descomprimir: {e}")
                self.status_bar.config(text="Error en descompresión")
        
        threading.Thread(target=do_decompress, daemon=True).start()
    
    def refresh_compressed_files(self):
        """Actualiza la lista de archivos comprimidos"""
        for item in self.compress_tree.get_children():
            self.compress_tree.delete(item)
        
        try:
            for root, dirs, files in os.walk(self.ruta_oficina):
                for f in files:
                    if f.endswith(('.zip', '.tar.gz', '.tar.bz2')):
                        filepath = os.path.join(root, f)
                        try:
                            tamaño = os.path.getsize(filepath)
                            self.compress_tree.insert('', tk.END, 
                                values=(f, self.format_size(tamaño), filepath))
                        except:
                            pass
        except Exception as e:
            print(f"Error listando archivos comprimidos: {e}")
    
    # FUNCIONES DE NOTIFICACIONES
    
    def send_notification(self, title, message):
        """Envía una notificación del sistema"""
        if not self.notifications_enabled.get():
            return
        
        try:
            if self.sistema == "Linux":
                subprocess.run(['notify-send', title, message])
            elif self.sistema == "Windows":
                try:
                    toast.show_toast(title, message, duration=5, threaded=True)
                except:
                    pass
        except Exception as e:
            print(f"Error enviando notificación: {e}")
    
    def watch_file(self):
        """Añade el archivo seleccionado a vigilancia"""
        selection = self.file_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Selecciona un archivo")
            return
        
        item = self.file_tree.item(selection[0])
        nombre = item['values'][0]
        filepath = os.path.join(self.current_path, nombre)
        
        if os.path.isdir(filepath):
            messagebox.showwarning("Advertencia", "Solo se pueden vigilar archivos, no carpetas")
            return
        
        self.watched_files.add(filepath)
        self.save_config()
        self.refresh_watched_files()
        self.log(f"Vigilando cambios en: {nombre}")
        messagebox.showinfo("Éxito", f"Se vigilarán los cambios en:\n{nombre}")
    
    def unwatch_file(self):
        """Elimina archivo de vigilancia"""
        selection = self.watched_listbox.curselection()
        if not selection:
            return
        
        filepath = self.watched_listbox.get(selection[0])
        if filepath in self.watched_files:
            self.watched_files.remove(filepath)
            self.save_config()
            self.refresh_watched_files()
            self.log(f"Dejó de vigilar: {os.path.basename(filepath)}")
    
    def refresh_watched_files(self):
        """Actualiza la lista de archivos vigilados"""
        self.watched_listbox.delete(0, tk.END)
        for filepath in self.watched_files:
            self.watched_listbox.insert(tk.END, filepath)
    
    def start_notification_monitor(self):
        """Inicia el monitor de notificaciones"""
        def monitor():
            last_checks = {}
            
            while True:
                if self.notifications_enabled.get():
                    for filepath in list(self.watched_files):
                        try:
                            if not os.path.exists(filepath):
                                continue
                            
                            current_mtime = os.path.getmtime(filepath)
                            
                            if filepath in last_checks:
                                if current_mtime > last_checks[filepath]:
                                    # Archivo modificado
                                    filename = os.path.basename(filepath)
                                    self.send_notification(
                                        "Archivo Modificado",
                                        f"{filename} ha sido modificado"
                                    )
                                    self.log(f"🔔 Notificación: {filename} modificado")
                            
                            last_checks[filepath] = current_mtime
                        except Exception as e:
                            print(f"Error monitoreando {filepath}: {e}")
                
                time.sleep(10)  # Verificar cada 10 segundos
        
        threading.Thread(target=monitor, daemon=True).start()
    
    def toggle_notifications(self):
        """Activa/desactiva notificaciones"""
        if self.notifications_enabled.get():
            self.notif_indicator.config(text="🔔 ON", foreground='green')
            self.log("Notificaciones activadas")
        else:
            self.notif_indicator.config(text="🔔 OFF", foreground='black')
            self.log("Notificaciones desactivadas")
    
    # FUNCIONES AUXILIARES DEL EXPLORADOR
    
    def on_file_double_click(self, event):
        """Maneja doble clic en archivo/carpeta"""
        selection = self.file_tree.selection()
        if not selection:
            return
        
        item = self.file_tree.item(selection[0])
        nombre = item['values'][0]
        ruta = os.path.join(self.current_path, nombre)
        
        if os.path.isdir(ruta):
            self.current_path = ruta
            self.refresh_files()
        else:
            self.open_file()
    
    def go_up(self):
        """Sube un nivel en la jerarquía"""
        parent = os.path.dirname(self.current_path)
        if parent and parent != self.current_path:
            self.current_path = parent
            self.refresh_files()
    
    def go_home(self):
        """Vuelve a la carpeta raíz"""
        self.current_path = self.ruta_oficina
        self.refresh_files()
    
    def show_context_menu(self, event):
        """Muestra menú contextual"""
        self.context_menu.post(event.x_root, event.y_root)
    
    def open_file(self):
        """Abre archivo con aplicación predeterminada"""
        selection = self.file_tree.selection()
        if not selection:
            return
        
        item = self.file_tree.item(selection[0])
        nombre = item['values'][0]
        ruta = os.path.join(self.current_path, nombre)
        
        try:
            if self.sistema == "Linux":
                os.system(f'xdg-open "{ruta}"')
            else:
                os.startfile(ruta)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el archivo: {e}")
    
    def copy_file(self):
        """Copia archivo seleccionado"""
        selection = self.file_tree.selection()
        if not selection:
            return
        
        item = self.file_tree.item(selection[0])
        nombre = item['values'][0]
        origen = os.path.join(self.current_path, nombre)
        
        destino = filedialog.asksaveasfilename(initialfile=nombre)
        if destino:
            try:
                if os.path.isdir(origen):
                    shutil.copytree(origen, destino)
                else:
                    shutil.copy2(origen, destino)
                messagebox.showinfo("Éxito", "Archivo copiado correctamente")
            except Exception as e:
                messagebox.showerror("Error", f"Error al copiar: {e}")
    
    def delete_file(self):
        """Elimina archivo seleccionado"""
        selection = self.file_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Selecciona un archivo")
            return
        
        items = [self.file_tree.item(s)['values'][0] for s in selection]
        
        if not messagebox.askyesno("Confirmar", 
                                   f"¿Eliminar {len(items)} elemento(s)?"):
            return
        
        for nombre in items:
            try:
                ruta = os.path.join(self.current_path, nombre)
                if os.path.isdir(ruta):
                    shutil.rmtree(ruta)
                else:
                    os.remove(ruta)
            except Exception as e:
                messagebox.showerror("Error", f"Error al eliminar {nombre}: {e}")
        
        self.refresh_files()
        messagebox.showinfo("Éxito", f"{len(items)} elemento(s) eliminado(s)")
    
    def new_folder(self):
        """Crea nueva carpeta"""
        nombre = simpledialog.askstring("Nueva Carpeta", "Nombre de la carpeta:")
        if nombre:
            try:
                ruta = os.path.join(self.current_path, nombre)
                os.makedirs(ruta)
                self.refresh_files()
            except Exception as e:
                messagebox.showerror("Error", f"Error al crear carpeta: {e}")
    
    def new_file(self):
        """Crea nuevo archivo"""
        nombre = simpledialog.askstring("Nuevo Archivo", "Nombre del archivo:")
        if nombre:
            try:
                ruta = os.path.join(self.current_path, nombre)
                open(ruta, 'w').close()
                self.refresh_files()
            except Exception as e:
                messagebox.showerror("Error", f"Error al crear archivo: {e}")
    
    def upload_file(self):
        """Sube archivo a la carpeta actual"""
        archivos = filedialog.askopenfilenames()
        if archivos:
            for archivo in archivos:
                try:
                    nombre = os.path.basename(archivo)
                    destino = os.path.join(self.current_path, nombre)
                    shutil.copy2(archivo, destino)
                except Exception as e:
                    messagebox.showerror("Error", f"Error al subir {nombre}: {e}")
            self.refresh_files()
            messagebox.showinfo("Éxito", f"{len(archivos)} archivo(s) subido(s)")
    
    def show_properties(self):
        """Muestra propiedades del archivo"""
        selection = self.file_tree.selection()
        if not selection:
            return
        
        item = self.file_tree.item(selection[0])
        nombre = item['values'][0]
        ruta = os.path.join(self.current_path, nombre)
        
        try:
            stats = os.stat(ruta)
            info = f"""Nombre: {nombre}
Ruta: {ruta}
Tamaño: {self.format_size(stats.st_size)}
Creado: {datetime.fromtimestamp(stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')}
Modificado: {datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}
Tipo: {'Carpeta' if os.path.isdir(ruta) else 'Archivo'}"""
            
            messagebox.showinfo("Propiedades", info)
        except Exception as e:
            messagebox.showerror("Error", f"Error al obtener propiedades: {e}")
    
    def open_folder(self, path):
        """Abre carpeta en explorador del sistema"""
        try:
            if self.sistema == "Linux":
                os.system(f'xdg-open "{path}"')
            else:
                os.startfile(path)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la carpeta: {e}")
    
    # FUNCIONES DE BACKUP
    
    def create_backup(self):
        """Crea un backup completo"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(self.ruta_backup, f"backup_{timestamp}")
        
        def do_backup():
            try:
                self.status_bar.config(text="Creando backup...")
                self.root.update()
                
                shutil.copytree(self.ruta_oficina, backup_dir)
                
                self.status_bar.config(text="Backup completado")
                self.log(f"Backup creado: {timestamp}")
                self.refresh_backups()
                self.send_notification("Backup Completado", 
                                      f"Backup creado exitosamente")
                messagebox.showinfo("Éxito", f"Backup creado en:\n{backup_dir}")
            except Exception as e:
                messagebox.showerror("Error", f"Error al crear backup: {e}")
                self.status_bar.config(text="Error en backup")
        
        threading.Thread(target=do_backup, daemon=True).start()
    
    def restore_backup(self):
        """Restaura un backup seleccionado"""
        selection = self.backup_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Selecciona un backup")
            return
        
        item = self.backup_tree.item(selection[0])
        fecha = item['values'][0]
        
        # Buscar el directorio de backup correspondiente
        backup_dirs = [d for d in os.listdir(self.ruta_backup) 
                      if d.startswith('backup_')]
        
        if not backup_dirs:
            messagebox.showerror("Error", "No se encontró el backup")
            return
        
        # Usar el primero que coincida (debería haber solo uno por timestamp)
        backup_dir = os.path.join(self.ruta_backup, sorted(backup_dirs, reverse=True)[0])
        
        if not messagebox.askyesno("Confirmar", 
                                   "¿Restaurar este backup?\n"
                                   "Esto reemplazará los archivos actuales."):
            return
        
        def do_restore():
            try:
                self.status_bar.config(text="Restaurando backup...")
                self.root.update()
                
                # Eliminar contenido actual
                for item in os.listdir(self.ruta_oficina):
                    ruta = os.path.join(self.ruta_oficina, item)
                    if os.path.isdir(ruta):
                        shutil.rmtree(ruta)
                    else:
                        os.remove(ruta)
                
                # Copiar backup
                for item in os.listdir(backup_dir):
                    origen = os.path.join(backup_dir, item)
                    destino = os.path.join(self.ruta_oficina, item)
                    if os.path.isdir(origen):
                        shutil.copytree(origen, destino)
                    else:
                        shutil.copy2(origen, destino)
                
                self.status_bar.config(text="Backup restaurado")
                self.log(f"Backup restaurado: {fecha}")
                self.refresh_files()
                self.send_notification("Backup Restaurado", 
                                      "Los archivos han sido restaurados")
                messagebox.showinfo("Éxito", "Backup restaurado correctamente")
            except Exception as e:
                messagebox.showerror("Error", f"Error al restaurar: {e}")
                self.status_bar.config(text="Error en restauración")
        
        threading.Thread(target=do_restore, daemon=True).start()
    
    def delete_backup(self):
        """Elimina un backup seleccionado"""
        selection = self.backup_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Selecciona un backup")
            return
        
        if not messagebox.askyesno("Confirmar", "¿Eliminar este backup?"):
            return
        
        try:
            # Obtener el directorio más reciente (asumiendo que es el seleccionado)
            backup_dirs = sorted([d for d in os.listdir(self.ruta_backup) 
                                if d.startswith('backup_')], reverse=True)
            
            if backup_dirs:
                idx = self.backup_tree.index(selection[0])
                if idx < len(backup_dirs):
                    backup_to_delete = os.path.join(self.ruta_backup, backup_dirs[idx])
                    shutil.rmtree(backup_to_delete)
                    self.log(f"Backup eliminado: {backup_dirs[idx]}")
                    self.refresh_backups()
                    messagebox.showinfo("Éxito", "Backup eliminado")
        except Exception as e:
            messagebox.showerror("Error", f"Error al eliminar backup: {e}")
    
    def refresh_backups(self):
        """Actualiza la lista de backups"""
        for item in self.backup_tree.get_children():
            self.backup_tree.delete(item)
        
        try:
            backups = [d for d in os.listdir(self.ruta_backup) 
                      if d.startswith('backup_') and os.path.isdir(
                          os.path.join(self.ruta_backup, d))]
            
            for backup in sorted(backups, reverse=True):
                backup_path = os.path.join(self.ruta_backup, backup)
                
                # Calcular tamaño total
                total_size = 0
                file_count = 0
                for root, dirs, files in os.walk(backup_path):
                    for f in files:
                        try:
                            total_size += os.path.getsize(os.path.join(root, f))
                            file_count += 1
                        except:
                            pass
                
                # Formatear fecha
                timestamp = backup.replace('backup_', '')
                fecha = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]} {timestamp[9:11]}:{timestamp[11:13]}:{timestamp[13:15]}"
                
                self.backup_tree.insert('', tk.END, 
                                      values=(fecha, self.format_size(total_size), 
                                             file_count))
        except Exception as e:
            print(f"Error al listar backups: {e}")
    
    def toggle_auto_backup(self):
        """Activa/desactiva backup automático"""
        if self.auto_backup.get():
            self.log("Backup automático activado (cada hora)")
            self.send_notification("Backup Automático", 
                                  "Backup automático activado")
            self.schedule_auto_backup()
        else:
            self.log("Backup automático desactivado")
    
    def schedule_auto_backup(self):
        """Programa backups automáticos"""
        if self.auto_backup.get():
            self.create_backup()
            # Programar siguiente backup en 1 hora (3600000 ms)
            self.root.after(3600000, self.schedule_auto_backup)
    
    # FUNCIONES DE SINCRONIZACIÓN
    
    def toggle_sync(self):
        """Activa/desactiva sincronización"""
        if self.sync_active.get():
            self.sync_indicator.config(text="🟢 Sync: ON", foreground='green')
            self.log("Sincronización activada")
            self.send_notification("Sincronización", 
                                  "Sincronización automática activada")
        else:
            self.sync_indicator.config(text="⚫ Sync: OFF", foreground='black')
            self.log("Sincronización desactivada")
    
    def start_sync_monitor(self):
        """Inicia el monitor de sincronización"""
        def monitor():
            while True:
                if self.sync_active.get():
                    try:
                        self.check_and_sync()
                    except Exception as e:
                        print(f"Error en sync monitor: {e}")
                time.sleep(30)  # Verificar cada 30 segundos
        
        threading.Thread(target=monitor, daemon=True).start()
    
    def check_and_sync(self):
        """Verifica y sincroniza cambios"""
        try:
            if not os.path.exists(self.ruta_oficina):
                return
            
            changes = False
            
            for root, dirs, files in os.walk(self.ruta_oficina):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.ruta_oficina)
                    
                    # Calcular hash del archivo
                    try:
                        current_hash = self.get_file_hash(file_path)
                        stored_hash = self.file_hashes.get(rel_path)
                        
                        if current_hash != stored_hash:
                            changes = True
                            self.file_hashes[rel_path] = current_hash
                            self.last_sync[rel_path] = datetime.now().isoformat()
                            
                            # Copiar a cache
                            cache_path = os.path.join(self.ruta_sync_cache, rel_path)
                            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                            shutil.copy2(file_path, cache_path)
                    except:
                        pass
            
            if changes:
                self.save_config()
                self.log("Cambios sincronizados automáticamente")
        except Exception as e:
            print(f"Error en check_and_sync: {e}")
    
    def get_file_hash(self, filepath):
        """Calcula hash MD5 de un archivo"""
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except:
            return None
    
    def download_for_offline(self):
        """Descarga todos los archivos para trabajo offline"""
        def do_download():
            try:
                self.status_bar.config(text="Descargando para offline...")
                self.root.update()
                
                file_count = 0
                
                for root, dirs, files in os.walk(self.ruta_oficina):
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            rel_path = os.path.relpath(file_path, self.ruta_oficina)
                            cache_path = os.path.join(self.ruta_sync_cache, rel_path)
                            
                            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                            shutil.copy2(file_path, cache_path)
                            
                            # Guardar hash
                            self.file_hashes[rel_path] = self.get_file_hash(file_path)
                            file_count += 1
                            
                            self.status_bar.config(
                                text=f"Descargando... {file_count} archivos")
                            self.root.update()
                        except Exception as e:
                            print(f"Error con {file}: {e}")
                
                self.save_config()
                self.status_bar.config(text="Descarga completada")
                self.log(f"{file_count} archivos descargados para offline")
                self.send_notification("Descarga Completa", 
                                      f"{file_count} archivos disponibles offline")
                messagebox.showinfo("Éxito", 
                    f"{file_count} archivos disponibles offline\n"
                    f"Cache: {self.ruta_sync_cache}")
            except Exception as e:
                messagebox.showerror("Error", f"Error al descargar: {e}")
                self.status_bar.config(text="Error en descarga")
        
        threading.Thread(target=do_download, daemon=True).start()
    
    def sync_changes(self):
        """Sincroniza cambios del cache al servidor"""
        def do_sync():
            try:
                self.status_bar.config(text="Sincronizando cambios...")
                self.root.update()
                
                if not os.path.exists(self.ruta_oficina):
                    messagebox.showerror("Error", 
                        "No se puede acceder a la carpeta de oficina.\n"
                        "Verifica la conexión de red.")
                    return
                
                synced = 0
                
                for root, dirs, files in os.walk(self.ruta_sync_cache):
                    for file in files:
                        try:
                            cache_file = os.path.join(root, file)
                            rel_path = os.path.relpath(cache_file, self.ruta_sync_cache)
                            server_file = os.path.join(self.ruta_oficina, rel_path)
                            
                            # Verificar si el archivo cambió en cache
                            cache_hash = self.get_file_hash(cache_file)
                            stored_hash = self.file_hashes.get(rel_path)
                            
                            if cache_hash != stored_hash:
                                # Copiar al servidor
                                os.makedirs(os.path.dirname(server_file), exist_ok=True)
                                shutil.copy2(cache_file, server_file)
                                
                                # Actualizar hash
                                self.file_hashes[rel_path] = cache_hash
                                synced += 1
                                
                                self.status_bar.config(
                                    text=f"Sincronizando... {synced} archivos")
                                self.root.update()
                        except Exception as e:
                            print(f"Error sincronizando {file}: {e}")
                
                self.save_config()
                self.status_bar.config(text="Sincronización completada")
                self.log(f"{synced} archivos sincronizados al servidor")
                self.refresh_files()
                self.send_notification("Sincronización Completa", 
                                      f"{synced} cambios sincronizados")
                messagebox.showinfo("Éxito", f"{synced} cambios sincronizados")
            except Exception as e:
                messagebox.showerror("Error", f"Error al sincronizar: {e}")
                self.status_bar.config(text="Error en sincronización")
        
        threading.Thread(target=do_sync, daemon=True).start()
    
    def clear_cache(self):
        """Limpia el cache de sincronización"""
        if not messagebox.askyesno("Confirmar", 
                                   "¿Limpiar todo el cache offline?\n"
                                   "Perderás los archivos descargados."):
            return
        
        try:
            if os.path.exists(self.ruta_sync_cache):
                shutil.rmtree(self.ruta_sync_cache)
                os.makedirs(self.ruta_sync_cache)
            
            self.file_hashes = {}
            self.last_sync = {}
            self.save_config()
            
            self.log("Cache limpiado")
            messagebox.showinfo("Éxito", "Cache limpiado correctamente")
        except Exception as e:
            messagebox.showerror("Error", f"Error al limpiar cache: {e}")
    
    def log(self, message):
        """Añade mensaje al log de sincronización"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {message}\n"
        
        self.sync_log.insert(tk.END, log_message)
        self.sync_log.see(tk.END)
        
        # Limitar tamaño del log
        if int(self.sync_log.index('end-1c').split('.')[0]) > 1000:
            self.sync_log.delete('1.0', '100.0')

def parse_args():
    """Parsea los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Gestor de Oficina Pro - Gestor de archivos para carpetas de oficina"
    )
    parser.add_argument(
        '--ruta', '-r',
        metavar='RUTA_OFICINA',
        help='Ruta de la carpeta de oficina (ej: /home/usuario/oficina o Z:\\)',
        default=None
    )
    parser.add_argument(
        '--backup', '-b',
        metavar='RUTA_BACKUP',
        help='Ruta de la carpeta de backup (ej: /home/usuario/oficina_backup)',
        default=None
    )
    parser.add_argument(
        '--reset-config',
        action='store_true',
        help='Elimina la configuración guardada y muestra el asistente de primera ejecución'
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Opción para resetear la configuración
    if args.reset_config:
        config_file = os.path.join(os.path.expanduser("~"), ".gestor_oficina.json")
        if os.path.exists(config_file):
            os.remove(config_file)
            print("Configuración eliminada. Se mostrará el asistente de primera ejecución.")

    root = tk.Tk()
    app = GestorOficina(root, ruta_oficina_arg=args.ruta, ruta_backup_arg=args.backup)
    root.mainloop()


if __name__ == "__main__":
    main()