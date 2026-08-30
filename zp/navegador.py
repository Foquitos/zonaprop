"""Capa de navegador.

Zonaprop está detrás de un desafío anti-bot, así que no sirve `requests`: hay
que usar un navegador real. Playwright en modo NO headless con un perfil
persistente es lo que más aguanta.

El perfil persistente (carpeta `.perfil-chrome`) guarda la cookie que queda
después de pasar el desafío (`cf_clearance` en el caso de Cloudflare), así que
una vez que lo resolvés a mano las corridas siguientes no lo vuelven a pedir
por un buen rato.

Sobre el desafío, que es la parte delicada:

  1. Zonaprop usa Cloudflare, no DataDome. La página dice "Un momento..." y
     "Verificación de seguridad en curso", y carga el widget desde
     challenges.cloudflare.com. La versión anterior de este archivo buscaba
     marcas de DataDome, así que el desafío pasaba sin detectarse.
  2. Al no detectarlo, la espera por las tarjetas del listado daba timeout, el
     timeout caía en el reintento, y el reintento hacía `goto` de nuevo: la
     página se recargaba justo cuando estabas por tildar el casillero. Por eso
     era imposible resolverlo.

Ahora, cuando aparece un desafío, no se toca más la página: se espera en
silencio a que lo resuelvas y se chequea cada segundo si ya pasó. Cloudflare
recarga solo cuando corresponde.
"""

from __future__ import annotations

import random
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

# Dominios del desafío: nunca hay que bloquearles un recurso ni tocarlos.
HOSTS_DESAFIO = ("challenges.cloudflare.com", "cdn-cgi", "captcha-delivery.com",
                 "geo.captcha-delivery.com", "hcaptcha.com", "recaptcha.net")

SELECTOR_AVISOS = '[data-qa="posting PROPERTY"]'
# Ojo: en el HTML el atributo va sin corchetes. Buscar el selector CSS dentro
# del HTML no matchea nunca, y entonces cualquier página buena que tuviera un
# script de Cloudflare se leía como desafío.
MARCA_AVISOS = 'data-qa="posting PROPERTY"'


class DesafioError(RuntimeError):
    """Apareció una verificación anti-bot y no se resolvió a tiempo."""


# Alias, porque el nombre viejo quedó escrito en varios lados.
BloqueadoError = DesafioError


# --------------------------------------------------------------------------- #
# Detección
# --------------------------------------------------------------------------- #
_MARCAS_CLOUDFLARE = (
    "challenges.cloudflare.com",
    "/cdn-cgi/challenge-platform/",
    "cf_chl_opt",
    "__cf_chl",
    "cf-turnstile",
    "verificación de seguridad en curso",
    "verifique que es un ser humano",
    "checking your browser",
)
_MARCAS_DATADOME = ("captcha-delivery.com", "geo.captcha-delivery", "datadome")
_TITULOS = ("un momento", "just a moment", "attention required", "acceso denegado",
            "access denied")


def detectar_desafio(html: str, titulo: str = "", avisos: int | None = None) -> str | None:
    """Devuelve 'Cloudflare', 'DataDome' o None.

    Si la página ya trae tarjetas de avisos, no hay desafío por más que
    aparezca algún script de Cloudflare dando vueltas: el contenido llegó.

    `avisos` es la cantidad real de tarjetas en el DOM y es la señal buena; la
    sesión siempre la pasa. Buscar la marca como texto dentro del HTML también
    matchea cuando aparece adentro de un `<script>`, así que solo se usa como
    respaldo cuando no hay un DOM a mano.
    """
    if avisos is not None:
        if avisos > 0:
            return None
    elif MARCA_AVISOS in html:
        return None

    bajo = html[:300_000].lower()
    t = (titulo or "").strip().lower()

    if any(m in bajo for m in _MARCAS_CLOUDFLARE):
        return "Cloudflare"
    if any(m in bajo for m in _MARCAS_DATADOME):
        return "DataDome"
    if any(t.startswith(x) for x in _TITULOS):
        return "verificación"
    return None


