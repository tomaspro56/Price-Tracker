"""
Módulo de persistencia para el monitor de precios.

Responsabilidad única: leer y escribir datos en SQLite.
No sabe nada de scraping ni de cómo se obtienen los datos.
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── DDL ─────────────────────────────────────────────────────────────────────
_SQL_CREAR_TABLA_LIBROS = """
CREATE TABLE IF NOT EXISTS libros (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo            TEXT    UNIQUE NOT NULL,
    link              TEXT,
    rating            INTEGER,
    primera_vez_visto TEXT    NOT NULL
);
"""

_SQL_CREAR_TABLA_HISTORIAL = """
CREATE TABLE IF NOT EXISTS historial_precios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    libro_id      INTEGER NOT NULL,
    precio        REAL    NOT NULL,
    disponibilidad TEXT,
    fecha         TEXT    NOT NULL,
    FOREIGN KEY (libro_id) REFERENCES libros(id)
);
"""

# Índice para acelerar las consultas de historial por libro y fecha
_SQL_CREAR_INDICE_HISTORIAL = """
CREATE INDEX IF NOT EXISTS idx_historial_libro_fecha
ON historial_precios(libro_id, fecha);
"""


# ── Utilidades internas ──────────────────────────────────────────────────────

def _ahora_iso() -> str:
    """Retorna el timestamp actual en formato ISO 8601 con timezone UTC."""
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _conectar(ruta_db: str) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager que abre y cierra la conexión a SQLite.
    Hace commit si el bloque termina sin error; rollback si hay excepción.
    """
    conexion = sqlite3.connect(ruta_db)
    # Devolver filas como objetos que soportan acceso por nombre de columna
    conexion.row_factory = sqlite3.Row
    # Activar soporte de claves foráneas (SQLite lo desactiva por defecto)
    conexion.execute("PRAGMA foreign_keys = ON")
    try:
        yield conexion
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


# ── API pública ──────────────────────────────────────────────────────────────

def inicializar_db(ruta_db: str = "precios.db") -> None:
    """
    Crea las tablas e índices si no existen. Seguro de llamar múltiples veces.

    Args:
        ruta_db: Ruta al archivo SQLite. Se crea si no existe.
    """
    try:
        with _conectar(ruta_db) as con:
            con.execute(_SQL_CREAR_TABLA_LIBROS)
            con.execute(_SQL_CREAR_TABLA_HISTORIAL)
            con.execute(_SQL_CREAR_INDICE_HISTORIAL)
        logger.info("Base de datos inicializada: %s", ruta_db)
    except sqlite3.Error as e:
        logger.error("Error al inicializar la base de datos: %s", e)
        raise


def guardar_snapshot(libros: list[dict], ruta_db: str = "precios.db") -> int:
    """
    Persiste un snapshot de la lista de libros extraída por el scraper.

    Para cada libro:
    - Si no existe en `libros`, lo inserta con su timestamp de primera visita.
    - Si ya existe, reutiliza su id (el título es la clave natural).
    - Siempre inserta un nuevo registro en `historial_precios`.

    Args:
        libros: Lista de dicts con claves titulo, precio, disponibilidad,
                rating y link (formato de salida de extraer_libros()).
        ruta_db: Ruta al archivo SQLite.

    Returns:
        Cantidad de snapshots insertados en historial_precios.
    """
    if not libros:
        logger.warning("guardar_snapshot recibió una lista vacía, nada que guardar.")
        return 0

    ahora = _ahora_iso()
    snapshots_insertados = 0

    try:
        with _conectar(ruta_db) as con:
            for libro in libros:
                titulo = libro.get("titulo")
                if not titulo:
                    logger.debug("Libro sin título, se omite.")
                    continue

                # Upsert: insertar si no existe; en conflicto no hacer nada
                # (preservamos primera_vez_visto del registro original)
                con.execute(
                    """
                    INSERT INTO libros (titulo, link, rating, primera_vez_visto)
                    VALUES (:titulo, :link, :rating, :ahora)
                    ON CONFLICT(titulo) DO NOTHING
                    """,
                    {
                        "titulo": titulo,
                        "link": libro.get("link"),
                        "rating": libro.get("rating"),
                        "ahora": ahora,
                    },
                )

                # Obtener el id del libro (existente o recién insertado)
                fila = con.execute(
                    "SELECT id FROM libros WHERE titulo = ?", (titulo,)
                ).fetchone()
                libro_id = fila["id"]

                # Snapshot de precio: siempre se inserta, nunca se actualiza
                con.execute(
                    """
                    INSERT INTO historial_precios (libro_id, precio, disponibilidad, fecha)
                    VALUES (?, ?, ?, ?)
                    """,
                    (libro_id, libro.get("precio"), libro.get("disponibilidad"), ahora),
                )
                snapshots_insertados += 1

        logger.info(
            "Snapshot guardado: %d registros en historial_precios (db: %s)",
            snapshots_insertados,
            ruta_db,
        )
        return snapshots_insertados

    except sqlite3.Error as e:
        logger.error("Error al guardar snapshot: %s", e)
        raise


