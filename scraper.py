"""
Módulo de scraping para books.toscrape.com.

Sandbox público diseñado para practicar scraping: sin anti-bot,
HTML estable, 50 páginas con 20 libros cada una.

Responsabilidad única: extraer datos del catálogo.
Si el sitio cambia su HTML, solo hay que tocar este archivo.
"""

import logging
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ── Configuración de logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────────────────
URL_BASE = "https://books.toscrape.com"
URL_CATALOGO = f"{URL_BASE}/catalogue/page-{{n}}.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIMEOUT_SEGUNDOS = 15

# El sitio tiene exactamente 50 páginas
PAGINAS_TOTALES = 50

# Mapeo de rating en texto a número (clase CSS del sitio)
RATING_TEXTO_A_NUMERO = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
}


# ── Funciones internas ──────────────────────────────────────────────────────

def _construir_url(pagina: int) -> str:
    """Devuelve la URL del catálogo para el número de página dado."""
    return URL_CATALOGO.format(n=pagina)


def _obtener_html(url: str) -> Optional[str]:
    """
    Realiza la petición HTTP y devuelve el HTML como texto.
    Retorna None si la petición falla por cualquier motivo.
    """
    try:
        logger.info("Solicitando: %s", url)
        respuesta = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SEGUNDOS)

        if respuesta.status_code != 200:
            logger.error(
                "Status inesperado %d para URL: %s",
                respuesta.status_code,
                url,
            )
            return None

        return respuesta.text

    except requests.exceptions.Timeout:
        logger.error("Timeout al conectar con %s (límite: %ds)", url, TIMEOUT_SEGUNDOS)
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Error de conexión al intentar acceder a %s", url)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Error inesperado en la petición: %s", e)
        return None


def _extraer_rating(tarjeta) -> int:
    """
    Lee la clase CSS del elemento p.star-rating y la convierte a entero 1-5.
    Retorna 0 si no puede determinarse el rating.
    """
    nodo_rating = tarjeta.select_one("p.star-rating")
    if not nodo_rating:
        return 0
    # Las clases son ["star-rating", "Three"] — tomamos la segunda
    clases = nodo_rating.get("class", [])
    for clase in clases:
        if clase in RATING_TEXTO_A_NUMERO:
            return RATING_TEXTO_A_NUMERO[clase]
    return 0


def _parsear_producto(tarjeta) -> Optional[dict]:
    """
    Extrae los datos de un elemento <article class='product_pod'>.
    Retorna None si no puede extraer los campos mínimos (título y precio).
    """
    try:
        # ── Título ───────────────────────────────────────────────────────────
        # El texto visible del <a> está truncado; el atributo 'title' tiene el nombre completo
        nodo_titulo = tarjeta.select_one("h3 > a")
        if not nodo_titulo:
            logger.debug("Tarjeta sin título, se omite.")
            return None
        titulo = nodo_titulo.get("title", nodo_titulo.get_text(strip=True))

        # ── Precio ───────────────────────────────────────────────────────────
        nodo_precio = tarjeta.select_one("p.price_color")
        if not nodo_precio:
            logger.debug("Libro '%s' sin precio visible, se omite.", titulo)
            return None
        # El texto tiene formato "£51.77" o "Â£51.77" según encoding; limpiar todo excepto dígitos y punto
        precio_texto = "".join(c for c in nodo_precio.get_text(strip=True) if c.isdigit() or c == ".")
        precio = float(precio_texto)

        # ── Disponibilidad ───────────────────────────────────────────────────
        nodo_disponibilidad = tarjeta.select_one("p.instock.availability")
        disponibilidad = nodo_disponibilidad.get_text(strip=True) if nodo_disponibilidad else "Unknown"

        # ── Rating ───────────────────────────────────────────────────────────
        rating = _extraer_rating(tarjeta)

        # ── Link al detalle ──────────────────────────────────────────────────
        # El href es relativo al directorio /catalogue/, ej: "../../../its-only-the-himalayas_981/index.html"
        href = nodo_titulo.get("href", "")
        if href:
            # Eliminar los "../" iniciales y construir URL absoluta
            href_limpio = href.replace("../", "")
            link = f"{URL_BASE}/catalogue/{href_limpio}"
        else:
            link = "N/D"

        return {
            "titulo": titulo,
            "precio": precio,
            "disponibilidad": disponibilidad,
            "rating": rating,
            "link": link,
        }

    except (ValueError, TypeError, KeyError) as e:
        logger.debug("Error al parsear tarjeta: %s", e)
        return None


