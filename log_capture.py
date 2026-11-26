#!/usr/bin/env python3
"""K1 / K1C (2025) Moonraker diagnostic recorder. Python 3.8+, standard library only.

GET requests only: no heating, motion, configuration changes, pause or cancellation.
F = mark extrusion failure; M = other marker; Q / Ctrl+C = stop recording only.

Object-name mappings verified on K1C 2025 via /printer/objects/list:
  heater_fan hotend_fan        -> hotend heatsink fan
  fan_generic model_fan        -> part cooling fan
  fan_generic side_fan         -> auxiliary / side fan
  fan_generic chassis_fan      -> chamber / chassis fan
  temperature_sensor chassis   -> chamber temperature
  temperature_fan main_board   -> main board temperature (used as mcu_c proxy)
Nozzle MCU temperature is not exposed on K1C; nozzle_mcu_c stays empty.
Original K1 names are kept as fallbacks so the same file still works on K1.
"""
import argparse
import csv
import ctypes
import json
import math
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

FIELDS = '''timestamp eventtime state filename print_seconds total_seconds progress display_progress layer
filament_used nozzle_c nozzle_target_c heater_power chamber_c bed_c bed_target_c
hotend_fan_command hotend_fan_power hotend_fan_rpm part_fan aux_fan chamber_fan
chamber_fan_target mcu_c nozzle_mcu_c extruder_current extruder_hold_current
driver_temperature pressure_advance smooth_time x y z e live_velocity live_extruder_velocity
max_accel max_velocity speed_factor extrude_factor absolute_coordinates absolute_extrude
system_load cpu_time mem_available extruder_drv_status'''.split()


def timestamp():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='milliseconds')


