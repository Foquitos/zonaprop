"""Menú visual moderno de la app (Tkinter con tema Dark Slate / Fluent).

Se abre con:
    python zp.py menu
O ejecutando el archivo 'Iniciar Zonaprop.bat' desde el escritorio.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

from zp import cotizacion, urls, zonas

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "salida"

# Paleta Dark Slate Moderna
COLOR_BG = "#0f172a"          # Slate 900
COLOR_CARD = "#1e293b"        # Slate 800
COLOR_CARD_BORDER = "#334155" # Slate 700
COLOR_TEXT = "#f8fafc"        # Slate 50
COLOR_TEXT_MUTED = "#94a3b8"  # Slate 400
COLOR_PRIMARY = "#38bdf8"     # Sky 400
COLOR_PRIMARY_BTN = "#0284c7" # Sky 600
COLOR_SUCCESS_BTN = "#059669" # Emerald 600
COLOR_DANGER_BTN = "#dc2626"  # Red 600
COLOR_LOG_BG = "#090d16"      # Deep Dark
COLOR_LOG_FG = "#e2e8f0"      # Slate 200


def _aplicar_estilo_oscuro(maestro: tk.Tk):
    """Configura los estilos de TTK para lograr una interfaz oscura moderna."""
    style = ttk.Style(maestro)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    maestro.configure(background=COLOR_BG)

    # Frames
    style.configure("TFrame", background=COLOR_BG)
    style.configure("Card.TFrame", background=COLOR_CARD, relief="flat")
    style.configure("TLabelframe", background=COLOR_CARD, foreground=COLOR_PRIMARY,
                    relief="solid", borderwidth=1, bordercolor=COLOR_CARD_BORDER)
    style.configure("TLabelframe.Label", background=COLOR_CARD, foreground=COLOR_PRIMARY,
                    font=("Segoe UI", 10, "bold"))

    # Labels
    style.configure("TLabel", background=COLOR_CARD, foreground=COLOR_TEXT,
                    font=("Segoe UI", 9))
    style.configure("Header.TLabel", background=COLOR_BG, foreground=COLOR_TEXT,
                    font=("Segoe UI", 15, "bold"))
    style.configure("SubHeader.TLabel", background=COLOR_BG, foreground=COLOR_TEXT_MUTED,
                    font=("Segoe UI", 9))
    style.configure("Muted.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT_MUTED,
                    font=("Segoe UI", 8))
    style.configure("Status.TLabel", background=COLOR_CARD, foreground=COLOR_PRIMARY,
                    font=("Segoe UI", 9, "bold"))

    # Botones
    style.configure("TButton", font=("Segoe UI", 9, "bold"), background=COLOR_CARD_BORDER,
                    foreground=COLOR_TEXT, borderwidth=0, padding=6)
    style.map("TButton",
              background=[("active", "#475569"), ("disabled", "#1e293b")],
              foreground=[("disabled", "#64748b")])

    style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), background=COLOR_PRIMARY_BTN,
                    foreground="#ffffff", padding=6)
    style.map("Primary.TButton",
              background=[("active", "#0369a1"), ("disabled", "#1e293b")],
              foreground=[("disabled", "#64748b")])

    style.configure("Success.TButton", font=("Segoe UI", 10, "bold"), background=COLOR_SUCCESS_BTN,
                    foreground="#ffffff", padding=8)
    style.map("Success.TButton",
              background=[("active", "#047857"), ("disabled", "#1e293b")],
              foreground=[("disabled", "#64748b")])

    style.configure("Danger.TButton", font=("Segoe UI", 9, "bold"), background=COLOR_DANGER_BTN,
                    foreground="#ffffff", padding=6)
    style.map("Danger.TButton",
              background=[("active", "#b91c1c"), ("disabled", "#1e293b")],
              foreground=[("disabled", "#64748b")])

    # Checkbuttons
    style.configure("TCheckbutton", background=COLOR_CARD, foreground=COLOR_TEXT,
                    font=("Segoe UI", 9))
    style.map("TCheckbutton",
              background=[("active", COLOR_CARD)],
              foreground=[("active", COLOR_PRIMARY)])

    # Treeview
    style.configure("Treeview",
                    background="#131d31",
                    foreground=COLOR_TEXT,
                    fieldbackground="#131d31",
                    font=("Segoe UI", 9),
                    rowheight=24,
                    borderwidth=0)
    style.map("Treeview",
              background=[("selected", COLOR_PRIMARY_BTN)],
              foreground=[("selected", "#ffffff")])

    # Scrollbars & Progressbar
    style.configure("Horizontal.TProgressbar",
                    background=COLOR_PRIMARY,
                    troughcolor=COLOR_LOG_BG,
                    borderwidth=0)


class Menu(ttk.Frame):
    def __init__(self, maestro: tk.Tk):
        super().__init__(maestro, padding=12)
        self.maestro = maestro
        self.cola: queue.Queue[str] = queue.Queue()
        self.proceso: subprocess.Popen | None = None
        self.ultimo_run: str | None = None

        self.grid(sticky="nsew")
        maestro.columnconfigure(0, weight=1)
        maestro.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=3, minsize=350)
        self.columnconfigure(1, weight=3, minsize=360)
        self.rowconfigure(1, weight=1)   # zonas y filtros
        self.rowconfigure(3, weight=1)   # log

        self._construir_header()
        self._construir_zonas()
        self._construir_filtros()
        self._construir_acciones()
        self._refrescar_arbol()
        self.after(100, self._vaciar_cola)

    def _construir_header(self):
        banner = ttk.Frame(self)
        banner.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        banner.columnconfigure(0, weight=1)

        ttk.Label(banner, text="🏙️ Zonaprop Alquileres · Scraper & Auditor Forense",
                  style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(banner, text="Extracción inteligente de avisos, scoring multi-criterio y diagnóstico para LLM.",
                  style="SubHeader.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

    # ------------------------------------------------------------------ #
    # Zonas
    # ------------------------------------------------------------------ #
    def _construir_zonas(self):
        caja = ttk.LabelFrame(self, text=" 📍 Dónde buscar (CABA & GBA Norte) ", padding=10)
        caja.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        caja.columnconfigure(0, weight=1)
        caja.rowconfigure(1, weight=1)
        caja.rowconfigure(3, minsize=80)

        barra = ttk.Frame(caja)
        barra.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        barra.columnconfigure(1, weight=1)
        ttk.Label(barra, text="Filtrar zona:").grid(row=0, column=0, padx=(0, 6))
        self.filtro = tk.StringVar()
        self.filtro.trace_add("write", lambda *_: self._refrescar_arbol())

        entry_filtro = tk.Entry(barra, textvariable=self.filtro, bg="#131d31", fg=COLOR_TEXT,
                                insertbackground=COLOR_TEXT, relief="flat", highlightthickness=1,
                                highlightbackground=COLOR_CARD_BORDER, highlightcolor=COLOR_PRIMARY)
        entry_filtro.grid(row=0, column=1, sticky="ew")

        self.arbol = ttk.Treeview(caja, selectmode="extended", show="tree", height=15)
        self.arbol.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(caja, orient="vertical", command=self.arbol.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.arbol.configure(yscrollcommand=scroll.set)
        self.arbol.bind("<<TreeviewSelect>>", self._al_elegir_zona)
        self.arbol.tag_configure("grupo", font=("Segoe UI", 9, "bold"), foreground=COLOR_PRIMARY)

        ttk.Label(caja, text="💡 Tip: Podés seleccionar varios barrios con Ctrl + Clic.",
                  style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 2))

        self.detalle = tk.Text(caja, height=4, wrap="word", relief="flat",
                               background="#131d31", foreground=COLOR_TEXT,
                               font=("Segoe UI", 9), highlightthickness=1,
                               highlightbackground=COLOR_CARD_BORDER)
        self.detalle.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._poner_detalle("Elegí una zona o barrio para ver detalles y cobertura.")

    def _refrescar_arbol(self):
        self.arbol.delete(*self.arbol.get_children())
        visibles = {z.slug for z in zonas.buscar(self.filtro.get())}
        for titulo, slugs in zonas.GRUPOS:
            hijos = [s for s in slugs if s in visibles]
            if not hijos:
                continue
            padre = self.arbol.insert("", "end", text=f"📁 {titulo}", open=True, tags=("grupo",))
            for s in hijos:
                z = zonas.TODAS[s]
                icono = "🏢 " if z.nivel == "barrio" else ("📌 " if z.nivel == "subbarrio" else "📍 ")
                self.arbol.insert(padre, "end", iid=s, text=f"{icono}{z.nombre}")

    def _al_elegir_zona(self, _evento=None):
        elegidas = self.zonas_elegidas()
        if not elegidas:
            self._poner_detalle("Elegí una zona para ver qué abarca.")
            return
        if len(elegidas) > 1:
            nombres = ", ".join(zonas.TODAS[s].nombre for s in elegidas)
            self._poner_detalle(
                f"{len(elegidas)} zonas seleccionadas: {nombres}.\n"
                "Se rastreará cada barrio consolidando un ranking regional unificado."
            )
            return
        z = zonas.TODAS[elegidas[0]]
        texto = f"{z.nombre} ({z.nivel.upper()})\nSlug: {z.slug} | Zonaprop H1: «{z.esperado}»"
        if z.nota:
            texto += f"\n\nNota: {z.nota}"
        self._poner_detalle(texto)

    def _poner_detalle(self, texto: str):
        self.detalle.configure(state="normal")
        self.detalle.delete("1.0", "end")
        self.detalle.insert("1.0", texto)
        self.detalle.configure(state="disabled")

    def zonas_elegidas(self) -> list[str]:
        return [i for i in self.arbol.selection() if i in zonas.TODAS]

    # ------------------------------------------------------------------ #
    # Filtros
    # ------------------------------------------------------------------ #
    def _construir_filtros(self):
        caja = ttk.LabelFrame(self, text=" ⚙️ Parámetros de Búsqueda ", padding=10)
        caja.grid(row=1, column=1, sticky="nsew")
        caja.columnconfigure(1, weight=1)
        fila = 0

        # Ambientes
        ttk.Label(caja, text="Ambientes:").grid(row=fila, column=0, sticky="w", pady=3)
        marco_amb = ttk.Frame(caja, style="Card.TFrame")
        marco_amb.grid(row=fila, column=1, sticky="w")
        self.ambientes = {}
        for n in (1, 2, 3, 4):
            v = tk.BooleanVar(value=(n in (2, 3)))
            ttk.Checkbutton(marco_amb, text=f"{n} amb", variable=v).pack(side="left", padx=4)
            self.ambientes[n] = v
        fila += 1

        # Tipos
        ttk.Label(caja, text="Tipo de propiedad:").grid(row=fila, column=0, sticky="w", pady=3)
        marco_tipo = ttk.Frame(caja, style="Card.TFrame")
        marco_tipo.grid(row=fila, column=1, sticky="w")
        self.tipos = {}
        for etiqueta, slug, defecto in (("Depto", "departamentos", True),
                                        ("PH", "ph", True),
                                        ("Casa", "casas", False)):
            v = tk.BooleanVar(value=defecto)
            ttk.Checkbutton(marco_tipo, text=etiqueta, variable=v).pack(side="left", padx=4)
            self.tipos[slug] = v
        fila += 1

        # Campos numéricos
        try:
            # solo_cache: el menú se dibuja al arrancar y no puede quedarse
            # esperando la red. Si hoy todavía no se consultó, muestra el
            # fallback y el valor real se resuelve al correr `rankear`.
            val_dolar, _ = cotizacion.obtener_dolar(solo_cache=True)
            dolar_defecto = str(int(val_dolar))
        except Exception as e:
            print(f"  [menu] Error al obtener cotización del dólar ({e}); usando fallback.")
            dolar_defecto = str(int(cotizacion.DOLAR_FALLBACK))

        self.campos = {}
        for etiqueta, clave, valor, ayuda in (
            ("Presupuesto máx", "presupuesto", "1100000", "alquiler + expensas en ARS"),
            ("Cotización Dólar", "dolar", dolar_defecto, "conversión para avisos en USD"),
            ("Páginas a scrapear", "paginas", "5", "30 propiedades por página"),
            ("Top para Fotos", "top", "20", "candidatos para análisis visual"),
            ("Fotos por aviso", "max_fotos", "16", "preserva fotos de plano y fachada"),
            ("Espera Captcha", "espera_captcha", "240", "segundos para resolver verificación"),
        ):
            ttk.Label(caja, text=f"{etiqueta}:").grid(row=fila, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=valor)
            entry = tk.Entry(caja, textvariable=v, width=14, bg="#131d31", fg=COLOR_TEXT,
                             insertbackground=COLOR_TEXT, relief="flat", highlightthickness=1,
                             highlightbackground=COLOR_CARD_BORDER, highlightcolor=COLOR_PRIMARY)
            entry.grid(row=fila, column=1, sticky="w")
            ttk.Label(caja, text=ayuda, style="Muted.TLabel").grid(row=fila + 1, column=1, sticky="w")
            self.campos[clave] = v
            fila += 2

        self.headless = tk.BooleanVar(value=False)
        ttk.Checkbutton(caja, text="Modo sin ventana (Headless)",
                        variable=self.headless).grid(row=fila, column=0, columnspan=2,
                                                     sticky="w", pady=(6, 0))
        fila += 1
        ttk.Label(caja, text="Recomendado destildado la 1ª vez si aparece verificación Cloudflare.",
                  style="Muted.TLabel").grid(row=fila, column=0, columnspan=2, sticky="w")

    # ------------------------------------------------------------------ #
    # Acciones, Progreso y Log
    # ------------------------------------------------------------------ #
    def _construir_acciones(self):
        caja = ttk.Frame(self)
        caja.grid(row=2, column=1, sticky="nsew", pady=(8, 0))
        caja.columnconfigure(0, weight=1)

        pasos = ttk.LabelFrame(caja, text=" 🚀 Ejecución del Pipeline ", padding=8)
        pasos.grid(row=0, column=0, sticky="ew")
        pasos.columnconfigure((0, 1), weight=1)

        self.botones = {}
        acciones = [
            ("🔍 1 · Buscar", self.paso_buscar),
            ("📊 2 · Rankear", self.paso_rankear),
            ("🖼️ 3 · Fotos", self.paso_fotos),
            ("📄 4 · Dossier", self.paso_dossier),
        ]
        for i, (texto, fn) in enumerate(acciones):
            b = ttk.Button(pasos, text=texto, command=fn, style="TButton")
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=3, pady=2)
            self.botones[texto] = b

        # Botón principal Todo Seguido
        self.btn_todo = ttk.Button(pasos, text="🚀 Correr Todo el Pipeline",
                                   command=self.paso_todo, style="Success.TButton")
        self.btn_todo.grid(row=2, column=0, sticky="ew", padx=3, pady=(6, 2))

        self.boton_frenar = ttk.Button(pasos, text="⏹ Frenar", command=self.frenar,
                                       state="disabled", style="Danger.TButton")
        self.boton_frenar.grid(row=2, column=1, sticky="ew", padx=3, pady=(6, 2))

        # Barra de progreso
        self.progreso = ttk.Progressbar(caja, orient="horizontal", mode="determinate",
                                        style="Horizontal.TProgressbar")
        self.progreso.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self.progreso["value"] = 0

        # Barra de Accesos Rápidos Post-Corrida
        marco_accesos = ttk.LabelFrame(caja, text=" ⚡ Accesos Rápidos de Resultados ", padding=6)
        marco_accesos.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        marco_accesos.columnconfigure((0, 1, 2, 3), weight=1)

        self.btn_dash = ttk.Button(marco_accesos, text="📊 Dashboard Web", command=self.abrir_dashboard)
        self.btn_dash.grid(row=0, column=0, padx=2, pady=2, sticky="ew")

        self.btn_prompt = ttk.Button(marco_accesos, text="🤖 Copiar Prompt LLM", command=self.copiar_prompt_llm)
        self.btn_prompt.grid(row=0, column=1, padx=2, pady=2, sticky="ew")

        self.btn_ficha = ttk.Button(marco_accesos, text="📋 Ficha Visitas", command=self.abrir_ficha_visita)
        self.btn_ficha.grid(row=0, column=2, padx=2, pady=2, sticky="ew")

        self.btn_fotos = ttk.Button(marco_accesos, text="📁 Ver Fotos", command=self.abrir_carpeta_fotos)
        self.btn_fotos.grid(row=0, column=3, padx=2, pady=2, sticky="ew")

        # Estado y comando
        self.estado = tk.StringVar(value="🟢 Listo para buscar.")
        ttk.Label(caja, textvariable=self.estado, style="Status.TLabel").grid(
            row=3, column=0, sticky="w", pady=(4, 0))

        # Log en vivo
        marco_log = ttk.LabelFrame(self, text=" 💻 Consola y Registro en Vivo ", padding=6)
        marco_log.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        marco_log.columnconfigure(0, weight=1)
        marco_log.rowconfigure(0, weight=1)

        self.log = tk.Text(marco_log, height=8, wrap="word", background=COLOR_LOG_BG,
                           foreground=COLOR_LOG_FG, insertbackground=COLOR_LOG_FG,
                           font=("Consolas", 9), relief="flat", highlightthickness=0)
        self.log.grid(row=0, column=0, sticky="nsew")
        sl = ttk.Scrollbar(marco_log, orient="vertical", command=self.log.yview)
        sl.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sl.set, state="disabled")

        self.log.tag_configure("error", foreground="#f87171")
        self.log.tag_configure("ok", foreground="#4ade80")
        self.log.tag_configure("info", foreground=COLOR_PRIMARY)
        self.log.tag_configure("captcha", foreground="#fbbf24", font=("Consolas", 9, "bold"))

    # ------------------------------------------------------------------ #
    # Accesos Rápidos
    # ------------------------------------------------------------------ #
    def _obtener_carpeta_run(self) -> Path | None:
        if self.ultimo_run:
            c = SALIDA / self.ultimo_run
            if c.exists():
                return c
        elegidas = self.zonas_elegidas()
        if elegidas:
            run = self.nombre_run(elegidas[0])
            c = SALIDA / run
            if c.exists():
                return c
        # Última carpeta en salida
        if SALIDA.exists():
            runs = [p for p in SALIDA.iterdir() if p.is_dir()]
            if runs:
                return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        return None

    def abrir_dashboard(self):
        c = self._obtener_carpeta_run()
        if c and (c / "resumen.html").exists():
            webbrowser.open(str(c / "resumen.html"))
        else:
            messagebox.showinfo("Dashboard", "Aún no se generó el resumen.html. Corré el paso '4 · Dossier'.")

    def copiar_prompt_llm(self):
        c = self._obtener_carpeta_run()
        if c and (c / "PROMPT_LLM.md").exists():
            texto = (c / "PROMPT_LLM.md").read_text(encoding="utf-8")
            self.maestro.clipboard_clear()
            self.maestro.clipboard_append(texto)
            messagebox.showinfo("Copiado al Portapapeles",
                                "¡Prompt copiado con éxito!\n\nPegalo directamente en Claude o Gemini "
                                "junto al archivo 'dossier.md' y las hojas de contacto.")
        else:
            messagebox.showinfo("Prompt", "Aún no se generó PROMPT_LLM.md. Corré el paso '4 · Dossier'.")

    def abrir_ficha_visita(self):
        c = self._obtener_carpeta_run()
        if c:
            pdf_path = c / "ficha_visita.pdf"
            html_path = c / "ficha_visita.html"
            md_path = c / "ficha_visita.md"

            archivo_a_abrir = pdf_path if pdf_path.exists() else (html_path if html_path.exists() else md_path)
            if archivo_a_abrir.exists():
                try:
                    os.startfile(str(archivo_a_abrir))
                except Exception:
                    webbrowser.open(str(archivo_a_abrir))
                return

        messagebox.showinfo("Ficha de Visita", "Aún no se generó la ficha de visita. Corré '4 · Dossier'.")

    def abrir_carpeta_fotos(self):
        c = self._obtener_carpeta_run()
        if c and (c / "contactos").exists():
            os.startfile(str(c / "contactos"))
        elif c:
            os.startfile(str(c))
        else:
            messagebox.showinfo("Fotos", "No hay carpetas de salida creadas todavía.")

    # ------------------------------------------------------------------ #
    # Validaciones y comandos
    # ------------------------------------------------------------------ #
    def _ambientes(self) -> list[int]:
        return [n for n, v in self.ambientes.items() if v.get()]

    def _tipos(self) -> list[str]:
        return [t for t, v in self.tipos.items() if v.get()]

    def _numero(self, clave: str, obligatorio: bool = True):
        crudo = self.campos[clave].get().strip().replace(".", "").replace(",", "")
        if not crudo:
            return None if not obligatorio else 0
        try:
            return float(crudo)
        except ValueError:
            raise ValueError(f"'{self.campos[clave].get()}' no es un número válido.")

    def nombre_run(self, zonas_sel: str | list[str]) -> str:
        return urls.nombre_run(zonas_sel, self._ambientes())

    def _extras_navegador(self) -> list[str]:
        extras = ["--espera-captcha", str(int(self._numero("espera_captcha")))]
        if self.headless.get():
            extras.append("--headless")
        return extras

    def _validar(self) -> list[str] | None:
        elegidas = self.zonas_elegidas()
        if not elegidas:
            messagebox.showwarning("Falta la zona", "Elegí al menos una zona en el árbol de la izquierda.")
            return None
        if not self._ambientes():
            messagebox.showwarning("Faltan ambientes", "Seleccioná al menos una cantidad de ambientes.")
            return None
        if not self._tipos():
            messagebox.showwarning("Falta el tipo", "Seleccioná al menos un tipo de propiedad.")
            return None
        return elegidas

    def paso_buscar(self):
        elegidas = self._validar()
        if not elegidas:
            return
        run = self.nombre_run(elegidas)
        self.ultimo_run = run
        presupuesto = int(self._numero("presupuesto")) if self._numero("presupuesto", False) else None
        precio_max_args = ["--precio-max", str(presupuesto)] if presupuesto else []

        cmd = ["buscar", "--zona", *elegidas,
               "--ambientes", *[str(a) for a in self._ambientes()],
               "--tipos", *self._tipos(),
               "--paginas", str(int(self._numero("paginas"))),
               "--run", run] + precio_max_args + self._extras_navegador()
        self._correr([cmd], f"Buscando en {len(elegidas)} zona(s)", progreso_val=25)

    def paso_rankear(self):
        elegidas = self._validar()
        if not elegidas:
            return
        run = self.nombre_run(elegidas)
        self.ultimo_run = run
        cmd = ["rankear", "--run", run,
               "--presupuesto", str(int(self._numero("presupuesto"))),
               "--dolar", str(int(self._numero("dolar"))),
               "--top", str(int(self._numero("top")))]
        self._correr([cmd], "Rankeando candidatos", progreso_val=50)

    def paso_fotos(self):
        elegidas = self._validar()
        if not elegidas:
            return
        run = self.nombre_run(elegidas)
        self.ultimo_run = run
        cmd = ["fotos", "--run", run,
               "--top", str(int(self._numero("top"))),
               "--max-fotos", str(int(self._numero("max_fotos"))),
               "--presupuesto", str(int(self._numero("presupuesto"))),
               "--dolar", str(int(self._numero("dolar")))] + self._extras_navegador()
        self._correr([cmd], "Descargando fotos y armando contactos", progreso_val=75)

    def paso_dossier(self):
        elegidas = self._validar()
        if not elegidas:
            return
        run = self.nombre_run(elegidas)
        self.ultimo_run = run
        cmd = ["dossier", "--run", run,
               "--top", str(int(self._numero("top")))]
        self._correr([cmd], "Generando dossier, dashboard y mapa", progreso_val=100)

    def paso_todo(self):
        elegidas = self._validar()
        if not elegidas:
            return
        run = self.nombre_run(elegidas)
        self.ultimo_run = run
        presupuesto = int(self._numero("presupuesto")) if self._numero("presupuesto", False) else None
        precio_max_args = ["--precio-max", str(presupuesto)] if presupuesto else []

        cmds = [
            ["buscar", "--zona", *elegidas,
             "--ambientes", *[str(a) for a in self._ambientes()],
             "--tipos", *self._tipos(),
             "--paginas", str(int(self._numero("paginas"))),
             "--run", run] + precio_max_args + self._extras_navegador(),
            ["rankear", "--run", run,
             "--presupuesto", str(int(self._numero("presupuesto"))),
             "--dolar", str(int(self._numero("dolar"))),
             "--top", str(int(self._numero("top")))],
            ["fotos", "--run", run,
             "--top", str(int(self._numero("top"))),
             "--max-fotos", str(int(self._numero("max_fotos"))),
             "--presupuesto", str(int(self._numero("presupuesto"))),
             "--dolar", str(int(self._numero("dolar")))] + self._extras_navegador(),
            ["dossier", "--run", run, "--top", str(int(self._numero("top")))],
        ]
        self._correr(cmds, f"Ejecutando Pipeline Completo ({len(elegidas)} zonas)", progreso_val=100)

    # ------------------------------------------------------------------ #
    # Ejecución de subprocesos
    # ------------------------------------------------------------------ #
    def _correr(self, comandos: list[list[str]], titulo: str, progreso_val: int = 50):
        if self.proceso is not None:
            messagebox.showinfo("Proceso activo", "Ya hay una tarea corriendo. Esperá a que finalice o presiona Frenar.")
            return

        self._habilitar(False)
        self.progreso["value"] = max(10, progreso_val - 20)
        self.estado.set(f"🔵 {titulo}...")
        hilo = threading.Thread(target=self._trabajar, args=(comandos, titulo, progreso_val), daemon=True)
        hilo.start()

    def _trabajar(self, comandos: list[list[str]], titulo: str, progreso_val: int):
        fallo = False
        total = len(comandos)
        for idx, cmd in enumerate(comandos, start=1):
            self.cola.put(f"\n$ python zp.py {' '.join(cmd)}\n")
            try:
                self.proceso = subprocess.Popen(
                    [sys.executable, "-u", str(RAIZ / "zp.py"), *cmd],
                    cwd=str(RAIZ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                )
                for linea in self.proceso.stdout:
                    self.cola.put(linea)
                codigo = self.proceso.wait()
            except Exception as e:
                self.cola.put(f"!ERROR {e}\n")
                fallo = True
                break
            finally:
                self.proceso = None

            if codigo != 0:
                self.cola.put(f"!ERROR El paso finalizó con código {codigo}.\n")
                fallo = True
                break

            self.progreso["value"] = int((idx / total) * progreso_val)

        self.progreso["value"] = 100 if not fallo else 0
        self.cola.put("!FIN " + ("🔴 Con errores" if fallo else f"🟢 {titulo}: ¡Completado con éxito!"))

    def frenar(self):
        p = self.proceso
        if p and p.poll() is None:
            p.terminate()
            self.cola.put("\n⚠️ (Ejecución cancelada por el usuario)\n")
            self.progreso["value"] = 0
            self.estado.set("⚪ Ejecución detenida.")

    def _habilitar(self, activo: bool):
        estado = "normal" if activo else "disabled"
        for b in self.botones.values():
            b.configure(state=estado)
        self.btn_todo.configure(state=estado)
        self.boton_frenar.configure(state="disabled" if activo else "normal")

    def _vaciar_cola(self):
        try:
            while True:
                linea = self.cola.get_nowait()
                if linea.startswith("!FIN "):
                    self.estado.set(linea[5:])
                    self._habilitar(True)
                    continue

                tag = ()
                bajo = linea.lower()
                if linea.startswith("!ERROR"):
                    linea, tag = linea[6:], ("error",)
                elif "verificación de seguridad" in bajo or "verificación pasada" in bajo:
                    tag = ("captcha",)
                    if "pasada" in bajo:
                        self.estado.set("🟢 Verificación superada, continuando.")
                    else:
                        self.estado.set("🟡 VERIFICACIÓN: Tildá el captcha en la ventana de Chrome")
                        self._avisar_captcha()
                elif "...esperando" in bajo:
                    tag = ("captcha",)
                elif "listo" in bajo or linea.strip().startswith("->"):
                    tag = ("ok",)
                elif "$" in linea:
                    tag = ("info",)

                self.log.configure(state="normal")
                self.log.insert("end", linea, tag)
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._vaciar_cola)

    def _avisar_captcha(self):
        try:
            self.maestro.bell()
            self.maestro.attributes("-topmost", True)
            self.maestro.after(1000, lambda: self.maestro.attributes("-topmost", False))
        except tk.TclError:
            pass


def abrir() -> int:
    raiz = tk.Tk()
    raiz.title("Zonaprop Alquileres · Auditor Forense")
    raiz.geometry("1120x820")
    raiz.minsize(980, 700)
    _aplicar_estilo_oscuro(raiz)
    Menu(raiz)
    raiz.mainloop()
    return 0
