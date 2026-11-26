#!/usr/bin/env python3
"""Графики по samples.csv от K1/K1C логгера.

Использование:
    python3 plot.py /путь/к/samples.csv

Зависимость: matplotlib (только она, без pandas).
Результат: <имя_csv>_plot.png рядом с входным файлом.
"""
import csv
import json
import os
import sys
from datetime import datetime

try:
    import matplotlib
    matplotlib.use('Agg')  # без GUI, чтобы работало в ssh/терминале
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


def drv_flags(rows):
    """Список (index, kind, extruder_velocity) для флагов ola/olb/ot/otpw.

    Учтены три формы поля extruder_drv_status в CSV:
      - обычный JSON-объект:  {"cs_actual": 23}
      - литерал null:         null          -> json.loads даёт None
      - пустая строка:        ""            -> отсекается if not raw
    Поэтому после json.loads обязательна проверка isinstance(obj, dict).
    """
    ext = column(rows, 'live_extruder_velocity')
    out = []
    for i, r in enumerate(rows):
        raw = r.get('extruder_drv_status', '')
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
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
        if kinds:
            out.append((i, '+'.join(kinds), ext[i] if ext[i] is not None else 0))
    return out


def median(values):
    v = sorted(x for x in values if x is not None)
    return v[len(v) // 2] if v else None


# ---------- отрисовка ----------

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

    flags = drv_flags(rows)
    baseline = median([x for x in rpm if x is not None and x > 1000])

    fig, axes = plt.subplots(5, 1, figsize=(14, 13), sharex=True)
    title = rows[0].get('filename') or os.path.basename(out_path)
    fig.suptitle(f'K1/K1C print analysis — {title}', fontweight='bold')

    # 1. Сопло
    ax = axes[0]
    ax.plot(t, nozzle, 'b-', lw=1.5, label='nozzle')
    ax.plot(t, target, 'r--', lw=1, label='target')
    if target and target[0]:
        ax.axhspan(target[0] - 1, target[0] + 1, alpha=0.1, color='green')
    ax.set_ylabel('°C')
    ax.set_title('Nozzle temperature')
    ax.legend(loc='upper right')
    ax.grid(alpha=0.3)
    yv = [v for v in nozzle + target if v is not None]
    if yv:
        ax.set_ylim(min(yv) - 3, max(yv) + 3)

    # 2. Вентилятор хотэнда
    ax = axes[1]
    ax.plot(t, rpm, 'g-', lw=1.5, label='hotend fan RPM')
    if baseline:
        ax.axhline(baseline, color='k', ls=':', label=f'median {baseline:.0f}')
        ax.axhline(baseline * 0.7, color='r', ls='--', label=f'70% = {baseline * 0.7:.0f}')
        ax.axhspan(baseline * 0.7, baseline * 1.1, alpha=0.1, color='green')
    ax.set_ylabel('RPM')
    ax.set_title('Hotend fan RPM (heater_fan hotend_fan)')
    ax.legend(loc='lower right')
    ax.grid(alpha=0.3)

    # 3. Кулеры
    ax = axes[2]
    ax.plot(t, part, lw=2, label='part fan (model_fan)')
    ax.plot(t, aux, lw=2, label='aux fan (side_fan)')
    ax.plot(t, chfan, lw=2, label='chamber fan (chassis_fan)')
    ax.set_ylabel('%')
    ax.set_ylim(-5, 105)
    ax.set_title('Cooling fans')
    ax.legend(loc='center right')
    ax.grid(alpha=0.3)

    # 4. Камера / плата / стол
    ax = axes[3]
    ax.plot(t, chamber, color='orange', lw=1.5, label='chamber')
    ax.plot(t, board, color='purple', lw=1.5, label='board')
    ax2 = ax.twinx()
    ax2.plot(t, bed, color='brown', lw=1.5, ls='--', label='bed')
    ax.set_ylabel('°C (chamber, board)')
    ax2.set_ylabel('°C (bed)')
    ax.set_title('Chamber / board / bed temperatures')
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc='center right')
    ax.grid(alpha=0.3)

    # 5. Скорость экструзии + флаги драйвера
    ax = axes[4]
    ax.plot(t, ext_v, 'b-', lw=1.2, label='extruder velocity')
    if flags:
        for i, kind, val in flags:
            ax.scatter(t[i], val, color='red', s=110, zorder=5)
            ax.annotate(kind, (t[i], val), xytext=(6, 6),
                        textcoords='offset points', color='red', fontsize=9)
        ax.scatter([], [], color='red', s=110, label='drv_status flag (ola/olb/ot/otpw)')
    ax.set_ylabel('mm/s')
    ax.set_xlabel('время от старта, мин')
    ax.set_title('Extruder velocity + TMC2209 status flags')
    ax.legend(loc='upper right')
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=130)
    plt.close(fig)


# ---------- main ----------

def main():
    if len(sys.argv) < 2:
        sys.exit('Использование: python3 plot.py /путь/к/samples.csv')
    csv_path = os.path.expanduser(sys.argv[1])
    if not os.path.isfile(csv_path):
        sys.exit(f'Файл не найден: {csv_path}')

    rows = load_csv(csv_path)
    if not rows:
        sys.exit(f'Пустой CSV: {csv_path}')

    out_path = os.path.splitext(csv_path)[0] + '_plot.png'
    make_plot(rows, out_path)

    n = len(rows)
    print(f'Строк в CSV: {n}')
    print(f'Готово: {out_path}')
    print(f'Открыть: open "{out_path}"')


if __name__ == '__main__':
    main()