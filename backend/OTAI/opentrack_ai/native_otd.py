"""Typed SOAP access to an already isolated, stock OpenTrack OTD test process."""

import argparse
from dataclasses import asdict, dataclass
from hashlib import file_digest
from http.client import HTTPConnection, HTTPException
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
from typing import Literal
from xml.etree import ElementTree as ET

from .catalog import EXPECTED_EXE_SHA256
from .license_authorization import require_authorization


_LOOPBACK = '127.0.0.1'
_SOAP = 'http://schemas.xmlsoap.org/soap/envelope/'
_RESPONSE_LIMIT = 16384
_DIME_RECORD = struct.Struct('>BBHHHI')
_DIME_ID = b'cid:id0'
_DIME_TYPE = _SOAP.encode('ascii')
_WATCHDOG_MAX = 2_147_483_646
_FLOAT32_MAX = 3.4028234e38
ROUTE_COMMANDS = {
    'allow': 'setRouteAllowed', 'disallow': 'setRouteDisallowed',
    'reserve': 'setRouteReserve', 'cancel': 'cancelRoute',
}
TIMETABLE_COMMANDS = {
    'arrival': 'setArrivalTime', 'departure': 'setDepartureTime', 'dwell': 'setDwellTime',
}


class OTDProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class CommandAcknowledgement:
    command: str
    http_status: Literal[200] = 200
    application_confirmed: Literal[False] = False


def _request_xml(command):
    payload = ET.tostring(command, encoding='us-ascii').decode('ascii')
    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<SOAP-ENV:Envelope xmlns:SOAP-ENV="{_SOAP}">\n<SOAP-ENV:Body>\n'
        f'{payload}\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>'
    )
    return envelope.encode('ascii')


def _identifier(value, label):
    if not isinstance(value, str) or value != value.strip() or not re.fullmatch(r'[\x20-\x7e]{1,200}', value):
        raise ValueError(f'Use an exact printable original {label} identifier')
    return value


def _nonnegative_number(value, label):
    if type(value) not in (int, float) or not 0 <= value <= _FLOAT32_MAX or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite nonnegative float32 value')
    return format(value, '.9g')


def _padded(length):
    return (length + 3) & ~3


def _status_xml(response):
    # The stock status reply builder may wrap the SOAP text in one DIME record.
    if response.startswith(b'\x0e\x20') and len(response) >= _DIME_RECORD.size:
        _, _, options, id_length, type_length, size = _DIME_RECORD.unpack_from(response)
        id_start = _DIME_RECORD.size
        type_start = id_start + _padded(id_length)
        data_start = type_start + _padded(type_length)
        if (options or size == 0 or data_start + _padded(size) != len(response)
                or response[id_start:id_start + id_length] != _DIME_ID
                or response[type_start:type_start + type_length] != _DIME_TYPE):
            raise OTDProtocolError('Unexpected OpenTrack status record')
        return response[data_start:data_start + size]
    return response


def _soap_element(response):
    try:
        xml = _status_xml(response).decode('utf-8')
        if '<!' in xml:
            raise OTDProtocolError('Unexpected declaration in OpenTrack status reply')
        root = ET.fromstring(xml)
    except (ET.ParseError, UnicodeError) as exc:
        raise OTDProtocolError('Invalid SOAP status reply') from exc
    body = root.find(f'{{{_SOAP}}}Body')
    if root.tag != f'{{{_SOAP}}}Envelope' or body is None or len(root) != 1 or len(body) != 1:
        raise OTDProtocolError('Unexpected SOAP status envelope')
    return body[0]


def _status_element(response, tag):
    message = _soap_element(response)
    if message.tag != tag:
        raise OTDProtocolError(f'Expected OpenTrack {tag} status')
    return message


