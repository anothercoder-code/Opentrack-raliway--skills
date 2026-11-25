"""Collect OpenTrack 1.7.6 OTD callbacks on an explicit local test port."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
from pathlib import Path
import re
from time import monotonic

from .license_authorization import require_authorization
from .native_otd import OTDProtocolError, _LOOPBACK, _RESPONSE_LIMIT, _identifier, _soap_element


_EVENT_ATTRIBUTES = {
    'simStarted': (), 'simPaused': (), 'simStopped': (), 'ping': (),
    'trainCreated': ('trainID',), 'trainDeleted': ('trainID',),
    'trainPassedSignal': ('trainID', 'signalID', 'delay'),
    'trainArrival': ('trainID', 'stationID', 'delay'),
    'trainDeparture': ('trainID', 'stationID', 'delay'),
    'trainPass': ('trainID', 'stationID', 'delay'),
    'routeReserved': ('routeID', 'trainID'), 'routeReleased': ('routeID', 'trainID'),
    'routePartReleased': ('routeID', 'partID', 'trainID'),
    'infraPartEntry': ('infraPartID', 'trainID'), 'infraPartReserved': ('infraPartID', 'trainID'),
    'infraPartExit': ('infraPartID', 'trainID'), 'infraPartReleased': ('infraPartID', 'trainID'),
}
_IDENTIFIERS = {
    'trainID': 'course_id', 'signalID': 'signal_id', 'stationID': 'station_id',
    'routeID': 'route_id', 'partID': 'route_part_id', 'infraPartID': 'infrastructure_part_id',
}


def _number(value, label):
    if not re.fullmatch(r'-?[0-9]{1,39}\.[0-9]', value):
        raise OTDProtocolError(f'Expected original one-decimal {label}')
    number = float(value)
    if not math.isfinite(number) or (label == 'time' and number < 0):
        raise OTDProtocolError(f'Invalid original {label}')
    return number


def parse_callback(payload):
    if not isinstance(payload, bytes) or not 0 < len(payload) <= _RESPONSE_LIMIT:
        raise OTDProtocolError('Missing or oversized OpenTrack callback')
    element = _soap_element(payload)
    fields = _EVENT_ATTRIBUTES.get(element.tag)
    if fields is None or set(element.attrib) != {*fields, 'time'} or len(element) or (element.text or '').strip():
        raise OTDProtocolError('Unexpected OpenTrack callback event or attributes')
    event = {'event': element.tag, 'time_s': _number(element.attrib['time'], 'time')}
    for key in fields:
        if key == 'delay':
            event['delay_s'] = _number(element.attrib[key], 'delay')
        else:
            event[_IDENTIFIERS[key]] = _identifier(element.attrib[key], key)
    return event


class _CallbackServer(HTTPServer):
    allow_reuse_address = False

    def get_request(self):
        connection, peer = super().get_request()
        connection.settimeout(1.0)
        return connection, peer


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,5}', lengths[0]) or self.headers.get('Transfer-Encoding'):
                raise OTDProtocolError('Expected one bounded Content-Length')
            size = int(lengths[0])
            if not 0 < size <= _RESPONSE_LIMIT:
                raise OTDProtocolError('Callback body outside allowed size')
            payload = self.rfile.read(size)
            if len(payload) != size:
                raise OTDProtocolError('Incomplete callback body')
            event = parse_callback(payload)
        except (ValueError, OSError):
            self.server.rejected += 1
            self._reply(400)
            return
        event.update(received_utc=datetime.now(timezone.utc).isoformat(), body_sha256=sha256(payload).hexdigest())
        self.server.events.append(event)
        self._reply(200)

    def _reply(self, status):
        self.send_response(status)
        self.send_header('Content-Length', '0')
        self.send_header('Connection', 'close')
        self.end_headers()

    def log_message(self, format, *args):
        pass


def record_callbacks(data_root, output_path, port, duration_s, maximum_events):
    root = Path(data_root).resolve(strict=True)
    require_authorization(root)
    selected = Path(output_path)
    target = selected if selected.is_absolute() else root / selected
    if not target.resolve().is_relative_to(root) or target.suffix.lower() != '.json' or target.exists():
        raise ValueError('Choose a fresh JSON callback output below the selected data root')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Choose an explicit loopback port from 1 through 65535')
    if type(duration_s) not in (float, int) or not 0 < duration_s <= 3600:
        raise ValueError('Choose a positive recording duration of at most 3600 seconds')
    if type(maximum_events) is not int or not 1 <= maximum_events <= 100000:
        raise ValueError('Choose a maximum from 1 through 100000 callback events')
    if not target.parent.is_dir():
        raise ValueError('Choose an existing output directory')
    with _CallbackServer((_LOOPBACK, port), _CallbackHandler) as server:
        server.events = []
        server.rejected = 0
        deadline = monotonic() + duration_s
        while len(server.events) < maximum_events:
            server.timeout = deadline - monotonic()
            if server.timeout <= 0:
                break
            server.handle_request()
    report = {'listen_host': _LOOPBACK, 'listen_port': port, 'events': server.events,
              'rejected_post_count': server.rejected, 'callbacks_received': len(server.events),
              'sender_process_independently_verified': False,
              'ended_by': 'event_limit' if len(server.events) == maximum_events else 'time_limit'}
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return {'path': target.as_posix(), 'callbacks_received': report['callbacks_received'],
            'rejected_post_count': report['rejected_post_count'], 'ended_by': report['ended_by']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--duration-s', type=float, required=True)
    parser.add_argument('--max-events', type=int, default=10000)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(record_callbacks(args.data_root, args.output, args.port, args.duration_s, args.max_events),
                         ensure_ascii=False))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'{exc}\n')


if __name__ == '__main__':
    main()
