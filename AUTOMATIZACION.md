# Automatización del Price Tracker

El scraper puede ejecutarse de tres formas según el entorno y las necesidades.

---

## 1. Ejecución manual con `run_scraper.py`

El script más básico: corre el pipeline una vez y termina. Útil para pruebas
o para dispararlo a mano.

```bash
# Corrida con valores por defecto (5 páginas, db: precios.db)
python run_scraper.py

# Personalizar páginas y ruta de la base de datos
python run_scraper.py --paginas 10
python run_scraper.py --paginas 3 --db /ruta/a/mi_base.db

# Ver todas las opciones
python run_scraper.py --help
```

Al finalizar imprime un resumen con libros extraídos, snapshots guardados
y cambios de precio detectados. El log queda en `logs/scraper_runs.log`.

**Códigos de salida:** `0` = éxito, `1` = error. Útil para scripts que
encadenan operaciones (`&&` en bash).

---

## 2. Automatizar con cron (Linux / WSL / macOS)

Cron es el estándar para tareas periódicas en sistemas Unix. Cada línea del
crontab define una tarea con su horario.

### Configuración paso a paso

```bash
# 1. Encontrar la ruta absoluta de Python en tu entorno virtual
which python          # en Linux/Mac con venv activo
# Ejemplo: /home/usuario/Price-Tracker/.venv/bin/python

# 2. Abrir el editor de crontab
crontab -e
```

### Ejemplos de líneas para el crontab

```cron
# Formato: minuto hora día-del-mes mes día-de-la-semana comando

# Cada 6 horas (00:00, 06:00, 12:00, 18:00)
0 */6 * * * cd /home/usuario/Price-Tracker && /home/usuario/Price-Tracker/.venv/bin/python run_scraper.py --paginas 5

# Todos los días a las 8:00 AM
0 8 * * * cd /home/usuario/Price-Tracker && /home/usuario/Price-Tracker/.venv/bin/python run_scraper.py

# Cada hora (para proyectos con alta frecuencia de cambios)
0 * * * * cd /home/usuario/Price-Tracker && /home/usuario/Price-Tracker/.venv/bin/python run_scraper.py --paginas 2
```

> **Importante:** cron no activa el entorno virtual automáticamente, por eso
> se usa la ruta absoluta al intérprete de Python del venv. El `cd` al
> directorio del proyecto garantiza que los archivos relativos (`precios.db`,
> `logs/`) se creen en el lugar correcto.

### Verificar que cron está corriendo (WSL)

```bash
sudo service cron start      # iniciar el servicio
sudo service cron status     # verificar que está activo
```

### Ver el log de cron y del scraper

```bash
# Log del scraper (generado por run_scraper.py)
tail -f logs/scraper_runs.log

# Log del sistema de cron (si algo no arranca)
grep CRON /var/log/syslog
```

---

## 3. Automatizar con Task Scheduler (Windows)

Para usuarios de Windows sin WSL, Task Scheduler es el equivalente nativo.

1. Abrir **Task Scheduler** (buscarlo en el menú de inicio)
2. Clic en **Create Basic Task** (panel derecho)
3. Configurar:
   - **Name:** `PriceTracker`
   - **Trigger:** Daily → repetir cada 6 horas (o el intervalo deseado)
   - **Action:** Start a program
     - **Program:** `C:\Users\usuario\Price-Tracker\.venv\Scripts\python.exe`
     - **Arguments:** `run_scraper.py --paginas 5`
     - **Start in:** `C:\Users\usuario\Price-Tracker`
4. En **Properties → Settings**, activar "Run task as soon as possible after
   a scheduled start is missed" para recuperar corridas fallidas.

> El log quedará en `C:\Users\usuario\Price-Tracker\logs\scraper_runs.log`.

---

## 4. Scheduler autocontenido con `scheduler.py`

Alternativa a cron que no depende del sistema operativo. Un proceso Python
que mantiene su propio reloj interno. Útil en entornos donde no tenés
acceso a cron o Task Scheduler (VPS básico, contenedor Docker simple).

```bash
# Iniciar con el intervalo por defecto (cada 6 horas)
python scheduler.py

# Para testing: correr cada minuto
python scheduler.py --intervalo-minutos 1

# Personalizar todo
python scheduler.py --intervalo-minutos 120 --paginas 10 --db precios.db

# Ver opciones
python scheduler.py --help
```

Al arrancar, ejecuta una primera corrida inmediata y luego espera el
intervalo configurado. El log va al mismo archivo que `run_scraper.py`.

Para detener limpiamente: `Ctrl+C`.

Para dejarlo corriendo en segundo plano en Linux:

```bash
# Con nohup (persiste al cerrar la terminal)
nohup python scheduler.py --intervalo-minutos 360 &

# Ver el proceso
ps aux | grep scheduler.py

# Detenerlo
kill <PID>
```

---

## 5. ¿Cuándo usar cada enfoque?

| Situación | Recomendación |
|---|---|
| Servidor Linux / VPS / WSL con acceso root | **cron** — es el estándar, más robusto y no consume recursos cuando no corre |
| Windows sin WSL | **Task Scheduler** o `scheduler.py` |
| Contenedor Docker | `scheduler.py` dentro del contenedor, o un contenedor separado con cron |
| Desarrollo y pruebas locales | `run_scraper.py` manual o `scheduler.py --intervalo-minutos 1` |
| No tenés acceso al sistema operativo (hosting compartido) | `scheduler.py` como proceso en background |
| Querés alertas si la tarea falla | **cron** con `MAILTO=tu@email.com` al inicio del crontab |

### Regla general

> Si controlás el servidor → **cron**.  
> Si solo controlás el proceso Python → **`scheduler.py`**.