def _verify_scoped_listener(port, process_id):
    """Inspect the selected local port and process without sending a probe."""
    if os.name != 'nt':
        raise OTDProtocolError('The stock OpenTrack OTD process guard requires Windows')
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = (
        "$ErrorActionPreference = 'Stop'; [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
        f'$owners = @(Get-NetTCPConnection -State Listen -LocalPort {port} | '
        "Where-Object { $_.LocalAddress -in @('127.0.0.1', '0.0.0.0') } | "
        'Select-Object -ExpandProperty OwningProcess); '
        f'$app = Get-Process -Id {process_id}; '
        '@{owners=$owners; image=$app.Path} | ConvertTo-Json -Compress'
    )
    try:
        result = subprocess.run(
            [str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
            capture_output=True, check=True, encoding='utf-8', timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        record = json.loads(result.stdout)
        if not isinstance(record, dict) or record.get('owners') != [process_id] or not record.get('image'):
            raise OTDProtocolError('The selected process must own the OTD listener')
        with Path(record['image']).open('rb') as original:
            if file_digest(original, 'sha256').hexdigest() != EXPECTED_EXE_SHA256:
                raise OTDProtocolError('The OTD process does not match the supported stock OpenTrack build')
    except (OSError, subprocess.SubprocessError, UnicodeError, json.JSONDecodeError) as exc:
        raise OTDProtocolError('Unable to verify the selected stock OpenTrack OTD listener') from exc


@dataclass(frozen=True)
class OTDClient:
    data_root: Path
    port: int
    process_id: int
    isolated_test_network: bool
    timeout: float = 3.0

    def __post_init__(self):
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError('Select an exact OTD port from 1 through 65535')
        if type(self.process_id) is not int or not 1 <= self.process_id <= 4_294_967_295:
            raise ValueError('Select the running stock test process ID')
        if self.isolated_test_network is not True:
            raise ValueError('Stock OTD requires an isolated test network because it binds all IPv4 interfaces')
        if type(self.timeout) not in (int, float) or not 0 < self.timeout <= 10:
            raise ValueError('The HTTP timeout must be greater than 0 and at most 10 seconds')

    def _post(self, command):
        require_authorization(self.data_root)
        _verify_scoped_listener(self.port, self.process_id)
        connection = HTTPConnection(_LOOPBACK, self.port, timeout=self.timeout)
        try:
            connection.request('POST', '/otd', body=_request_xml(command), headers={
                'Content-Type': 'text/xml; charset=us-ascii',
                'SOAPAction': '',
                'Connection': 'close',
            })
            response = connection.getresponse()
            if response.status != 200:
                raise OTDProtocolError(f'OpenTrack returned HTTP {response.status}')
            data = response.read(_RESPONSE_LIMIT + 1)
            if len(data) > _RESPONSE_LIMIT or response.length not in (None, 0):
                raise OTDProtocolError('Incomplete or oversized OpenTrack HTTP response')
            return data
        except (OSError, HTTPException) as exc:
            raise OTDProtocolError('OpenTrack OTD transport failed. Command application is unknown.') from exc
        finally:
            connection.close()

    def version(self) -> str:
        result = _status_element(self._post(ET.Element('getOpenTrackVersionRequest')),
                                 'getOpenTrackVersionResponse')
        version = result.attrib.get('version', '')
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', version) or len(result):
            raise OTDProtocolError('Unexpected OpenTrack version value')
        return version

    def watchdog(self, value: int = 0) -> int:
        if type(value) is not int or not 0 <= value <= _WATCHDOG_MAX:
            raise ValueError('The watchdog value must admit a signed 32-bit increment')
        request = ET.Element('getLifeRequest')
        ET.SubElement(request, 'Watchdog', {'value': str(value)})
        result = _status_element(self._post(request), 'getLifeResponse')
        if len(result) != 1 or result[0].tag != 'Watchdog' or result[0].attrib != {
                'value': str(value + 1), 'module': 'OT'}:
            raise OTDProtocolError('Unexpected OpenTrack watchdog echo')
        return value + 1

    def _acknowledge(self, command):
        if self._post(command):
            raise OTDProtocolError('Unexpected body in OpenTrack command acknowledgement')
        return CommandAcknowledgement(command.tag)

    def pause(self, simulation_time_s: float) -> CommandAcknowledgement:
        return self._acknowledge(ET.Element('pauseSimulation', {'time': _nonnegative_number(simulation_time_s, 'Pause time in seconds')}))

    def step(self) -> CommandAcknowledgement:
        return self._acknowledge(ET.Element('stepSimulation'))

    def start(self, simulation_time_s: float) -> CommandAcknowledgement:
        return self._acknowledge(ET.Element('startSimulation', {'time': _nonnegative_number(simulation_time_s, 'Start time in seconds')}))

    def end(self, simulation_time_s: float) -> CommandAcknowledgement:
        return self._acknowledge(ET.Element('endSimulation', {'time': _nonnegative_number(simulation_time_s, 'End time in seconds')}))

    def route(self, action: Literal['allow', 'disallow', 'reserve', 'cancel'], course_id: str,
              route_id: str, simulation_time_s: float) -> CommandAcknowledgement:
        if action not in ROUTE_COMMANDS:
            raise ValueError('Select allow, disallow, reserve or cancel')
        return self._acknowledge(ET.Element(ROUTE_COMMANDS[action], {
            'trainID': _identifier(course_id, 'Course'), 'routeID': _identifier(route_id, 'Route'),
            'time': _nonnegative_number(simulation_time_s, 'Route request time in seconds'),
        }))

    def requested_speed(self, course_id: str, simulation_time_s: float,
                        speed_kmh: float | None = None) -> CommandAcknowledgement:
        attributes = {'trainID': _identifier(course_id, 'Course'),
                      'time': _nonnegative_number(simulation_time_s, 'Speed request time in seconds')}
        if speed_kmh is None:
            return self._acknowledge(ET.Element('resetRequestedSpeed', attributes))
        attributes['speed'] = _nonnegative_number(speed_kmh, 'Requested speed in km/h')
        return self._acknowledge(ET.Element('setRequestedSpeed', attributes))

    def timetable(self, action: Literal['arrival', 'departure', 'dwell'], course_id: str,
                  station_id: str, seconds: float) -> CommandAcknowledgement:
        if action not in TIMETABLE_COMMANDS:
            raise ValueError('Select arrival, departure or dwell')
        return self._acknowledge(ET.Element(TIMETABLE_COMMANDS[action], {
            'trainID': _identifier(course_id, 'Course'), 'stationID': _identifier(station_id, 'Station'),
            'time': _nonnegative_number(seconds, 'Timetable time or dwell in seconds'),
        }))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--process-id', type=int, required=True)
    parser.add_argument('--isolated-test-network', action='store_true')
    subcommands = parser.add_subparsers(dest='command', required=True)
    subcommands.add_parser('version')
    subcommands.add_parser('watchdog').add_argument('--value', type=int, default=0)
    for name in ('pause', 'start', 'end'):
        subcommands.add_parser(name).add_argument('simulation_time_s', type=float)
    subcommands.add_parser('step')
    route = subcommands.add_parser('route')
    route.add_argument('action', choices=ROUTE_COMMANDS)
    route.add_argument('course_id')
    route.add_argument('route_id')
    route.add_argument('simulation_time_s', type=float)
    speed = subcommands.add_parser('speed')
    speed.add_argument('course_id')
    speed.add_argument('simulation_time_s', type=float)
    speed.add_argument('speed_kmh', type=float, nargs='?')
    timetable = subcommands.add_parser('timetable')
    timetable.add_argument('action', choices=TIMETABLE_COMMANDS)
    timetable.add_argument('course_id')
    timetable.add_argument('station_id')
    timetable.add_argument('seconds', type=float)
    args = parser.parse_args(argv)
    try:
        client = OTDClient(args.data_root, args.port, args.process_id, args.isolated_test_network)
        if args.command == 'version':
            result = {'version': client.version()}
        elif args.command == 'watchdog':
            result = {'watchdog': client.watchdog(args.value)}
        elif args.command in ('pause', 'start', 'end'):
            result = asdict(getattr(client, args.command)(args.simulation_time_s))
        elif args.command == 'route':
            result = asdict(client.route(args.action, args.course_id, args.route_id, args.simulation_time_s))
        elif args.command == 'speed':
            result = asdict(client.requested_speed(args.course_id, args.simulation_time_s, args.speed_kmh))
        elif args.command == 'timetable':
            result = asdict(client.timetable(args.action, args.course_id, args.station_id, args.seconds))
        else:
            result = asdict(client.step())
    except ValueError as exc:
        parser.exit(2, f'{exc}\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
