"""Menú visual de la app. Tkinter, que viene con Python, así que no agrega
dependencias ni hay que instalar nada.

Se abre con:

    python zp.py menu

La ventana tiene tres partes:

  izquierda   el árbol de zonas, agrupado por partido y por ciudad. Al hacer
              clic en una zona se explica exactamente qué abarca, que es la
              diferencia entre "Vicente López, el partido entero" y "Vicente
              López, la localidad".
  derecha     los filtros de la búsqueda.
  abajo       los cuatro pasos del pipeline y el log en vivo.

Cada paso lanza el mismo `zp.py` que se usa desde la terminal, como
subproceso, y va volcando la salida en el log. Así el menú no duplica lógica:
si mañana cambia el scraper, el menú sigue andando igual. Abajo de todo se
muestra el comando que se está por ejecutar, para que se pueda copiar y
automatizar sin la ventana.
"""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

from zp import urls, zonas

RAIZ = Path(__file__).resolve().parents[1]

COLOR_FONDO = "#f4f4f5"
COLOR_LOG_BG = "#18181b"
COLOR_LOG_FG = "#e4e4e7"


class Menu(ttk.Frame):
    def __init__(self, maestro: tk.Tk):
        super().__init__(maestro, padding=10)
        self.maestro = maestro
        self.cola: queue.Queue[str] = queue.Queue()
        self.proceso: subprocess.Popen | None = None

        self.grid(sticky="nsew")
        maestro.columnconfigure(0, weight=1)
        maestro.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=3, minsize=330)
        self.columnconfigure(1, weight=2, minsize=320)
        self.rowconfigure(0, weight=1)   # zonas y filtros
        self.rowconfigure(2, weight=1)   # el log, que es lo que más crece

        self._construir_zonas()
        self._construir_filtros()
        self._construir_acciones()
        self._refrescar_arbol()
        self.after(120, self._vaciar_cola)

    # ------------------------------------------------------------------ #
    # Zonas
    # ------------------------------------------------------------------ #
    def _construir_zonas(self):
        caja = ttk.LabelFrame(self, text="Dónde buscar", padding=8)
        caja.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        caja.rowconfigure(3, minsize=90)
        caja.columnconfigure(0, weight=1)
        caja.rowconfigure(1, weight=1)

        barra = ttk.Frame(caja)
        barra.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        barra.columnconfigure(1, weight=1)
        ttk.Label(barra, text="Filtrar:").grid(row=0, column=0, padx=(0, 6))
        self.filtro = tk.StringVar()
        self.filtro.trace_add("write", lambda *_: self._refrescar_arbol())
        ttk.Entry(barra, textvariable=self.filtro).grid(row=0, column=1, sticky="ew")

        self.arbol = ttk.Treeview(caja, selectmode="extended", show="tree", height=17)
        self.arbol.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(caja, orient="vertical", command=self.arbol.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.arbol.configure(yscrollcommand=scroll.set)
        self.arbol.bind("<<TreeviewSelect>>", self._al_elegir_zona)
        self.arbol.tag_configure("grupo", font=("TkDefaultFont", 9, "bold"))

        ttk.Label(caja, text="Ctrl + clic para elegir varias zonas.",
                  foreground="#71717a").grid(row=2, column=0, sticky="w", pady=(6, 2))

        self.detalle = tk.Text(caja, height=5, wrap="word", relief="flat",
                               background=COLOR_FONDO, foreground="#3f3f46",
                               font=("TkDefaultFont", 9))
        self.detalle.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._poner_detalle("Elegí una zona para ver qué abarca.")

    def _refrescar_arbol(self):
        self.arbol.delete(*self.arbol.get_children())
        visibles = {z.slug for z in zonas.buscar(self.filtro.get())}
        for titulo, slugs in zonas.GRUPOS:
            hijos = [s for s in slugs if s in visibles]
            if not hijos:
                continue
            padre = self.arbol.insert("", "end", text=titulo, open=True, tags=("grupo",))
            for s in hijos:
                z = zonas.TODAS[s]
                marca = "  " if z.nivel in ("localidad", "barrio") else ""
                self.arbol.insert(padre, "end", iid=s, text=f"{marca}{z.nombre}")

    def _al_elegir_zona(self, _evento=None):
        elegidas = self.zonas_elegidas()
        if not elegidas:
            self._poner_detalle("Elegí una zona para ver qué abarca.")
            return
        if len(elegidas) > 1:
            nombres = ", ".join(zonas.TODAS[s].nombre for s in elegidas)
            self._poner_detalle(
                f"{len(elegidas)} zonas: {nombres}.\n"
                "Se hace una búsqueda por cada una y después se unen "
                "descartando los avisos repetidos."
            )
            return
        z = zonas.TODAS[elegidas[0]]
        texto = f"{z.nombre}  ({z.nivel})\nslug: {z.slug}\nZonaprop lo llama: «{z.esperado}»"
        if z.nota:
            texto += f"\n\n{z.nota}"
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
        caja = ttk.LabelFrame(self, text="Qué buscar", padding=8)
        caja.grid(row=0, column=1, sticky="nsew")
        caja.columnconfigure(1, weight=1)
        fila = 0

        ttk.Label(caja, text="Ambientes").grid(row=fila, column=0, sticky="w", pady=3)
        marco_amb = ttk.Frame(caja)
        marco_amb.grid(row=fila, column=1, sticky="w")
        self.ambientes = {}
        for n in (1, 2, 3, 4):
            v = tk.BooleanVar(value=(n in (1, 2)))
            ttk.Checkbutton(marco_amb, text=str(n), variable=v).pack(side="left")
            self.ambientes[n] = v
        fila += 1

        ttk.Label(caja, text="Tipo").grid(row=fila, column=0, sticky="w", pady=3)
        marco_tipo = ttk.Frame(caja)
        marco_tipo.grid(row=fila, column=1, sticky="w")
        self.tipos = {}
        for etiqueta, slug, defecto in (("Depto", "departamentos", True),
                                        ("PH", "ph", True),
                                        ("Casa", "casas", False)):
            v = tk.BooleanVar(value=defecto)
            ttk.Checkbutton(marco_tipo, text=etiqueta, variable=v).pack(side="left")
            self.tipos[slug] = v
        fila += 1

        self.campos = {}
        for etiqueta, clave, valor, ayuda in (
            ("Presupuesto", "presupuesto", "900000", "alquiler + expensas, en pesos"),
            ("Dólar", "dolar", "1450", "para convertir los avisos en USD"),
            ("Páginas", "paginas", "6", "30 avisos por página"),
            ("Top a revisar", "top", "20", "cuántos pasan a la etapa de fotos"),
            ("Fotos por aviso", "max_fotos", "16", "las últimas siempre se conservan"),
            ("Espera captcha", "espera_captcha", "240",
             "segundos para tildar el casillero"),
        ):
            ttk.Label(caja, text=etiqueta).grid(row=fila, column=0, sticky="w", pady=3)
            v = tk.StringVar(value=valor)
            ttk.Entry(caja, textvariable=v, width=12).grid(row=fila, column=1, sticky="w")
            ttk.Label(caja, text=ayuda, foreground="#71717a",
                      font=("TkDefaultFont", 8)).grid(row=fila + 1, column=1, sticky="w")
            self.campos[clave] = v
            fila += 2

        self.headless = tk.BooleanVar(value=False)
        ttk.Checkbutton(caja, text="Sin ventana del navegador (headless)",
                        variable=self.headless).grid(row=fila, column=0, columnspan=2,
                                                     sticky="w", pady=(8, 0))
        fila += 1
        ttk.Label(caja, text="Dejalo destildado la primera vez: si Zonaprop pide\n"
                             "captcha, hay que resolverlo a mano una sola vez.",
                  foreground="#71717a", font=("TkDefaultFont", 8),
                  justify="left").grid(row=fila, column=0, columnspan=2, sticky="w")

    # ------------------------------------------------------------------ #
    # Acciones y log
    # ------------------------------------------------------------------ #
    def _construir_acciones(self):
        caja = ttk.Frame(self)
        caja.grid(row=1, column=1, sticky="nsew", pady=(8, 0))
        caja.columnconfigure(0, weight=1)

        pasos = ttk.LabelFrame(caja, text="Pasos", padding=8)
        pasos.grid(row=0, column=0, sticky="ew")
        pasos.columnconfigure((0, 1), weight=1)

        self.botones = {}
        acciones = [
            ("1 · Buscar", self.paso_buscar),
            ("2 · Rankear", self.paso_rankear),
            ("3 · Fotos", self.paso_fotos),
            ("4 · Dossier", self.paso_dossier),
        ]
        for i, (texto, fn) in enumerate(acciones):
            b = ttk.Button(pasos, text=texto, command=fn)
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
            self.botones[texto] = b

        ttk.Button(pasos, text="Todo seguido", command=self.paso_todo).grid(
            row=2, column=0, sticky="ew", padx=2, pady=(6, 2))
        self.boton_frenar = ttk.Button(pasos, text="Frenar", command=self.frenar,
                                       state="disabled")
        self.boton_frenar.grid(row=2, column=1, sticky="ew", padx=2, pady=(6, 2))

        self.comando = tk.StringVar(value="")
        ttk.Label(caja, textvariable=self.comando, foreground="#52525b",
                  font=("TkFixedFont", 8), wraplength=420, justify="left").grid(
            row=1, column=0, sticky="w", pady=(6, 2))

        self.estado = tk.StringVar(value="Listo.")
        ttk.Label(caja, textvariable=self.estado).grid(row=2, column=0, sticky="w")

        # El log va abajo de todo y a lo ancho de la ventana: es lo que se lee
        # mientras corre, y en la primera versión quedaba aplastado en 3 líneas.
        marco_log = ttk.LabelFrame(self, text="Qué está pasando", padding=6)
        marco_log.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        marco_log.columnconfigure(0, weight=1)
        marco_log.rowconfigure(0, weight=1)
        self.log = tk.Text(marco_log, height=9, wrap="word", background=COLOR_LOG_BG,
                           foreground=COLOR_LOG_FG, insertbackground=COLOR_LOG_FG,
                           font=("TkFixedFont", 9), relief="flat")
        self.log.grid(row=0, column=0, sticky="nsew")
        sl = ttk.Scrollbar(marco_log, orient="vertical", command=self.log.yview)
        sl.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sl.set, state="disabled")
        self.log.tag_configure("error", foreground="#f87171")
        self.log.tag_configure("ok", foreground="#4ade80")
        self.log.tag_configure("captcha", foreground="#fbbf24",
                               font=("TkFixedFont", 9, "bold"))

    # ------------------------------------------------------------------ #
    # Armado de los comandos
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

    def nombre_run(self, slug: str) -> str:
        return urls.nombre_run(slug, self._ambientes())

    def _extras_navegador(self) -> list[str]:
        extras = ["--espera-captcha", str(int(self._numero("espera_captcha")))]
        if self.headless.get():
            extras.append("--headless")
        return extras

    def _validar(self) -> list[str] | None:
        elegidas = self.zonas_elegidas()
        if not elegidas:
            messagebox.showwarning("Falta la zona", "Elegí al menos una zona.")
            return None
        if not self._ambientes():
            messagebox.showwarning("Faltan ambientes", "Elegí al menos una cantidad de ambientes.")
            return None
        if not self._tipos():
            messagebox.showwarning("Falta el tipo", "Elegí al menos un tipo de propiedad.")
            return None
        return elegidas

    def paso_buscar(self):
        elegidas = self._validar()
        if not elegidas:
            return
        cmds = []
        for slug in elegidas:
            cmds.append(["buscar", "--zona", slug,
                         "--ambientes", *[str(a) for a in self._ambientes()],
                         "--tipos", *self._tipos(),
                         "--paginas", str(int(self._numero("paginas"))),
                         "--run", self.nombre_run(slug)] + self._extras_navegador())
        self._correr(cmds, "Buscando")

    def paso_rankear(self):
        elegidas = self._validar()
        if not elegidas:
            return
        cmds = [["rankear", "--run", self.nombre_run(s),
                 "--presupuesto", str(int(self._numero("presupuesto"))),
                 "--dolar", str(int(self._numero("dolar"))),
                 "--top", str(int(self._numero("top")))] for s in elegidas]
        self._correr(cmds, "Rankeando")

    def paso_fotos(self):
        elegidas = self._validar()
        if not elegidas:
            return
        cmds = [["fotos", "--run", self.nombre_run(s),
                 "--top", str(int(self._numero("top"))),
                 "--max-fotos", str(int(self._numero("max_fotos"))),
                 "--presupuesto", str(int(self._numero("presupuesto"))),
                 "--dolar", str(int(self._numero("dolar")))] + self._extras_navegador()
                for s in elegidas]
        self._correr(cmds, "Bajando fotos")

    def paso_dossier(self):
        elegidas = self._validar()
        if not elegidas:
            return
        cmds = [["dossier", "--run", self.nombre_run(s),
                 "--top", str(int(self._numero("top")))] for s in elegidas]
        self._correr(cmds, "Armando el dossier")

    def paso_todo(self):
        elegidas = self._validar()
        if not elegidas:
            return
        cmds = []
        for s in elegidas:
            run = self.nombre_run(s)
            cmds.append(["buscar", "--zona", s,
                         "--ambientes", *[str(a) for a in self._ambientes()],
                         "--tipos", *self._tipos(),
                         "--paginas", str(int(self._numero("paginas"))),
                         "--run", run] + self._extras_navegador())
            cmds.append(["rankear", "--run", run,
                         "--presupuesto", str(int(self._numero("presupuesto"))),
                         "--dolar", str(int(self._numero("dolar"))),
                         "--top", str(int(self._numero("top")))])
            cmds.append(["fotos", "--run", run,
                         "--top", str(int(self._numero("top"))),
                         "--max-fotos", str(int(self._numero("max_fotos"))),
                         "--presupuesto", str(int(self._numero("presupuesto"))),
                         "--dolar", str(int(self._numero("dolar")))]
                        + self._extras_navegador())
            cmds.append(["dossier", "--run", run, "--top", str(int(self._numero("top")))])
        self._correr(cmds, "Corriendo todo")

    # ------------------------------------------------------------------ #
    # Ejecución
    # ------------------------------------------------------------------ #
    def _correr(self, comandos: list[list[str]], titulo: str):
        if self.proceso is not None:
            messagebox.showinfo("Ya hay algo corriendo", "Esperá a que termine o frenalo.")
            return
        if self.headless.get() and any("--headless" in c for c in comandos):
            seguir = messagebox.askokcancel(
                "Sin ventana del navegador",
                "Con 'headless' tildado la ventana no se ve, así que si Zonaprop "
                "pide verificación no vas a poder tildar el casillero y el paso "
                "se corta.\n\nDestildalo la primera vez: una vez resuelta, la "
                "cookie queda guardada y después sí podés usar headless.\n\n"
                "¿Seguir igual?")
            if not seguir:
                return
        self.comando.set("python zp.py " + " ".join(comandos[0]))
        self._ya_avise = False
        self._habilitar(False)
        self.estado.set(f"{titulo}...")
        hilo = threading.Thread(target=self._trabajar, args=(comandos, titulo), daemon=True)
        hilo.start()

    def _trabajar(self, comandos: list[list[str]], titulo: str):
        fallo = False
        for cmd in comandos:
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
                self.cola.put(f"!ERROR el paso terminó con código {codigo}; corto acá.\n")
                fallo = True
                break
        self.cola.put("!FIN " + ("con errores" if fallo else f"{titulo}: listo"))

    def _avisar_captcha(self):
        """Trae la ventana al frente una sola vez por corrida, para que no se te
        pase el captcha si estabas en otra cosa."""
        if getattr(self, "_ya_avise", False):
            return
        self._ya_avise = True
        try:
            self.maestro.bell()
            self.maestro.attributes("-topmost", True)
            self.maestro.after(1200, lambda: self.maestro.attributes("-topmost", False))
        except tk.TclError:
            pass

    def frenar(self):
        p = self.proceso
        if p and p.poll() is None:
            p.terminate()
            self.cola.put("\n(frenado a mano)\n")

    def _habilitar(self, activo: bool):
        estado = "normal" if activo else "disabled"
        for b in self.botones.values():
            b.configure(state=estado)
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
                    # El captcha es lo único que necesita que estés mirando:
                    # tiene que gritar, no perderse entre las líneas del log.
                    tag = ("captcha",)
                    if "pasada" in bajo:
                        self.estado.set("Verificación pasada, sigo.")
                    else:
                        self.estado.set(
                            "VERIFICACIÓN: tildá el casillero en la ventana del navegador"
                        )
                        self._avisar_captcha()
                elif "...esperando" in bajo:
                    tag = ("captcha",)
                elif "listo" in bajo or linea.strip().startswith("->"):
                    tag = ("ok",)
                self.log.configure(state="normal")
                self.log.insert("end", linea, tag)
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(120, self._vaciar_cola)


def abrir() -> int:
    raiz = tk.Tk()
    raiz.title("Alquileres · Zonaprop")
    raiz.geometry("1060x800")
    raiz.minsize(940, 680)
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    Menu(raiz)
    raiz.mainloop()
    return 0
