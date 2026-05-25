"""
Scheduler autocontenido para el price tracker.

Alternativa a cron: un proceso Python que corre el scraper cada N minutos
sin depender del sistema operativo. Útil en entornos donde no tenés acceso
a cron (Windows sin Task Scheduler configurado, contenedores simples, etc.).

Uso:
    python scheduler.py                        # cada 360 minutos (6 horas)
    python scheduler.py --intervalo-minutos 1  # cada minuto (para testing)
    python scheduler.py --intervalo-minutos 30 --paginas 3 --db precios.db
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

import schedule
import time as time_mod

from run_scraper import ejecutar_pipeline

# ── Carpeta de logs (misma que run_scraper) ───────────────────────────────────
CARPETA_LOGS = "logs"
os.makedirs(CARPETA_LOGS, exist_ok=True)

# force=True por la misma razón que en run_scraper.py: los módulos importados
# ya ejecutaron basicConfig antes de que lleguemos a esta línea.
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


# ── Tarea programada ──────────────────────────────────────────────────────────

def _construir_tarea(paginas: int, ruta_db: str, intervalo_minutos: int):
    """Devuelve un callable que ejecuta el pipeline y loguea la próxima corrida."""
    def tarea():
        logger.info("Scheduler: iniciando corrida programada.")
        ejecutar_pipeline(paginas=paginas, ruta_db=ruta_db)

        # Calcular la próxima corrida manualmente: schedule.next_run() dentro
        # de la propia tarea devuelve el next_run ANTERIOR al reajuste (schedule
        # actualiza el job recién cuando la función retorna), por eso repetía
        # la misma hora. datetime.now() usa hora local, consistente con el resto.
        proxima = datetime.now() + timedelta(minutes=intervalo_minutos)
        logger.info(
            "Próxima corrida programada: %s (hora local)",
            proxima.strftime("%Y-%m-%d %H:%M:%S"),
        )

    return tarea


# ── Loop principal ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scheduler autocontenido del price tracker.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--intervalo-minutos",
        type=int,
        default=360,
        metavar="N",
        help="Minutos entre cada corrida del scraper",
    )
    parser.add_argument(
        "--paginas",
        type=int,
        default=5,
        metavar="N",
        help="Páginas a scrapear por corrida",
    )
    parser.add_argument(
        "--db",
        type=str,
        default="precios.db",
        metavar="RUTA",
        help="Ruta al archivo SQLite",
    )
    args = parser.parse_args()

    tarea = _construir_tarea(
        paginas=args.paginas,
        ruta_db=args.db,
        intervalo_minutos=args.intervalo_minutos,
    )

    schedule.every(args.intervalo_minutos).minutes.do(tarea)

    inicio = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=" * 60)
    logger.info("Scheduler iniciado — %s (hora local)", inicio)
    logger.info("Intervalo: cada %d minuto(s)", args.intervalo_minutos)
    logger.info("Páginas por corrida: %d", args.paginas)
    logger.info("Base de datos: %s", args.db)
    logger.info("Presioná Ctrl+C para detener.")
    logger.info("=" * 60)

    # Correr inmediatamente al arrancar, sin esperar el primer intervalo
    logger.info("Ejecutando primera corrida al inicio...")
    tarea()

    try:
        while True:
            schedule.run_pending()
            time_mod.sleep(30)  # revisar la cola cada 30 segundos
    except KeyboardInterrupt:
        logger.info("")
        logger.info("Scheduler detenido manualmente (Ctrl+C). Hasta luego.")
        logger.info("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
