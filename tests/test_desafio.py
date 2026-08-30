"""Test de integración del manejo del desafío anti-bot.

Este es el test que cubre el bug que hacía imposible resolver el captcha: la
página se recargaba antes de que llegaras a tildar el casillero.

Levanta un servidor local que devuelve una página de desafío igual a la de
Cloudflare, y que después de unos segundos se transforma sola en un listado
(como hace Cloudflare cuando pasás la verificación). Se verifica:

  1. que el desafío se detecte,
  2. que se espere sin tocar la página,
  3. y sobre todo que el servidor reciba UNA sola request: si el scraper
     recargara, el contador daría más de uno y el casillero se perdería.

Necesita Playwright con Chromium. Si no está, el test se saltea.

    python -m pytest tests/test_desafio.py -q
"""

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("playwright", reason="requiere playwright")
from zp.navegador import DesafioError, detectar_desafio, navegador  # noqa: E402

# Página de desafío que, a los 3 segundos, se convierte sola en un listado.
# Es lo que hace Cloudflare cuando pasás la verificación.
DESAFIO = """<!doctype html><html lang="es"><head><title>Un momento...</title></head>
<body>
  <h1>www.zonaprop.com.ar</h1>
  <h2>Verificación de seguridad en curso</h2>
  <p>Verifique que es un ser humano</p>
  <script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1"></script>
<script>
  setTimeout(function () {
    document.title = "Departamentos en alquiler - Zonaprop";
    document.body.innerHTML =
      '<h1>3 Departamentos en alquiler en Villa Martelli, Vicente L\\u00f3pez</h1>' +
      '<div data-' + 'qa="posting PROPERTY" data-id="1"></div>';
  }, 3000);
</script>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    pedidos: list = []

    def do_GET(self):
        _Handler.pedidos.append(self.path)
        cuerpo = DESAFIO.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *_args):
        pass


@pytest.fixture
def servidor():
    _Handler.pedidos = []
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/listado"
    srv.shutdown()


@pytest.fixture
def sesion(tmp_path):
    with navegador(tmp_path / "perfil", headless=True, lento=False,
                   canal=None, espera_desafio=30) as ses:
        yield ses


def test_el_desafio_se_detecta_y_no_se_recarga(servidor, sesion, capsys):
    html = sesion.ir(servidor, espera_selector='[data-qa="posting PROPERTY"]')

    # Salió del desafío y llegó al contenido.
    assert 'data-qa="posting PROPERTY"' in html
    assert detectar_desafio(html, "Departamentos en alquiler - Zonaprop") is None

    # Lo importante: una sola visita. Si recargara, el casillero se perdería.
    visitas = [p for p in _Handler.pedidos if p == "/listado"]
    assert len(visitas) == 1, f"la página se pidió {len(visitas)} veces; no debe recargarse"

    salida = capsys.readouterr().out
    assert "VERIFICACIÓN DE SEGURIDAD" in salida
    assert "Verificación pasada" in salida


def test_si_no_se_resuelve_avisa_claro(tmp_path):
    """Con un desafío que nunca se resuelve, corta con un error entendible."""
    class Eterno(_Handler):
        def do_GET(self):
            _Handler.pedidos.append(self.path)
            cuerpo = DESAFIO.replace("}, 3000);", "}, 999000);").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

    _Handler.pedidos = []
    srv = HTTPServer(("127.0.0.1", 0), Eterno)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/listado"
    try:
        with navegador(tmp_path / "perfil2", headless=True, lento=False,
                       canal=None, espera_desafio=5) as ses:
            with pytest.raises(DesafioError) as err:
                ses.ir(url, espera_selector='[data-qa="posting PROPERTY"]')
        assert "verificación" in str(err.value).lower()
        # Tampoco acá tiene que haber recargado.
        assert len([p for p in _Handler.pedidos if p == "/listado"]) == 1
    finally:
        srv.shutdown()
