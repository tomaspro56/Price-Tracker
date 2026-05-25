"""
Script standalone para ejecutar una corrida completa del pipeline.

Diseñado para ser disparado por cron (Linux/WSL/Mac) o Task Scheduler
(Windows). No es un servidor: corre, reporta y termina.

Uso:
    python run_scraper.py
    python run_scraper.py --paginas 10
    python run_scraper.py --paginas 3 --db mi_base.db
"""

import argparse
import logging
import os
import sys
from datetime import datetime

import database as db
from scraper import extraer_libros

# ── Carpeta de logs ───────────────────────────────────────────────────────────
CARPETA_LOGS = "logs"
os.makedirs(CARPETA_LOGS, exist_ok=True)

# ── Logging: consola + archivo persistente ────────────────────────────────────
# force=True es necesario porque scraper.py y database.py llaman a basicConfig()
# al importarse, configurando el root logger solo con StreamHandler. Sin force=True,
# este basicConfig sería un no-op y el FileHandler nunca se agregaría.
logging.basicConfig(
    force=True,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(CARPETA_LOGS, "scraper_runs.log"),
            mode="a",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


# ── Lógica principal ──────────────────────────────────────────────────────────

def ejecutar_pipeline(paginas: int, ruta_db: str) -> int:
    """
    Corre el pipeline completo: inicializar → extraer → guardar → reportar.

    Returns:
        0 si la corrida fue exitosa, 1 si ocurrió un error.
    """
    inicio = datetime.now()
    logger.info("=" * 60)
    logger.info("Iniciando corrida — %s (hora local)", inicio.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Páginas: %d | Base de datos: %s", paginas, ruta_db)

    try:
        db.inicializar_db(ruta_db)
        libros = extraer_libros(paginas=paginas)

        if not libros:
            logger.warning("El scraper no devolvió libros. Corrida abortada.")
            return 1

        snapshots = db.guardar_snapshot(libros, ruta_db)
        cambios = db.detectar_cambios_precio(ruta_db)

        duracion = (datetime.now() - inicio).total_seconds()

        logger.info("-" * 60)
        logger.info("RESUMEN DE LA CORRIDA")
        logger.info("  Libros extraídos   : %d", len(libros))
        logger.info("  Snapshots guardados: %d", snapshots)
        logger.info("  Cambios de precio  : %d", len(cambios))
        logger.info("  Duración           : %.1f segundos", duracion)
        logger.info("  Timestamp          : %s (hora local)", inicio.strftime("%Y-%m-%d %H:%M:%S"))

        if cambios:
            logger.info("  Detalle de cambios:")
            for c in cambios:
                signo = "+" if c["diferencia"] > 0 else ""
                logger.info(
                    "    [%d] %s: £%.2f → £%.2f (%s%.2f)",
                    c["libro_id"],
                    c["titulo"][:45],
                    c["precio_anterior"],
                    c["precio_nuevo"],
                    signo,
                    c["diferencia"],
                )

        logger.info("Corrida completada exitosamente.")
        logger.info("=" * 60)
        return 0

    except Exception as e:
        logger.error("Error crítico durante la corrida: %s", e, exc_info=True)
        logger.info("=" * 60)
        return 1


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ejecuta una corrida completa del price tracker.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--paginas",
        type=int,
        default=5,
        metavar="N",
        help="Cantidad de páginas a scrapear (20 libros por página)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default="precios.db",
        metavar="RUTA",
        help="Ruta al archivo SQLite",
    )
    args = parser.parse_args()

    codigo_salida = ejecutar_pipeline(paginas=args.paginas, ruta_db=args.db)
    sys.exit(codigo_salida)


if __name__ == "__main__":
    main()
