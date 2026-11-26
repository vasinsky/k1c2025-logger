#!/usr/bin/env python3
"""Графики по samples.csv от K1/K1C логгера.
Использование:
python3 plot-full.py /путь/к/samples.csv
Зависимость: matplotlib (только она, без pandas).
Результат:
  <имя_csv>_plot-full.png   — 10 временных рядов
  <имя_csv>_xy.png          — квадратная карта траектории XY с наложением флагов
  <имя_csv>_layers.png      — послойная структура печати
  <имя_csv>_extruder.png    — детальный график экструдера (ретракты + расход)
  <имя_csv>_thermal.png     — тепловая карта температуры сопла в координатах XY
"""
import csv
import json
import os
import statistics
import sys
from datetime import datetime
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit(
        'Нужен matplotlib. Установите одним из способов:\n'
        '  python3 -m venv ~/.venv && source ~/.venv/bin/activate && pip install matplotlib\n'
        '  brew install matplotlib\n'
        '  pip install -i https://pypi.tuna.tsinghua.edu.cn/simple matplotlib'
    )


# ---------- разбор CSV ----------
def fnum(v):
    """Строка -> float или None."""
    if v is None:
        return None
    v = v.strip()
    if v in ('', 'None', 'nan', 'NaN'):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def iso_to_ts(s):
    """ISO-время -> epoch-секунды, или None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def column(rows, name, scale=1.0):
    """Колонка как список float/None. scale — умножить (например, 100 для долей в %)."""
    out = []
    for r in rows:
        v = fnum(r.get(name))
        out.append(v * scale if v is not None else None)
    return out


def time_axis(rows):
    """Ось X в минутах от первого сэмпла. Если время битое — по индексу."""
    t0 = iso_to_ts(rows[0].get('timestamp', ''))
    if t0 is None:
        return [i / 60.0 for i in range(len(rows))]
    out = []
    for i, r in enumerate(rows):
        ts = iso_to_ts(r.get('timestamp', ''))
        out.append((ts - t0) / 60.0 if ts is not None else i / 60.0)
    return out


def drv_flags_series(rows):
    """Список kinds по каждой строке CSV: '' если флагов нет, 'ola+olb' если есть."""
    out = []
    for r in rows:
        raw = r.get('extruder_drv_status', '')
        if not raw:
            out.append('')
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            out.append('')
            continue
        if not isinstance(obj, dict):
            out.append('')
            continue
        kinds = []
        if obj.get('ola'):
            kinds.append('ola')
        if obj.get('olb'):
            kinds.append('olb')
        if obj.get('ot'):
            kinds.append('ot')
        if obj.get('otpw'):
            kinds.append('otpw')
        out.append('+'.join(kinds))
    return out


def median(values):
    v = sorted(x for x in values if x is not None)
    return v[len(v) // 2] if v else None


def short_title(rows, out_path):
    title = rows[0].get('filename') or os.path.basename(out_path)
    return title[:87] + '...' if len(title) > 90 else title


# ---------- 1. Основной стек: 10 временных рядов ----------
def make_plot(rows, out_path):
    t = time_axis(rows)

    nozzle  = column(rows, 'nozzle_c')
    target  = column(rows, 'nozzle_target_c')
    rpm     = column(rows, 'hotend_fan_rpm')
    part    = column(rows, 'part_fan', 100)
    aux     = column(rows, 'aux_fan', 100)
    chfan   = column(rows, 'chamber_fan', 100)
    chamber = column(rows, 'chamber_c')
    board   = column(rows, 'mcu_c')
    bed     = column(rows, 'bed_c')
    ext_v   = column(rows, 'live_extruder_velocity')
    baseline = median([x for x in rpm if x is not None and x > 1000])

    heater_power = column(rows, 'heater_power')
    head_v       = column(rows, 'live_velocity')
    ext_current  = column(rows, 'extruder_current')
    ext_hold     = column(rows, 'extruder_hold_current')
    drv_temp     = column(rows, 'driver_temperature')
    sys_load     = column(rows, 'system_load')
    mem_avail    = column(rows, 'mem_available')
    speed_f      = column(rows, 'speed_factor', 100)
    extrude_f    = column(rows, 'extrude_factor', 100)
    progress     = column(rows, 'progress', 100)
    kinds_series = drv_flags_series(rows)

    fig, axes = plt.subplots(10, 1, figsize=(15, 26), sharex=True)
    fig.suptitle(f'K1/K1C print analysis — {short_title(rows, out_path)}',
                 fontweight='bold', fontsize=13)

    # 1. Сопло
    ax = axes[0]
    ax.plot(t, nozzle, 'b-', lw=1.5, label='nozzle')
    ax.plot(t, target, 'r--', lw=1, label='target')
    if target and target[0]:
        ax.axhspan(target[0] - 1, target[0] + 1, alpha=0.1, color='green')
    ax.set_ylabel('°C')
    ax.set_title('1. Nozzle temperature')
    ax.legend(loc='upper right')
    ax.grid(alpha=0.3)
    yv = [v for v in nozzle + target if v is not None]
    if yv:
        ax.set_ylim(min(yv) - 3, max(yv) + 3)

    # 2. Мощность нагревателя
    ax = axes[1]
    ax.plot(t, heater_power, 'r-', lw=1.2, label='heater power (0..1)')
    ax.axhline(1.0, color='gray', ls=':', lw=0.7)
    ax.axhline(0.0, color='gray', ls=':', lw=0.7)
    ax.set_ylabel('power')
    ax.set_ylim(-0.05, 1.05)
    ax.set_title('2. Heater power — PID regulation quality')
    ax.legend(loc='upper right')
    ax.grid(alpha=0.3)

    # 3. Вентилятор хотэнда
    ax = axes[2]
    ax.plot(t, rpm, 'g-', lw=1.5, label='hotend fan RPM')
    if baseline:
        ax.axhline(baseline, color='k', ls=':', label=f'median {baseline:.0f}')
        ax.axhline(baseline * 0.7, color='r', ls='--', label=f'70% = {baseline * 0.7:.0f}')
        ax.axhspan(baseline * 0.7, baseline * 1.1, alpha=0.1, color='green')
    ax.set_ylabel('RPM')
    ax.set_title('3. Hotend fan RPM')
    ax.legend(loc='lower right')
    ax.grid(alpha=0.3)

    # 4. Кулеры
    ax = axes[3]
    ax.plot(t, part, lw=2, label='part fan (model_fan)')
    ax.plot(t, aux, lw=2, label='aux fan (side_fan)')
    ax.plot(t, chfan, lw=2, label='chamber fan (chassis_fan)')
    ax.set_ylabel('%')
    ax.set_ylim(-5, 105)
    ax.set_title('4. Cooling fans')
    ax.legend(loc='center right')
    ax.grid(alpha=0.3)

    # 5. Камера / плата / стол
    ax = axes[4]
    ax.plot(t, chamber, color='orange', lw=1.5, label='chamber')
    ax.plot(t, board, color='purple', lw=1.5, label='board')
    ax2 = ax.twinx()
    ax2.plot(t, bed, color='brown', lw=1.5, ls='--', label='bed')
    ax.set_ylabel('°C (chamber, board)')
    ax2.set_ylabel('°C (bed)')
    ax.set_title('5. Chamber / board / bed temperatures')
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc='center right')
    ax.grid(alpha=0.3)

    # 6. Скорость головы + экструдера
    ax = axes[5]
    ax.plot(t, head_v, 'b-', lw=1.2, label='head velocity (mm/s)')
    ax.plot(t, ext_v, 'g-', lw=1.2, label='extruder velocity (mm/s)')
    ax.set_ylabel('mm/s')
    ax.set_title('6. Motion: head velocity + extruder velocity')
    ax.legend(loc='upper right')
    ax.grid(alpha=0.3)

    # 7. Ток экструдера + температура драйвера
    ax = axes[6]
    ax.plot(t, ext_current, 'b-', lw=1.3, label='run current (A)')
    if any(v is not None for v in ext_hold):
        ax.plot(t, ext_hold, 'b--', lw=1, alpha=0.7, label='hold current (A)')
    ax.set_ylabel('A')
    ax.set_ylim(bottom=0)
    ax.set_title('7. Extruder: motor current + TMC2209 driver temperature')
    ax.grid(alpha=0.3)
    ax2 = ax.twinx()
    ax2.plot(t, drv_temp, 'r-', lw=1.3, label='driver temp (°C)')
    ax2.axhline(70, color='red', ls=':', lw=0.8, alpha=0.6)
    ax2.axhline(85, color='darkred', ls='--', lw=0.8, alpha=0.6, label='overheat threshold')
    ax2.set_ylabel('°C')
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc='upper right')

    # 8. Флаги драйвера
    ax = axes[7]
    flag_y = [1 if k else 0 for k in kinds_series]
    ax.step(t, flag_y, where='post', color='red', lw=1.5)
    ax.fill_between(t, 0, flag_y, step='post', alpha=0.3, color='red')
    ax.set_ylim(-0.15, 1.5)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(['no fault', 'fault'])
    ax.set_ylabel('flag')
    ax.set_title('8. TMC2209 fault flags (ola=stall A, olb=stall B, ot=overtemp, otpw=overtemp prewarn)')
    ax.grid(alpha=0.3)
    for i in range(len(kinds_series)):
        if kinds_series[i] and (i == 0 or not kinds_series[i - 1]):
            ax.annotate(kinds_series[i], (t[i], 1),
                        xytext=(3, 8), textcoords='offset points',
                        color='red', fontsize=8, fontweight='bold')

    # 9. Система: CPU + память
    ax = axes[8]
    ax.plot(t, sys_load, 'purple', lw=1.3, label='system load')
    ax.set_ylabel('load')
    ax.set_ylim(bottom=0)
    ax.set_title('9. System: CPU load + memory available')
    ax.grid(alpha=0.3)
    ax2 = ax.twinx()
    ax2.plot(t, mem_avail, 'orange', lw=1.3, label='memory available (bytes)')
    ax2.set_ylabel('bytes')
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc='upper right', fontsize=8)

    # 10. Факторы + прогресс
    ax = axes[9]
    ax.plot(t, speed_f, 'g-', lw=1.2, label='speed factor %')
    ax.plot(t, extrude_f, 'b-', lw=1.2, label='extrude factor %')
    ax.plot(t, progress, 'k--', lw=1, alpha=0.7, label='progress %')
    ax.set_ylabel('%')
    ax.set_ylim(-5, 110)
    ax.set_title('10. Speed / extrude factors + print progress')
    ax.legend(loc='center right')
    ax.grid(alpha=0.3)
    ax.set_xlabel('время от старта, мин')

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


# ---------- 2. XY траектория с наложением флагов ----------
def make_xy_plot(rows, out_path):
    x_vals = column(rows, 'x')
    y_vals = column(rows, 'y')
    v_vals = column(rows, 'live_velocity')
    kinds  = drv_flags_series(rows)

    valid = [(x, y, v) for x, y, v in zip(x_vals, y_vals, v_vals)
             if x is not None and y is not None and v is not None]

    fig, ax = plt.subplots(figsize=(11, 11))
    fig.suptitle(f'XY trajectory — {short_title(rows, out_path)}',
                 fontweight='bold', fontsize=13)

    if valid:
        xs, ys, vs = zip(*valid)
        sc = ax.scatter(xs, ys, c=vs, cmap='viridis', s=6, alpha=0.8)
        fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04).set_label('live velocity (mm/s)')

        stall_pts = [(x_vals[i], y_vals[i]) for i in range(len(rows))
                     if kinds[i] and 'ot' not in kinds[i]
                     and x_vals[i] is not None and y_vals[i] is not None]
        overtemp_pts = [(x_vals[i], y_vals[i]) for i in range(len(rows))
                        if 'ot' in kinds[i]
                        and x_vals[i] is not None and y_vals[i] is not None]

        if stall_pts:
            sx, sy = zip(*stall_pts)
            ax.scatter(sx, sy, marker='x', s=90, c='red', lw=2,
                       label=f'stallGuard ola/olb ({len(sx)} шт)', zorder=6)
        if overtemp_pts:
            ox, oy = zip(*overtemp_pts)
            ax.scatter(ox, oy, marker='s', s=110, facecolors='none',
                       edgecolors='darkorange', lw=2,
                       label=f'overtemp ot ({len(ox)} шт)', zorder=6)

        ax.axhline(0, color='gray', ls=':', lw=0.8)
        ax.axhline(220, color='gray', ls=':', lw=0.8)
        ax.axvline(0, color='gray', ls=':', lw=0.8)
        ax.axvline(220, color='gray', ls=':', lw=0.8)
        ax.set_xlim(-5, 225)
        ax.set_ylim(-5, 225)
        ax.legend(loc='upper right', fontsize=10)
    else:
        ax.text(0.5, 0.5, 'Нет данных координат XY', ha='center',
                va='center', transform=ax.transAxes)

    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_aspect('equal', adjustable='box')
    ax.grid(alpha=0.3)
    ax.set_title('Крестик = экструдер клинил в этой точке. '
                 'Красные крестики в одной зоне = локальная проблема; '
                 'размазаны = ложный stallGuard от travel', fontsize=10)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


# ---------- 3. Послойная структура ----------
def make_layer_plot(rows, out_path):
    """Z-высота + средняя скорость по каждому слою + длительность слоя."""
    t = time_axis(rows)
    z_vals = column(rows, 'z')
    v_vals = column(rows, 'live_velocity')

    valid = [(t[i], z_vals[i], v_vals[i]) for i in range(len(rows))
             if z_vals[i] is not None and v_vals[i] is not None]

    if not valid:
        print('Нет данных Z/velocity для графика слоёв')
        return

    # Группируем по Z с точностью 0.01 мм
    layers = {}
    for tt, z, v in valid:
        key = round(z, 2)
        layers.setdefault(key, {'times': [], 'velocities': []})
        layers[key]['times'].append(tt)
        layers[key]['velocities'].append(v)

    sorted_z = sorted(layers.keys())
    layer_starts = [min(layers[z]['times']) for z in sorted_z]
    layer_ends   = [max(layers[z]['times']) for z in sorted_z]
    layer_durs   = [e - s for s, e in zip(layer_starts, layer_ends)]
    layer_avg_v  = [statistics.mean(layers[z]['velocities']) for z in sorted_z]

    fig, ax1 = plt.subplots(figsize=(15, 8))
    fig.suptitle(f'Layer structure — {short_title(rows, out_path)}',
                 fontweight='bold', fontsize=13)

    # Z-высота ступенчатой линией (левая ось)
    ax1.step(layer_starts, sorted_z, where='post', color='blue', lw=2, label='Z height (mm)')
    ax1.set_xlabel('время от старта, мин')
    ax1.set_ylabel('Z height (mm)', color='blue')
    ax1.tick_params(axis='y', labelcolor='blue')
    ax1.grid(alpha=0.3)

    # Средняя скорость по слою как бары (правая ось)
    ax2 = ax1.twinx()
    ax2.bar(layer_starts, layer_avg_v, width=[d * 0.9 for d in layer_durs],
            alpha=0.5, color='green', label='avg velocity per layer (mm/s)')
    ax2.set_ylabel('avg velocity (mm/s)', color='green')
    ax2.tick_params(axis='y', labelcolor='green')

    # Подпись: количество слоёв и общая высота
    total_h = max(sorted_z) - min(sorted_z) if sorted_z else 0
    ax1.text(0.02, 0.95,
             f'Слоёв: {len(sorted_z)}  |  Высота: {total_h:.2f} мм  |  '
             f'Средняя скорость: {statistics.mean(layer_avg_v):.0f} мм/с',
             transform=ax1.transAxes, fontsize=10, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


# ---------- 4. Детальный график экструдера ----------
def make_extruder_plot(rows, out_path):
    """Скорость экструдера (подача/ретракт) + расход филамента."""
    t = time_axis(rows)
    ext_v    = column(rows, 'live_extruder_velocity')
    filament = column(rows, 'filament_used')

    fig, ax1 = plt.subplots(figsize=(15, 6))
    fig.suptitle(f'Extruder detail — {short_title(rows, out_path)}',
                 fontweight='bold', fontsize=13)

    # Скорость экструдера: синий = подача, красный = ретракт
    colors = ['red' if v < 0 else 'blue' for v in ext_v]
    ax1.scatter(t, ext_v, c=colors, s=2, alpha=0.5, label='extruder velocity')
    ax1.axhline(0, color='black', ls='-', lw=0.5)
    ax1.set_xlabel('время от старта, мин')
    ax1.set_ylabel('extruder velocity (mm/s)')
    ax1.grid(alpha=0.3)

    # Счётчик ретрактов
    retract_count = sum(1 for v in ext_v if v is not None and v < 0)
    ax1.text(0.02, 0.95, f'Ретрактов: {retract_count}',
             transform=ax1.transAxes, fontsize=10, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.5))

    # Расход филамента (правая ось)
    if any(v is not None for v in filament):
        ax2 = ax1.twinx()
        ax2.plot(t, filament, color='green', lw=1.5, label='filament used (mm)')
        ax2.set_ylabel('filament used (mm)', color='green')
        ax2.tick_params(axis='y', labelcolor='green')
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
    else:
        ax1.legend(loc='upper right')

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


# ---------- 5. Тепловая карта температуры сопла в координатах XY ----------
def make_thermal_map(rows, out_path):
    """Тепловая карта температуры сопла в координатах XY.
    Цветовая шкала: синий = недогрев, зелёный = норма, красный = перегрев."""
    x_vals = column(rows, 'x')
    y_vals = column(rows, 'y')
    nozzle = column(rows, 'nozzle_c')
    target = column(rows, 'nozzle_target_c')

    valid = [(x, y, n) for x, y, n in zip(x_vals, y_vals, nozzle)
             if x is not None and y is not None and n is not None]

    if not valid:
        print('Нет данных XY/temperature для тепловой карты')
        return

    xs, ys, temps = zip(*valid)

    # Целевая температура для нормировки цветовой шкалы
    tgt = next((v for v in target if v is not None), 220)
    vmin = tgt - 5
    vmax = tgt + 5

    fig, ax = plt.subplots(figsize=(11, 11))
    fig.suptitle(f'Thermal map — {short_title(rows, out_path)}',
                 fontweight='bold', fontsize=13)

    # RdYlGn_r: красный=горячо, зелёный=норма, синий=холодно
    sc = ax.scatter(xs, ys, c=temps, cmap='RdYlGn_r', s=6, alpha=0.8,
                    vmin=vmin, vmax=vmax)
    cbar = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('nozzle temperature (°C)')

    # Рамка стола K1C = 220x220
    ax.axhline(0, color='gray', ls=':', lw=0.8)
    ax.axhline(220, color='gray', ls=':', lw=0.8)
    ax.axvline(0, color='gray', ls=':', lw=0.8)
    ax.axvline(220, color='gray', ls=':', lw=0.8)
    ax.set_xlim(-5, 225)
    ax.set_ylim(-5, 225)

    # Статистика
    avg_temp = statistics.mean(temps)
    min_temp = min(temps)
    max_temp = max(temps)
    deviation = max_temp - min_temp
    ax.text(0.02, 0.95,
            f'Средняя: {avg_temp:.1f}°C  |  Мин: {min_temp:.1f}°C  |  '
            f'Макс: {max_temp:.1f}°C  |  Разброс: {deviation:.1f}°C',
            transform=ax.transAxes, fontsize=10, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_aspect('equal', adjustable='box')
    ax.grid(alpha=0.3)
    ax.set_title('Синий = недогрев, зелёный = норма, красный = перегрев. '
                 'Разброс > 3°C = проблема с PID', fontsize=10)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


# ---------- main ----------
def main():
    if len(sys.argv) < 2:
        sys.exit('Использование: python3 plot-full.py /путь/к/samples.csv')
    csv_path = os.path.expanduser(sys.argv[1])
    if not os.path.isfile(csv_path):
        sys.exit(f'Файл не найден: {csv_path}')
    rows = load_csv(csv_path)
    if not rows:
        sys.exit(f'Пустой CSV: {csv_path}')

    base = os.path.splitext(csv_path)[0]
    out_main     = base + '_plot-full.png'
    out_xy       = base + '_xy.png'
    out_layers   = base + '_layers.png'
    out_extruder = base + '_extruder.png'
    out_thermal  = base + '_thermal.png'

    make_plot(rows, out_main)
    make_xy_plot(rows, out_xy)
    make_layer_plot(rows, out_layers)
    make_extruder_plot(rows, out_extruder)
    make_thermal_map(rows, out_thermal)

    print(f'Строк в CSV: {len(rows)}')
    print(f'Готово (временные ряды):   {out_main}')
    print(f'Готово (карта XY):         {out_xy}')
    print(f'Готово (послойная структура): {out_layers}')
    print(f'Готово (детали экструдера):   {out_extruder}')
    print(f'Готово (тепловая карта):      {out_thermal}')
    print(f'Открыть все:')
    print(f'  open "{out_main}" "{out_xy}" "{out_layers}" "{out_extruder}" "{out_thermal}"')


if __name__ == '__main__':
    main()