# --------------------------------------------------------------------------- #
@contextmanager
def navegador(perfil: Path, headless: bool = False, lento: bool = True,
              canal: str | None = "chrome", espera_desafio: int = 240):
    """Context manager que devuelve una sesión lista para usar.

    canal: 'chrome' usa el Chrome instalado en la máquina, que recibe bastantes
    menos desafíos que el Chromium que trae Playwright. Si no está instalado,
    cae solo al Chromium de Playwright.
    """
    perfil.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        opciones = dict(
            user_data_dir=str(perfil),
            headless=headless,
            viewport={"width": 1400, "height": 950},
            user_agent=UA,
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        ctx, usado = None, None
        for intento_canal in ([canal] if canal else []) + [None]:
            try:
                if intento_canal:
                    ctx = p.chromium.launch_persistent_context(channel=intento_canal, **opciones)
                else:
                    ctx = p.chromium.launch_persistent_context(**opciones)
                usado = intento_canal or "chromium (el que trae Playwright)"
                break
            except Exception:
                continue
        if ctx is None:
            raise RuntimeError(
                "No pude abrir ningún navegador. Probá `playwright install chromium`."
            )

        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        pagina = ctx.pages[0] if ctx.pages else ctx.new_page()
        pagina.route("**/*", _filtrar_recursos)
        try:
            yield _Sesion(pagina, lento, espera_desafio, usado)
        finally:
            ctx.close()


def _filtrar_recursos(route):
    """No cargar fuentes ni video: acelera y no perdemos nada.

    Los dominios del desafío quedan exentos: bloquearles un recurso puede
    romper el widget o, peor, delatar que del otro lado hay un bot.
    """
    peticion = route.request
    if any(h in peticion.url for h in HOSTS_DESAFIO):
        return route.continue_()
    if peticion.resource_type in ("font", "media"):
        return route.abort()
    return route.continue_()


class _Sesion:
    def __init__(self, pagina, lento: bool, espera_desafio: int, canal: str):
        self.pagina = pagina
        self.lento = lento
        self.espera_desafio = espera_desafio
        self.canal = canal
        self._calentado = False

    # ------------------------------------------------------------------ #
    def esperar(self):
        if self.lento:
            time.sleep(random.uniform(1.8, 4.2))

    def _hay_desafio(self) -> str | None:
        """Mira el estado real de la página: HTML, título y tarjetas del DOM."""
        try:
            return detectar_desafio(
                self.pagina.content(), self.pagina.title(), self._contar_avisos()
            )
        except Exception:
            return None  # la página está navegando; no es un desafío

    def _contar_avisos(self) -> int:
        try:
            return len(self.pagina.query_selector_all(SELECTOR_AVISOS))
        except Exception:
            return 0

    def calentar(self):
        """Pasar primero por la home. Entrar directo a una URL de resultados,
        sin cookies y sin referer, es de las cosas que más dispara el desafío."""
        if self._calentado:
            return
        self._calentado = True
        try:
            self.pagina.goto("https://www.zonaprop.com.ar/",
                             wait_until="domcontentloaded", timeout=45000)
            self.pagina.wait_for_timeout(1200)
            if self._hay_desafio():
                self.resolver_desafio()
        except Exception:
            pass  # si la home falla, seguimos igual: no es crítico

    # ------------------------------------------------------------------ #
    def ir(self, url: str, espera_selector: str | None = None, intentos: int = 3) -> str:
        """Navega y devuelve el HTML.

        Un desafío NO cuenta como intento fallido: no se recarga la página,
        se espera a que se resuelva y recién ahí se sigue.
        """
        ultimo = None
        for i in range(intentos):
            try:
                self.pagina.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                ultimo = e
                time.sleep(3 + 4 * i)
                continue

            if self._hay_desafio():
                self.resolver_desafio()          # bloquea hasta que pase o se acabe el tiempo
                if espera_selector:
                    try:
                        self.pagina.wait_for_selector(espera_selector, timeout=20000)
                    except Exception:
                        pass
                return self.pagina.content()

            if espera_selector:
                try:
                    self.pagina.wait_for_selector(espera_selector, timeout=20000)
                except Exception as e:
                    # Puede ser que el desafío haya aparecido recién ahora.
                    if self._hay_desafio():
                        self.resolver_desafio()
                        return self.pagina.content()
                    ultimo = e
                    time.sleep(3 + 4 * i)
                    continue
            else:
                self.pagina.wait_for_timeout(1500)
            return self.pagina.content()

        raise RuntimeError(f"No pude cargar {url}: {ultimo}")

    # ------------------------------------------------------------------ #
    def resolver_desafio(self) -> bool:
        """Espera a que la verificación se resuelva. NO toca la página.

        Nada de recargar ni navegar mientras el desafío está arriba: eso era
        justamente lo que impedía llegar a tildar el casillero. Cloudflare
        recarga solo cuando corresponde.
        """
        cual = self._hay_desafio() or "verificación"
        try:
            self.pagina.bring_to_front()
        except Exception:
            pass

        print()
        print("  " + "=" * 66)
        print(f"  VERIFICACIÓN DE SEGURIDAD ({cual}). Te toca a vos.")
        print("  Tildá el casillero en la ventana del navegador que se abrió.")
        print("  No cierres la ventana ni recargues: la página no se toca desde acá,")
        print("  yo espero y sigo solo cuando pase.")
        print("  " + "=" * 66, flush=True)

        limite = time.time() + self.espera_desafio
        ultimo_aviso = 0.0
        while time.time() < limite:
            self.pagina.wait_for_timeout(1000)
            if not self._hay_desafio():
                print("  Verificación pasada, sigo.\n", flush=True)
                self.pagina.wait_for_timeout(1500)
                return True
            restante = int(limite - time.time())
            if restante and restante % 30 == 0 and time.time() - ultimo_aviso > 5:
                ultimo_aviso = time.time()
                print(f"  ...esperando (quedan {restante}s)", flush=True)

        raise DesafioError(
            f"Pasaron {self.espera_desafio}s y la verificación seguía sin resolverse."
        )

    # ------------------------------------------------------------------ #
    def scrollear(self, pasos: int = 6):
        """Zonaprop carga imágenes de forma diferida; scrollear las materializa."""
        for _ in range(pasos):
            self.pagina.mouse.wheel(0, 1200)
            self.pagina.wait_for_timeout(random.randint(220, 480))