def _parsear_pagina(html: str) -> list[dict]:
    """Parsea el HTML completo de una página y devuelve la lista de libros."""
    soup = BeautifulSoup(html, "lxml")

    tarjetas = soup.select("article.product_pod")

    if not tarjetas:
        logger.warning(
            "No se encontraron tarjetas de productos. "
            "El sitio pudo haber cambiado su estructura HTML."
        )
        return []

    logger.info("Libros encontrados en la página: %d", len(tarjetas))

    libros = []
    for tarjeta in tarjetas:
        libro = _parsear_producto(tarjeta)
        if libro:
            libros.append(libro)

    return libros


# ── API pública del módulo ──────────────────────────────────────────────────

def extraer_libros(
    paginas: int = 1,
    pausa_segundos: float = 2.0,
) -> list[dict]:
    """
    Extrae libros del catálogo de books.toscrape.com.

    Args:
        paginas: Cantidad de páginas a recorrer (máximo 50, 20 libros por página).
        pausa_segundos: Segundos de espera entre páginas consecutivas.
            Respetar un intervalo mínimo entre peticiones es fundamental
            para no sobrecargar el servidor y evitar bloqueos por IP,
            incluso en sitios sandbox que no tienen anti-bot activo.

    Returns:
        Lista de dicts con claves: titulo, precio, disponibilidad, rating, link.
    """
    if paginas < 1:
        raise ValueError("El número de páginas debe ser al menos 1.")
    if paginas > PAGINAS_TOTALES:
        logger.warning(
            "Se solicitaron %d páginas pero el sitio solo tiene %d. "
            "Se usará el máximo disponible.",
            paginas,
            PAGINAS_TOTALES,
        )
        paginas = PAGINAS_TOTALES

    todos_los_libros: list[dict] = []

    for numero_pagina in range(1, paginas + 1):
        url = _construir_url(numero_pagina)
        html = _obtener_html(url)

        if html is None:
            logger.warning("Se omite página %d por error en la petición.", numero_pagina)
            continue

        libros_pagina = _parsear_pagina(html)
        todos_los_libros.extend(libros_pagina)
        logger.info(
            "Página %d/%d — libros extraídos: %d (total acumulado: %d)",
            numero_pagina,
            paginas,
            len(libros_pagina),
            len(todos_los_libros),
        )

        # Pausa entre páginas para respetar rate limits (no aplica en la última)
        if numero_pagina < paginas:
            logger.debug("Esperando %.1f segundos antes de la siguiente página...", pausa_segundos)
            time.sleep(pausa_segundos)

    return todos_los_libros


# ── Prueba rápida ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    PAGINAS_PRUEBA = 1

    print(f"\nExtrayendo libros de books.toscrape.com (página 1 de {PAGINAS_TOTALES})...\n")
    resultados = extraer_libros(paginas=PAGINAS_PRUEBA)

    if not resultados:
        print("No se obtuvieron resultados. Revisá los logs para más detalles.")
    else:
        ANCHO_TITULO = 38
        print(f"{'─' * 68}")
        print(f"  {'TÍTULO':<{ANCHO_TITULO}} {'PRECIO':>7}  {'RATING':>6}  STOCK")
        print(f"{'─' * 68}")
        for libro in resultados:
            titulo_corto = libro["titulo"][:ANCHO_TITULO]
            precio_fmt = f"£{libro['precio']:.2f}"
            estrellas = "★" * libro["rating"] + "☆" * (5 - libro["rating"])
            stock = libro["disponibilidad"]
            print(f"  {titulo_corto:<{ANCHO_TITULO}} {precio_fmt:>7}  {estrellas}  {stock}")
        print(f"{'─' * 68}")
        print(f"\nTotal: {len(resultados)} libros\n")