class Recorder:
    def __init__(self, args):
        self.args = args
        host = args.host.rstrip('/')
        self.base = host if '://' in host else 'http://' + host
        if urllib.parse.urlsplit(self.base).scheme not in ('http', 'https'):
            raise ValueError('Host must be an HTTP(S) Moonraker address')
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        label = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:4]
        self.folder = Path(args.output).expanduser().resolve() / ('K1-' + label)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.streams = {}
        self.last = None
        self.samples = self.errors = 0
        self.ranges = {}
        self.active_alerts = set()
        self.counts = {}
        self.baseline = deque(maxlen=20)
        self.fan_started = None
        self.target = None
        self.target_since = time.monotonic()
        self.awake = False
        self.keyboard = os.name == 'nt' and sys.stdin.isatty() and not args.no_keyboard
        self._hotend_has_tach = None  # True/False once known, None before first sample
        self.reason = 'unknown'

    def get(self, endpoint):
        # There is deliberately no method that sends POST requests or G-code.
        req = urllib.request.Request(self.base + endpoint, method='GET')
        with self.http.open(req, timeout=self.args.timeout) as response:
            return json.load(response)['result']

    def query(self, names):
        return self.get('/printer/objects/query?' + '&'.join(urllib.parse.quote(n, safe='') for n in names))

    def save_json(self, name, value):
        tmp = self.folder / (name + '.tmp')
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(str(tmp), str(self.folder / name))

    def event(self, kind, detail=None):
        item = {'timestamp': timestamp(), 'kind': kind, 'detail': detail, 'last_sample': self.last}
        self.streams['events'].write(json.dumps(item, ensure_ascii=False) + '\n')
        print('\nEVENT: {} — {}'.format(kind, detail or ''), flush=True)

    def warning(self, key, condition, detail):
        if condition and key not in self.active_alerts:
            self.active_alerts.add(key)
            self.event(key, detail)
        elif not condition and key in self.active_alerts:
            self.active_alerts.remove(key)
            self.event('recovered_' + key)

    def keys(self):
        if not self.keyboard:
            return False
        import msvcrt
        while msvcrt.kbhit():
            key = msvcrt.getwch().lower()
            if key in ('f', '\u0430'):
                self.event('USER_EXTRUSION_FAILURE', 'User marked clicking / lost extrusion. Printer was NOT paused by this recorder.')
            elif key in ('m', '\u044c'):
                self.event('USER_MARKER', 'User marker: note lid/fan/temperature changes separately.')
            elif key in ('q', '\u0439'):
                self.reason = 'user_stopped_recorder'
                return True
        return False

    def make_row(self, result):
        s = result['status']
        ps, ex = s.get('print_stats', {}), s.get('extruder', {})
        # --- K1C 2025 names first, original K1 names as fallbacks ---
        fan = s.get('heater_fan hotend_fan') or s.get('heater_fan hotend') or {}
        drv = s.get('tmc2209 extruder') or {}
        sd, th = s.get('virtual_sdcard', {}), s.get('toolhead', {})
        mo, sy, gm = s.get('motion_report', {}), s.get('system_stats', {}), s.get('gcode_move', {})
        chamber_fan = s.get('fan_generic chassis_fan') or s.get('temperature_fan chamber_fan') or {}
        part_fan_obj = s.get('fan_generic model_fan') or s.get('fan') or {}
        aux_fan_obj = s.get('fan_generic side_fan') or s.get('fan_generic auxiliary') or {}
        chamber_sensor = s.get('temperature_sensor chassis') or s.get('temperature_sensor chamber_temp') or {}
        board_sensor = s.get('temperature_fan main_board') or s.get('temperature_sensor mcu_temp') or {}
        nozzle_mcu_sensor = s.get('temperature_sensor nozzle_mcu_temp') or {}
        pos = list(th.get('position', [])) + [None] * 4
        # Remember whether the hotend fan exposes a tachometer (rpm field) at all.
        # K1C commonly has no tach on the hotend fan; skip RPM alerts in that case.
        self._hotend_has_tach = 'rpm' in fan
        return dict(
            timestamp=timestamp(), eventtime=result.get('eventtime'), state=ps.get('state'),
            filename=ps.get('filename'), print_seconds=ps.get('print_duration'), total_seconds=ps.get('total_duration'),
            progress=sd.get('progress'), display_progress=s.get('display_status', {}).get('progress'),
            layer=ps.get('info', {}).get('current_layer'), filament_used=ps.get('filament_used'),
            nozzle_c=ex.get('temperature'), nozzle_target_c=ex.get('target'), heater_power=ex.get('power'),
            chamber_c=chamber_sensor.get('temperature'),
            bed_c=s.get('heater_bed', {}).get('temperature'), bed_target_c=s.get('heater_bed', {}).get('target'),
            hotend_fan_command=fan.get('speed'), hotend_fan_power=fan.get('power'), hotend_fan_rpm=fan.get('rpm'),
            part_fan=part_fan_obj.get('speed'), aux_fan=aux_fan_obj.get('speed'),
            chamber_fan=chamber_fan.get('speed'), chamber_fan_target=chamber_fan.get('target'),
            mcu_c=board_sensor.get('temperature'),
            nozzle_mcu_c=nozzle_mcu_sensor.get('temperature'),
            extruder_current=drv.get('run_current'), extruder_hold_current=drv.get('hold_current'),
            driver_temperature=drv.get('temperature'), pressure_advance=ex.get('pressure_advance'),
            smooth_time=ex.get('smooth_time'), x=pos[0], y=pos[1], z=pos[2], e=pos[3],
            live_velocity=mo.get('live_velocity'), live_extruder_velocity=mo.get('live_extruder_velocity'),
            max_accel=th.get('max_accel'), max_velocity=th.get('max_velocity'), speed_factor=gm.get('speed_factor'),
            extrude_factor=gm.get('extrude_factor'), absolute_coordinates=gm.get('absolute_coordinates'),
            absolute_extrude=gm.get('absolute_extrude'), system_load=sy.get('sysload'), cpu_time=sy.get('cputime'),
            mem_available=sy.get('memavail'), extruder_drv_status=json.dumps(drv.get('drv_status')))

    def check(self, row, now):
        command, rpm = row['hotend_fan_command'] or 0, row['hotend_fan_rpm']
        expected = (row['nozzle_target_c'] or 0) > 0 or (row['nozzle_c'] or 0) > self.fan_threshold
        if command > .5:
            self.fan_started = self.fan_started if self.fan_started is not None else now
        else:
            self.fan_started = None
        ready = self.fan_started is not None and now - self.fan_started > 10
        if ready and rpm is not None and rpm > 1000 and len(self.baseline) < 20:
            self.baseline.append(rpm)
        baseline = statistics.median(self.baseline) if len(self.baseline) >= 20 else None
        # Only run RPM-based tests if the hotend fan actually reports a tachometer.
        has_tach = bool(self._hotend_has_tach)
        tests = [('FAN_ZERO_RPM', ready and has_tach and rpm is not None and rpm <= 0, 3),
                 ('FAN_TACH_MISSING', ready and has_tach and rpm is None, 5),
                 ('FAN_COMMAND_OFF_WHEN_EXPECTED', expected and command <= .01, 5),
                 ('FAN_RPM_DROP', ready and has_tach and baseline is not None and rpm is not None and rpm < .7 * baseline, 5)]
        for key, bad, count in tests:
            self.counts[key] = self.counts.get(key, 0) + 1 if bad else 0
            self.warning(key, self.counts[key] >= count, 'command={}, rpm={}, baseline={}'.format(command, rpm, baseline))
        if row['nozzle_target_c'] != self.target:
            self.target, self.target_since = row['nozzle_target_c'], now
        delta = (row['nozzle_c'] or 0) - (row['nozzle_target_c'] or 0)
        bad = (self.target or 0) >= 170 and now - self.target_since > 120 and abs(delta) > 5
        self.counts['temp'] = self.counts.get('temp', 0) + 1 if bad else 0
        self.warning('NOZZLE_TEMPERATURE_DEVIATION', self.counts['temp'] >= 10, 'actual={}, target={}'.format(row['nozzle_c'], self.target))
        flags = json.loads(row['extruder_drv_status']) or {}
        bad_flags = {k: v for k, v in flags.items() if v and k.lower() in ('ot', 'otpw', 's2ga', 's2gb', 's2vsa', 's2vsb')}
        self.warning('EXTRUDER_DRIVER_FAULT', bool(bad_flags), bad_flags)

    def summary(self):
        return dict(started=self.started, updated=timestamp(), reason=self.reason, samples=self.samples,
                    query_errors=self.errors, ranges=self.ranges, latest=self.last, host=self.base,
                    requested_interval=self.args.interval, active_alerts=sorted(self.active_alerts),
                    hotend_fan_has_tach=self._hotend_has_tach,
                    note='RPM is tachometer feedback; currents and filament_used are reported/commanded values. No physical flow or motor temperature sensor. Mapping adjusted for K1C 2025.')

    def run(self):
        self.started = timestamp()
        start = time.monotonic()
        print('K1/K1C diagnostic recorder — READ ONLY\nFolder: {}\nHost: {}'.format(self.folder, self.base), flush=True)
        print('F = mark failure; M = marker; Q / Ctrl+C = stop RECORDING ONLY. These keys do not stop the printer.', flush=True)
        if not self.keyboard:
            print('Keyboard markers unavailable in this terminal; use an ordinary interactive terminal for F/M/Q.', flush=True)
        try:
            if os.name == 'nt' and not self.args.no_keep_awake:
                self.awake = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
            self.streams = {name: (self.folder / filename).open('a', encoding='utf-8', buffering=1, newline='')
                            for name, filename in [('raw', 'samples.jsonl'), ('csv', 'samples.csv'),
                                                  ('events', 'events.jsonl'), ('gcode', 'gcode.jsonl')]}
            writer = csv.DictWriter(self.streams['csv'], fieldnames=FIELDS)
            writer.writeheader()
            while True:
                if self.keys(): return
                try:
                    objects = self.get('/printer/objects/list')['objects']
                    initial = self.query(objects)
                    break
                except Exception as exc:
                    self.event('CONNECTING', str(exc))
                    if time.monotonic() - start > 120:
                        self.reason = 'initial_connection_timeout'
                        return
                    time.sleep(2)
            self.save_json('initial.json', initial)
            settings = initial['status'].get('configfile', {}).get('settings', {})
            # K1C name first, K1 fallback.
            self.fan_threshold = (settings.get('heater_fan hotend_fan')
                                  or settings.get('heater_fan hotend') or {}).get('heater_temp', 40)
            dynamic = [n for n in objects if n != 'configfile' and not n.startswith('gcode_macro ')]
            self.save_json('manifest.json', dict(started=self.started, host=self.base, objects=objects,
                monitored_objects=dynamic, python=sys.version, user_note=self.args.note,
                hotkeys='F: extrusion failure, M: marker, Q/Ctrl+C: stop recorder only',
                read_only=True, keep_awake=self.awake, target_printer='K1 / K1C 2025'))
            seen_printing = False
            terminal_since = None
            last_ok = last_sample = time.monotonic()
            last_report = last_gcode = 0
            gcode_time = 0
            previous_state = None
            previous_file = None
            while True:
                tick = time.monotonic()
                if self.keys(): break
                if self.args.duration and tick - start >= self.args.duration:
                    self.reason = 'duration_limit'
                    break
                try:
                    result = self.query(dynamic)
                    now = time.monotonic()
                    row = self.make_row(result)
                    if now - last_sample > max(5, self.args.interval * 3):
                        self.event('SAMPLING_GAP_SECONDS', round(now - last_sample, 3))
                    last_ok = last_sample = now
                    self.warning('CONNECTION_LOST', False, None)
                    self.last = row
                    self.streams['raw'].write(json.dumps({'timestamp': row['timestamp'], **result}, ensure_ascii=False) + '\n')
                    writer.writerow(row)
                    self.streams['csv'].flush()
                    self.samples += 1
                    for key in ('nozzle_c', 'chamber_c', 'bed_c', 'hotend_fan_rpm', 'mcu_c', 'nozzle_mcu_c',
                                'part_fan', 'aux_fan', 'driver_temperature', 'extruder_current'):
                        value = row[key]
                        if isinstance(value, (int, float)) and math.isfinite(value):
                            bounds = self.ranges.setdefault(key, {'min': value, 'max': value})
                            bounds['min'], bounds['max'] = min(bounds['min'], value), max(bounds['max'], value)
                    self.check(row, now)
                    if row['state'] != previous_state:
                        self.event('PRINT_STATE', row['state'])
                        previous_state = row['state']
                    if row['filename'] and row['filename'] != previous_file:
                        previous_file = row['filename']
                        try:
                            self.save_json('gcode_metadata.json', self.get('/server/files/metadata?filename=' + urllib.parse.quote(previous_file, safe='')))
                        except Exception as exc:
                            self.event('METADATA_UNAVAILABLE', str(exc))
                    seen_printing |= row['state'] in ('printing', 'paused') or bool(result['status'].get('virtual_sdcard', {}).get('is_active'))
                    terminal = seen_printing and row['state'] in ('complete', 'cancelled', 'error', 'standby') and not result['status'].get('virtual_sdcard', {}).get('is_active')
                    terminal_since = (terminal_since if terminal_since is not None else now) if terminal else None
                    if not self.args.keep_after_print and terminal_since is not None and now - terminal_since >= 15:
                        self.reason = 'print_' + row['state']
                        break
                    if now - last_report >= 10:
                        print('{} | {:.1f} min | {} | nozzle {}/{} C | chamber {} C | hotend fan {} RPM ({:.0f}%) | part fan {:.0f}% | board {} C'.format(
                            row['timestamp'][11:19], (row['print_seconds'] or 0) / 60, row['state'],
                            row['nozzle_c'], row['nozzle_target_c'], row['chamber_c'],
                            round(row['hotend_fan_rpm']) if row['hotend_fan_rpm'] is not None else '?',
                            (row['hotend_fan_command'] or 0) * 100,
                            (row['part_fan'] or 0) * 100, row['mcu_c']), flush=True)
                        self.save_json('summary.json', self.summary())
                        last_report = now
                    if now - last_gcode >= 5:
                        try:
                            items = self.get('/server/gcode_store?count=200').get('gcode_store', [])
                            for item in items:
                                if item.get('time', 0) > gcode_time:
                                    self.streams['gcode'].write(json.dumps(item, ensure_ascii=False) + '\n')
                            gcode_time = max([gcode_time] + [item.get('time', 0) for item in items])
                        except Exception as exc:
                            self.event('GCODE_HISTORY_UNAVAILABLE', str(exc))
                        last_gcode = now
                except Exception as exc:
                    self.errors += 1
                    self.streams['events'].write(json.dumps({'timestamp': timestamp(), 'kind': 'QUERY_ERROR', 'detail': str(exc)}) + '\n')
                    self.warning('CONNECTION_LOST', time.monotonic() - last_ok >= 5, str(exc))
                    if time.monotonic() - last_ok > 180:
                        self.reason = 'connection_lost_180_seconds'
                        break
                while time.monotonic() - tick < self.args.interval:
                    if self.keys(): return
                    time.sleep(min(.1, max(0, self.args.interval - (time.monotonic() - tick))))
        except KeyboardInterrupt:
            self.reason = 'keyboard_interrupt'
        except Exception as exc:
            self.reason = 'recorder_error: ' + repr(exc)
            print(self.reason, flush=True)
        finally:
            for stream in self.streams.values(): stream.close()
            self.save_json('summary.json', self.summary())
            if self.awake:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            archive = self.folder.with_suffix('.zip')
            with zipfile.ZipFile(str(archive), 'w', compression=zipfile.ZIP_DEFLATED) as z:
                for file in self.folder.iterdir():
                    if file.is_file(): z.write(str(file), arcname=file.name)
            print('\nRecording finished: {}\nArchive: {}\nPrinter commands were NOT sent.'.format(self.reason, archive), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='192.168.1.95', help='Printer IP or Moonraker URL, e.g. http://192.168.1.95:7125')
    p.add_argument('--output', default=str(Path(__file__).resolve().parent / 'K1c2025_logs'), help='Output parent folder')
    p.add_argument('--interval', type=float, default=1.0, help='Requested sampling interval in seconds (default 1)')
    p.add_argument('--timeout', type=float, default=4.0, help='HTTP timeout in seconds')
    p.add_argument('--note', default='', help='Describe model, material, temperature, lid and other test conditions')
    p.add_argument('--keep-after-print', action='store_true', help='Continue until Q/Ctrl+C after completion or cancellation')
    p.add_argument('--duration', type=float, default=0, help='Optional recording limit in seconds; 0 means no limit')
    p.add_argument('--no-keep-awake', action='store_true', help='Do not request temporary Windows sleep prevention')
    p.add_argument('--no-keyboard', action='store_true', help='Disable F/M/Q hotkeys, useful for redirected execution')
    args = p.parse_args()
    if args.interval < .5 or args.timeout <= 0 or args.duration < 0:
        p.error('interval must be >= 0.5, timeout > 0, duration >= 0')
    Recorder(args).run()


if __name__ == '__main__':
    main()