def obtener_libros_con_precio_actual(ruta_db: str = "precios.db") -> list[dict]:
    """
    Devuelve cada libro con el precio de su snapshot más reciente.

    Returns:
        Lista de dicts con claves: id, titulo, link, rating,
        primera_vez_visto, precio_actual, disponibilidad, ultima_actualizacion.
    """
    sql = """
    SELECT
        l.id,
        l.titulo,
        l.link,
        l.rating,
        l.primera_vez_visto,
        h.precio        AS precio_actual,
        h.disponibilidad,
        h.fecha         AS ultima_actualizacion
    FROM libros l
    JOIN historial_precios h ON h.libro_id = l.id
    -- Subconsulta para quedarse solo con el snapshot más reciente de cada libro
    WHERE h.fecha = (
        SELECT MAX(fecha)
        FROM historial_precios
        WHERE libro_id = l.id
    )
    ORDER BY l.titulo
    """
    try:
        with _conectar(ruta_db) as con:
            filas = con.execute(sql).fetchall()
        return [dict(fila) for fila in filas]
    except sqlite3.Error as e:
        logger.error("Error al obtener libros con precio actual: %s", e)
        raise


def obtener_historial_libro(libro_id: int, ruta_db: str = "precios.db") -> list[dict]:
    """
    Devuelve todos los snapshots de precio de un libro, del más viejo al más nuevo.

    Args:
        libro_id: ID del libro en la tabla `libros`.
        ruta_db: Ruta al archivo SQLite.

    Returns:
        Lista de dicts con claves: id, libro_id, precio, disponibilidad, fecha.
    """
    sql = """
    SELECT id, libro_id, precio, disponibilidad, fecha
    FROM historial_precios
    WHERE libro_id = ?
    ORDER BY fecha ASC
    """
    try:
        with _conectar(ruta_db) as con:
            filas = con.execute(sql, (libro_id,)).fetchall()
        return [dict(fila) for fila in filas]
    except sqlite3.Error as e:
        logger.error("Error al obtener historial del libro %d: %s", libro_id, e)
        raise


def detectar_cambios_precio(ruta_db: str = "precios.db") -> list[dict]:
    """
    Compara los dos últimos snapshots de cada libro y devuelve los que
    tuvieron variación de precio.

    Returns:
        Lista de dicts con claves: libro_id, titulo, precio_anterior,
        precio_nuevo, diferencia (precio_nuevo - precio_anterior).
        Lista vacía si no hay cambios o si algún libro tiene menos de 2 snapshots.
    """
    # CTE que numera los snapshots por libro, del más reciente (1) al más viejo
    sql = """
    WITH snapshots_numerados AS (
        SELECT
            h.libro_id,
            h.precio,
            h.fecha,
            ROW_NUMBER() OVER (PARTITION BY h.libro_id ORDER BY h.fecha DESC) AS orden
        FROM historial_precios h
    )
    SELECT
        l.id            AS libro_id,
        l.titulo,
        s_ant.precio    AS precio_anterior,
        s_nuevo.precio  AS precio_nuevo,
        (s_nuevo.precio - s_ant.precio) AS diferencia
    FROM libros l
    JOIN snapshots_numerados s_nuevo ON s_nuevo.libro_id = l.id AND s_nuevo.orden = 1
    JOIN snapshots_numerados s_ant   ON s_ant.libro_id   = l.id AND s_ant.orden   = 2
    WHERE s_nuevo.precio != s_ant.precio
    ORDER BY ABS(s_nuevo.precio - s_ant.precio) DESC
    """
    try:
        with _conectar(ruta_db) as con:
            filas = con.execute(sql).fetchall()
        cambios = [dict(fila) for fila in filas]
        if cambios:
            logger.info("Cambios de precio detectados: %d libro(s)", len(cambios))
        else:
            logger.info("Sin cambios de precio respecto al snapshot anterior.")
        return cambios
    except sqlite3.Error as e:
        logger.error("Error al detectar cambios de precio: %s", e)
        raise


# ── Prueba rápida ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from scraper import extraer_libros

    RUTA_DB = "precios.db"
    PAGINAS = 2

    # 1. Inicializar (crea las tablas si no existen)
    inicializar_db(RUTA_DB)

    # 2. Extraer libros del scraper
    print(f"\nExtrayendo {PAGINAS} página(s) de books.toscrape.com...\n")
    libros = extraer_libros(paginas=PAGINAS)
    print(f"Libros extraídos por el scraper: {len(libros)}\n")

    # 3. Guardar snapshot
    insertados = guardar_snapshot(libros, RUTA_DB)
    print(f"Snapshots insertados en historial_precios: {insertados}\n")

    # 4. Listar libros con precio actual
    catalogo = obtener_libros_con_precio_actual(RUTA_DB)
    print(f"Libros en la base de datos (con último precio):\n")

    ANCHO = 38
    print(f"{'─' * 62}")
    print(f"  {'ID':>3}  {'TÍTULO':<{ANCHO}} {'PRECIO':>7}  {'RATING':>6}")
    print(f"{'─' * 62}")
    for libro in catalogo:
        titulo_corto = libro["titulo"][:ANCHO]
        precio_fmt = f"£{libro['precio_actual']:.2f}"
        estrellas = "★" * libro["rating"] + "☆" * (5 - libro["rating"])
        print(f"  {libro['id']:>3}  {titulo_corto:<{ANCHO}} {precio_fmt:>7}  {estrellas}")
    print(f"{'─' * 62}")
    print(f"\nTotal en DB: {len(catalogo)} libro(s)\n")

    # 5. Mostrar cambios de precio (útil a partir de la segunda corrida)
    cambios = detectar_cambios_precio(RUTA_DB)
    if cambios:
        print("Cambios de precio detectados:")
        for c in cambios:
            signo = "+" if c["diferencia"] > 0 else ""
            print(f"  [{c['libro_id']}] {c['titulo'][:40]}: "
                  f"£{c['precio_anterior']:.2f} → £{c['precio_nuevo']:.2f} "
                  f"({signo}{c['diferencia']:.2f})")
    else:
        print("Sin cambios de precio (normal en la primera corrida).")
    print()
