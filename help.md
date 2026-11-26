# 📊 Графики диагностики K1C 2025 / K1C 2025 diagnostic plots

**[RU](#ru)** · **[EN](#en)**

---

<a id="ru"></a>

## 🇷🇺 RU: Описание графиков

### `samples_plot.png` — Быстрый взгляд

**Что показывает:** температура сопла, RPM хотэнд-вентилятора, кулеры (part / aux / chamber), камера + плата + стол, скорость экструдера + флаги TMC2209.

**Когда смотреть:** после любой печати — проверка за 30 секунд.

**Что искать:**
- осцилляции сопла >±2°C → плохой PID
- RPM хотэнда ниже 70% медианы → умирает вентилятор или забит радиатор
- красные точки `ola` / `olb` / `ot` → stallGuard или перегрев драйвера

---

### `samples_plot-full.png` — Полная диагностика (10 рядов)

**Что показывает:** всё из быстрого + мощность нагревателя PID, ток экструдера, температура драйвера TMC2209, флаги драйвера (step-plot), загрузка CPU, память, speed/extrude factors, прогресс.

**Когда смотреть:** когда есть проблема — щелчки, пропуски экструзии, артефакты, перегрев.

**Что искать:**
- `heater_power` постоянно на 1.0 → не догревает; скачет 0↔1 → плохой PID
- ток экструдера + флаги `ola/olb` → экструдер клинит
- температура драйвера >70°C → перегрев платы; >85°C → критично
- `system_load` >2.0 стабильно → Klipper тормозит, возможны артефакты

---

### `samples_xy.png` — Карта движения + StallGuard

**Что показывает:** траектория головы на столе (X/Y), цвет = скорость (синий = медленно, красный = быстро), красные крестики = координаты срабатывания stallGuard.

**Когда смотреть:** когда на графике 8 видны флаги `ola/olb` — чтобы понять, где именно клинит.

**Что искать:**
- крестики **внутри** контуров печати → реальный клин экструдера (поднять `run_current`, снизить скорость периметров)
- крестики **вне** контуров (на travel между деталями) → ложный stallGuard от резких торможений, можно игнорировать
- концентрация крестиков в одной зоне → локальная проблема (зацеп филамента, угол с резким ретрактом)

---

### `samples_layers.png` — Послойная структура

**Что показывает:** Z-высота ступенчатой линией (левая ось) + средняя скорость каждого слоя барами (правая ось).

**Когда смотреть:** для понимания структуры печати и поиска аномальных слоёв.

**Что искать:**
- резкие провалы скорости на конкретных слоях → мосты, навесы, первые слои (это норма)
- хаотичные скачки скорости без логики → проблема слайсера (нереалистичные ускорения)
- слишком длинные «плато» на одном Z → застревание на слое (possible z-hop issue)

---

### `samples_extruder.png` — Детали экструдера

**Что показывает:** скорость экструдера по времени (синие точки = подача, красные ниже нуля = ретракты) + накопленный расход филамента (зелёная линия).

**Когда смотреть:** при подозрении на проблемы с экструзией — пропуски, недоэкструзия, слишком агрессивные ретракты.

**Что искать:**
- счётчик ретрактов в плашке (для мелкой геометрии норма 200–400 за печать; если 3 — артефакт семплирования)
- длинные периоды нулевой скорости экструдера при движении головы → travel без ретракта (possible stringing)
- резкие пики подачи >10 мм/с → возможный клин или slip
- ступеньки на зелёной линии расхода → пропуски экструзии

---

### `samples_thermal.png` — Тепловая карта сопла

**Что показывает:** температура сопла в координатах XY, цвет: синий = недогрев, зелёный = норма, красный = перегрев. В плашке — статистика (средняя / мин / макс / разброс).

**Когда смотреть:** для проверки качества PID и влияния обдува на термистор.

**Что искать:**
- равномерный зелёный → ✅ PID идеальный
- синие пятна в углах печати → обдув модели задувает на термистор (добавить термокожух или снизить обдув)
- красные пятна в центре → PID слишком агрессивный (перегрев)
- хаотичные цвета по всей площади → PID разбалансирован → `PID_CALIBRATE`
- **разброс >3°C** (видно в плашке) → требует калибровки PID

---

### 🔎 Порядок просмотра

1. `samples_plot.png` — всё ок? закрыть тему.
2. Есть проблема → `samples_plot-full.png` — ищем виновника.
3. Видны флаги `ola/olb` → `samples_xy.png` — где клинит.
4. Подозрение на слои → `samples_layers.png`.
5. Подозрение на экструзию → `samples_extruder.png`.
6. Подозрение на PID / обдув → `samples_thermal.png`.

---

<a id="en"></a>

## 🇬🇧 EN: Plots description

### `samples_plot.png` — Quick glance

**What it shows:** nozzle temperature, hotend fan RPM, cooling fans (part / aux / chamber), chamber + board + bed, extruder velocity + TMC2209 flags.

**When to use:** after any print — 30-second sanity check.

**What to look for:**
- nozzle oscillation >±2°C → bad PID
- hotend fan RPM below 70% of median → fan dying or heatsink clogged
- red dots `ola` / `olb` / `ot` → stallGuard or driver overheat

---

### `samples_plot-full.png` — Full diagnostics (10 time series)

**What it shows:** everything from quick + heater PID power, extruder current, TMC2209 driver temperature, driver flags (step plot), CPU load, memory, speed/extrude factors, progress.

**When to use:** when there is a problem — clicks, skipped extrusion, artifacts, overheating.

**What to look for:**
- `heater_power` stuck at 1.0 → not heating enough; jumping 0↔1 → bad PID
- extruder current + `ola/olb` flags → extruder is stalling
- driver temperature >70°C → board overheating; >85°C → critical
- `system_load` >2.0 sustained → Klipper is lagging, artifacts possible

---

### `samples_xy.png` — Motion map + StallGuard

**What it shows:** head trajectory on the bed (X/Y), color = speed (blue = slow, red = fast), red crosses = stallGuard trigger coordinates.

**When to use:** when plot 8 shows `ola/olb` flags — to see exactly where it stalls.

**What to look for:**
- crosses **inside** print contours → real extruder stall (raise `run_current`, lower perimeter speed)
- crosses **outside** contours (on travel moves) → false stallGuard from hard braking, can ignore
- cluster of crosses in one zone → local problem (filament snag, sharp-angle retract)

---

### `samples_layers.png` — Layer structure

**What it shows:** Z-height as step line (left axis) + average speed per layer as bars (right axis).

**When to use:** to understand print structure and find anomalous layers.

**What to look for:**
- sharp speed drops on specific layers → bridges, overhangs, first layers (normal)
- chaotic speed jumps without logic → slicer issue (unrealistic accelerations)
- too long "plateaus" at one Z → stuck on a layer (possible z-hop issue)

---

### `samples_extruder.png` — Extruder detail

**What it shows:** extruder velocity over time (blue dots = feed, red below zero = retracts) + cumulative filament used (green line).

**When to use:** when suspecting extrusion problems — skips, underextrusion, too aggressive retracts.

**What to look for:**
- retract counter in the badge (small geometry normal 200–400 per print; if 3 — sampling artifact)
- long periods of zero extruder velocity while head moves → travel without retract (possible stringing)
- sharp feed spikes >10 mm/s → possible stall or slip
- steps on the green filament line → extrusion skips

---

### `samples_thermal.png` — Nozzle thermal map

**What it shows:** nozzle temperature in XY coordinates, color: blue = underheat, green = normal, red = overheat. Badge shows stats (avg / min / max / spread).

**When to use:** to check PID quality and fan blow effect on thermistor.

**What to look for:**
- uniform green → ✅ PID is perfect
- blue spots at print corners → part fan blows on thermistor (add thermistor shield or lower fan)
- red spots in center → PID too aggressive (overheat)
- chaotic colors all over → PID unbalanced → `PID_CALIBRATE`
- **spread >3°C** (visible in badge) → needs PID calibration

---

### 🔎 Viewing order

1. `samples_plot.png` — all OK? done.
2. Problem exists → `samples_plot-full.png` — find the culprit.
3. `ola/olb` flags visible → `samples_xy.png` — where it stalls.
4. Suspect layer issues → `samples_layers.png`.
5. Suspect extrusion issues → `samples_extruder.png`.
6. Suspect PID / fan issues → `samples_thermal.png`.
