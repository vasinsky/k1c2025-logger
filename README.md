# k1c2025-logger

**[RU: Описание](#ru)** | **[EN: Description](#en)**

Read-only telemetry logger and diagnostic plotter for Creality K1 / K1C (2025).

Бортовой самописец и диагностический анализатор для 3D-принтеров Creality K1 и K1C (2025). Работает **без root и SSH**, только через открытый порт Moonraker API (7125). Принтеру не отправляется ни одна команда — инструмент читает телеметрию.

---

<a id="ru"></a>

## RU: Описание

### Возможности

- Запись телеметрии в реальном времени, интервал от 0.5 сек
- Read-only: только GET-запросы `/printer/objects/query`, никаких POST и G-code
- Автодетект событий: stallGuard (`ola`/`olb`), перегрев драйвера (`ot`/`otpw`), падение RPM хотэнд-вентилятора, отклонение температуры сопла
- Ручные метки в процессе: `F` — сбой экструзии, `M` — заметка, `Q` — стоп записи
- Автоупаковка папки с логом в ZIP
- Два анализатора: `plot.py` (быстрый, 5 графиков в одном PNG) и `plot-full.py` (расширенный, 5 отдельных PNG)

### Установка зависимостей

`log_capture.py` — только стандартная библиотека Python 3.8+, пакеты не нужны.
`plot.py` и `plot-full.py` — нужен `matplotlib`.

macOS:

```bash
brew install python@3 matplotlib
# или через venv:
python3 -m venv ~/.venv_k1c && source ~/.venv_k1c/bin/activate && pip install matplotlib
```

Linux (Ubuntu/Debian):

```bash
sudo apt install python3 python3-pip python3-matplotlib
# или через venv:
python3 -m venv ~/.venv_k1c && source ~/.venv_k1c/bin/activate && pip install matplotlib
```

Windows (PowerShell):

```powershell
python -m venv $env:USERPROFILE\.venv_k1c
& "$env:USERPROFILE\.venv_k1c\Scripts\Activate.ps1"
pip install matplotlib
```

### Логгер: `log_capture.py`

| Аргумент | По умолчанию | Описание |
|---|---|---|
| `--host` | `192.168.1.95` | IP или URL Moonraker, напр. `192.168.0.185:7125` |
| `--output` | `./K1c2025_logs` | Родительская папка для логов |
| `--interval` | `1.0` | Интервал опроса, сек (мин. 0.5) |
| `--timeout` | `4.0` | Таймаут HTTP-запроса, сек |
| `--note` | пусто | Заметка о материале и условиях — пишется в `manifest.json` |
| `--keep-after-print` | выкл | Продолжать запись после завершения печати |
| `--duration` | `0` | Лимит записи в сек; 0 = без лимита |
| `--no-keep-awake` | выкл | Не блокировать сон Windows |
| `--no-keyboard` | выкл | Отключить горячие клавиши F/M/Q |

Горячие клавиши (в интерактивном терминале, поддерживается и русская раскладка):

- `F` / `А` — пометить сбой экструзии (принтер НЕ останавливается)
- `M` / `Ь` — пользовательская метка (открыл крышку, сменил филамент и т.п.)
- `Q` / `Й` или `Ctrl+C` — остановить только запись, печать продолжается

Когда какой интервал:

- `--interval 1.0` — обычный режим, баланс детализации и нагрузки
- `--interval 2.0` — длинные печати (несколько часов): меньше CPU на Klipper, меньше файл
- `--interval 0.5` — короткие диагностические тесты (10–30 мин): ловит быстрые всплески PID и короткие stallGuard; ниже 0.5 сек по Wi-Fi на K1C не стоит — Moonraker начнёт пропускать запросы

Примеры:

```bash
# обычная печать PLA
python3 log_capture.py --host 192.168.0.185:7125 \
  --note "PLA, 220C, крышка снята, K1C 2025" --interval 1.0

# длительная печать, запись не останавливать после завершения
python3 log_capture.py --host 192.168.0.185:7125 \
  --note "PETG, 240C, крышка закрыта" --interval 2.0 --keep-after-print

# короткий диагностический тест stallGuard, 10 минут
python3 log_capture.py --host 192.168.0.185:7125 \
  --note "Диагностика stallGuard" --interval 0.5 --duration 600
```

Структура папки `K1c2025_logs/K1-YYYYMMDD-HHMMSS-xxxx/`:

- `samples.csv` — телеметрия по строкам, вход для анализаторов
- `samples.jsonl` — сырые ответы Moonraker
- `events.jsonl` — события и алерты (stallGuard, RPM drop, метки F/M)
- `gcode.jsonl` — история G-code из `/server/gcode_store`
- `initial.json`, `manifest.json`, `summary.json` — метаданные и сводка
- `K1-....zip` — архив всей папки

### Анализаторы графиков

Быстрый, 5 subplot'ов в одном файле:

```bash
python3 plot.py /путь/к/samples.csv
# результат: samples_plot.png
```

Расширенный, 5 отдельных PNG:

```bash
python3 plot-full.py /путь/к/samples.csv
# результаты: samples_plot-full.png, samples_xy.png, samples_layers.png,
#             samples_extruder.png, samples_thermal.png
```

### Описание графиков `plot-full.py`

| Файл | Что смотреть |
|---|---|
| `*_plot-full.png` | 10 временных рядов: сопло, мощность PID, RPM, кулеры, камера/плата/стол, скорости, ток экструдера, флаги TMC, CPU, прогресс. Осцилляции >2°C — плохой PID; `system_load` >2.0 — Klipper тормозит; всплески `ola/olb` — stallGuard |
| `*_xy.png` | Траектория головы, цвет = скорость. Красные крестики — координаты срабатывания stallGuard. Внутри контуров = реальный клин экструдера; вне контуров (на travel) = ложный stallGuard от резких торможений |
| `*_layers.png` | Z-высота ступенями + средняя скорость по слоям барами. Провалы скорости = мосты/первые слои; хаотичные скачки = проблема слайсера |
| `*_extruder.png` | Скорость экструдера: синий = подача, красный ниже нуля = ретракт; зелёная линия = накопленный расход. Счётчик ретрактов в плашке |
| `*_thermal.png` | Тепловая карта сопла в XY: зелёный = норма, синий = недогрев (обдув задувает термистор), красный = перегрев. Разброс >3°C — калибровать PID |

### Ограничения

- Read-only: команды принтеру не отправляются
- `extruder_current` и `filament_used` — расчётные/запрашиваемые значения Klipper, не данные физических датчиков
- `driver_temperature` на K1C 2025 обычно пуст: Creality не отдаёт телеметрию TMC через Moonraker; перегрев драйвера виден только по флагу `ot`
- `TEST_RESONANCES` (Input Shaper) требует доступа к `/tmp/` Klipper — без root не работает; этот инструмент его не заменяет

---

<a id="en"></a>

## EN: Description

Read-only telemetry logger and diagnostic plotter for Creality K1 / K1C (2025). Works **without root or SSH**, using only the open Moonraker API port (7125). No commands are ever sent to the printer — the tool only reads telemetry.

### Features

- Real-time recording, interval from 0.5s
- Read-only: GET `/printer/objects/query` only, no POST, no G-code
- Auto-detection: stallGuard (`ola`/`olb`), driver overtemp (`ot`/`otpw`), hotend fan RPM drop, nozzle temperature deviation
- Manual markers: `F` extrusion failure, `M` user marker, `Q` stop recording (print continues)
- Auto ZIP archiving
- Two analyzers: `plot.py` (5 plots in one PNG) and `plot-full.py` (5 separate PNGs)

### Dependencies

`log_capture.py` — Python 3.8+ stdlib only.
`plot.py` / `plot-full.py` — `matplotlib` required.

macOS: `brew install python@3 matplotlib` or venv + `pip install matplotlib`.
Linux: `sudo apt install python3 python3-matplotlib` or venv.
Windows: `python -m venv .venv_k1c` then activate and `pip install matplotlib`.

### Logger arguments

| Argument | Default | Description |
|---|---|---|
| `--host` | `192.168.1.95` | Moonraker IP or URL |
| `--output` | `./K1c2025_logs` | Log parent folder |
| `--interval` | `1.0` | Sampling interval, seconds (min 0.5) |
| `--timeout` | `4.0` | HTTP timeout, seconds |
| `--note` | empty | Note about material/conditions, saved to manifest |
| `--keep-after-print` | off | Keep recording after print completes |
| `--duration` | `0` | Recording limit in seconds; 0 = unlimited |
| `--no-keep-awake` | off | Do not prevent Windows sleep |
| `--no-keyboard` | off | Disable F/M/Q hotkeys |

Hotkeys: `F` mark extrusion failure, `M` user marker, `Q`/Ctrl+C stop recording only.

Interval guidance: `1.0` default; `2.0` for long prints (less CPU, smaller file); `0.5` for short diagnostic tests (catches fast PID oscillations and brief stallGuard events). Below 0.5s over Wi-Fi on K1C is not recommended — Moonraker starts skipping queries.

Examples:

```bash
python3 log_capture.py --host 192.168.0.185:7125 --note "PLA, 220C" --interval 1.0
python3 log_capture.py --host 192.168.0.185:7125 --note "PETG, 240C" --interval 2.0 --keep-after-print
python3 log_capture.py --host 192.168.0.185:7125 --note "stallGuard test" --interval 0.5 --duration 600
```

### Plots description (`plot-full.py`)

| File | What to look for |
|---|---|
| `*_plot-full.png` | 10 time series. Temp oscillation >2°C = bad PID; `system_load` >2.0 = Klipper lag; `ola/olb` spikes = stallGuard |
| `*_xy.png` | Head trajectory colored by speed. Red X marks = stallGuard coordinates. Inside contours = real extruder stall; outside = false stallGuard from travel braking |
| `*_layers.png` | Z height + per-layer average speed. Speed dips = bridges/first layers; chaos = slicer issue |
| `*_extruder.png` | Extruder velocity (blue feed, red retracts) + cumulative filament used |
| `*_thermal.png` | Nozzle temperature map in XY. Green = OK, blue = underheat (fan blowing on thermistor), red = overheat. Spread >3°C = recalibrate PID |

### Limitations

- Read-only: no commands sent to the printer
- `extruder_current` and `filament_used` are reported/commanded values, not physical sensor data
- `driver_temperature` is typically empty on K1C 2025 (Creality does not expose TMC telemetry via Moonraker); driver overheat is visible only via the `ot` flag
- `TEST_RESONANCES` (Input Shaper) requires Klipper `/tmp/` access — not available without root; this tool does not replace it
