"""
Capa web del price tracker. Solo orquesta: recibe requests HTTP,
consulta database.py y renderiza templates. Sin lógica de datos ni scraping.
"""

import logging

from flask import Flask, redirect, render_template, send_file, url_for

import database as db
import export
from scraper import extraer_libros

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

RUTA_DB = "precios.db"

# Inicializar tablas al arrancar la app
db.inicializar_db(RUTA_DB)


# ── Filtro Jinja2 para formatear precios ─────────────────────────────────────
@app.template_filter("libras")
def filtro_libras(valor):
    """Convierte un float a string con símbolo £ y 2 decimales."""
    try:
        return f"£{float(valor):.2f}"
    except (TypeError, ValueError):
        return "N/D"


# ── Rutas ─────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    """Dashboard principal: resumen, cambios de precio y tabla de libros."""
    libros = db.obtener_libros_con_precio_actual(RUTA_DB)
    cambios = db.detectar_cambios_precio(RUTA_DB)

    if libros:
        precios = [l["precio_actual"] for l in libros]
        resumen = {
            "total": len(libros),
            "promedio": sum(precios) / len(precios),
            "mas_caro": max(libros, key=lambda l: l["precio_actual"]),
            "mas_barato": min(libros, key=lambda l: l["precio_actual"]),
        }
    else:
        resumen = None

    return render_template("index.html", libros=libros, cambios=cambios, resumen=resumen)


@app.route("/libro/<int:libro_id>")
def detalle(libro_id: int):
    """Detalle de un libro: info + gráfico de evolución de precios."""
    # Obtener info del libro desde el listado general
    todos = db.obtener_libros_con_precio_actual(RUTA_DB)
    libro = next((l for l in todos if l["id"] == libro_id), None)

    if libro is None:
        return render_template("404.html"), 404

    historial = db.obtener_historial_libro(libro_id, RUTA_DB)

    # Preparar datos para Chart.js: listas paralelas de fechas y precios
    fechas = [h["fecha"][:16].replace("T", " ") for h in historial]  # "2024-01-15 10:30"
    precios_hist = [round(h["precio"], 2) for h in historial]

    return render_template(
        "detalle.html",
        libro=libro,
        historial=historial,
        fechas_json=fechas,
        precios_json=precios_hist,
    )


@app.route("/api/actualizar")
def actualizar():
    """Fuerza un nuevo scrape y guarda el snapshot. Redirige al home."""
    logger.info("Actualización manual solicitada desde la interfaz web.")
    try:
        libros = extraer_libros(paginas=2)
        insertados = db.guardar_snapshot(libros, RUTA_DB)
        logger.info("Actualización completada: %d snapshots guardados.", insertados)
    except Exception as e:
        logger.error("Error durante la actualización: %s", e)
    return redirect(url_for("home"))


@app.route("/exportar/catalogo/excel")
def exportar_catalogo_excel():
    """Genera el Excel del catálogo y lo envía como descarga."""
    try:
        ruta = export.exportar_catalogo_excel(ruta_db=RUTA_DB)
        return send_file(ruta, as_attachment=True, download_name="catalogo.xlsx")
    except ValueError as e:
        logger.warning("Exportación fallida: %s", e)
        return redirect(url_for("home"))


@app.route("/exportar/catalogo/csv")
def exportar_catalogo_csv():
    """Genera el CSV del catálogo y lo envía como descarga."""
    try:
        ruta = export.exportar_catalogo_csv(ruta_db=RUTA_DB)
        return send_file(ruta, as_attachment=True, download_name="catalogo.csv")
    except ValueError as e:
        logger.warning("Exportación fallida: %s", e)
        return redirect(url_for("home"))


@app.route("/exportar/historial/excel")
def exportar_historial_excel():
    """Genera el Excel del historial completo y lo envía como descarga."""
    try:
        ruta = export.exportar_historial_excel(ruta_db=RUTA_DB)
        return send_file(ruta, as_attachment=True, download_name="historial_completo.xlsx")
    except ValueError as e:
        logger.warning("Exportación fallida: %s", e)
        return redirect(url_for("home"))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
