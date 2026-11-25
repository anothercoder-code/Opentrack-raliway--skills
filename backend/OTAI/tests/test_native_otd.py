from email.parser import BytesHeaderParser
from hashlib import sha256
from http.client import HTTPConnection
from io import BytesIO
import json
from struct import pack
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from opentrack_ai import native_otd, native_otd_callbacks


SOAP = 'http://schemas.xmlsoap.org/soap/envelope/'


def envelope(body):
    return f'<e:Envelope xmlns:e="{SOAP}"><e:Body>{body}</e:Body></e:Envelope>'.encode('ascii')


def dime(data):
    def pad(value):
        return value + b'\x00' * (-len(value) % 4)

    identifier = b'cid:id0'
    content_type = SOAP.encode('ascii')
    header = pack('>BBHHHI', 0x0E, 0x20, 0, len(identifier), len(content_type), len(data))
    return header + pad(identifier) + pad(content_type) + pad(data)


@pytest.fixture
def server(tmp_path, monkeypatch):
    requests = []
    checks = []
    responses = []

    class Socket:
        def __init__(self, sent, status, body):
            self.sent = sent
            self.received = (
                f'HTTP/1.1 {status} Test\r\nContent-Type: text/xml; charset=us-ascii\r\n'
                f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n'
            ).encode('ascii') + body

        def sendall(self, data):
            self.sent.extend(data)

        def makefile(self, mode):
            assert mode == 'rb'
            return BytesIO(self.received)

        def close(self):
            pass

    class Connection(HTTPConnection):
        def connect(self):
            assert self.host == '127.0.0.1' and self.port == 9002
            sent = bytearray()
            requests.append(sent)
            self.sock = Socket(sent, *responses.pop(0))

    monkeypatch.setattr(native_otd, 'HTTPConnection', Connection)
    monkeypatch.setattr(native_otd, 'require_authorization', lambda root: checks.append(root))
    monkeypatch.setattr(native_otd, '_verify_scoped_listener', lambda *scope: checks.append(scope))
    return native_otd.OTDClient(tmp_path, 9002, 3141, True), requests, responses, checks


def commands(requests):
    result = []
    for request in requests:
        first_line, rest = bytes(request).split(b'\r\n', 1)
        header_bytes, data = rest.split(b'\r\n\r\n', 1)
        headers = BytesHeaderParser().parsebytes(header_bytes)
        assert first_line == b'POST /otd HTTP/1.1'
        assert headers['Host'].startswith('127.0.0.1:')
        assert headers['Content-Type'] == 'text/xml; charset=us-ascii'
        assert headers['SOAPAction'] == ''
        assert headers['Connection'] == 'close'
        root = ET.fromstring(data)
        assert root.tag == f'{{{SOAP}}}Envelope'
        body = root.find(f'{{{SOAP}}}Body')
        assert len(body) == 1
        result.append(body[0])
    return result


def test_exact_typed_status_requests_support_native_record_and_plain_soap(server):
    client, requests, responses, checks = server
    responses.extend([
        (200, dime(envelope('<getOpenTrackVersionResponse version="1.7.6"/>'))),
        (200, envelope('<getLifeResponse><Watchdog value="19" module="OT"/></getLifeResponse>')),
    ])
    assert client.version() == '1.7.6'
    assert client.watchdog(18) == 19
    version, watchdog = commands(requests)
    assert version.tag == 'getOpenTrackVersionRequest'
    assert watchdog.tag == 'getLifeRequest'
    assert watchdog[0].tag == 'Watchdog'
    assert watchdog[0].attrib == {'value': '18'}
    assert checks == [client.data_root, (client.port, client.process_id)] * 2


def test_pause_and_step_return_transport_acknowledgement(server):
    client, requests, responses, _ = server
    responses.extend([(200, b''), (200, b'')])
    pause = client.pause(36841.5)
    step = client.step()
    assert pause == native_otd.CommandAcknowledgement('pauseSimulation')
    assert step == native_otd.CommandAcknowledgement('stepSimulation')
    assert not pause.application_confirmed and not step.application_confirmed
    pause_xml, step_xml = commands(requests)
    assert (pause_xml.tag, pause_xml.attrib) == ('pauseSimulation', {'time': '36841.5'})
    assert (step_xml.tag, step_xml.attrib) == ('stepSimulation', {})


def test_original_route_speed_timetable_and_lifecycle_commands(server):
    client, requests, responses, _ = server
    responses.extend([(200, b'')] * 9)
    issued = [client.start(37200), client.end(37800)]
    issued += [client.route(action, 'RDG09', 'R:RDG-WB', 37594) for action in
               ('allow', 'disallow', 'reserve', 'cancel')]
    issued += [client.requested_speed('RDG09', 37594, 35),
               client.requested_speed('RDG09', 37625),
               client.timetable('departure', 'RDG09', 'RDG', 37596)]
    assert all(not ack.application_confirmed for ack in issued)
    sent = commands(requests)
    assert [message.tag for message in sent] == [
        'startSimulation', 'endSimulation', 'setRouteAllowed', 'setRouteDisallowed',
        'setRouteReserve', 'cancelRoute', 'setRequestedSpeed', 'resetRequestedSpeed', 'setDepartureTime',
    ]
    assert [message.attrib for message in sent] == [
        {'time': '37200'}, {'time': '37800'},
        *[{'trainID': 'RDG09', 'routeID': 'R:RDG-WB', 'time': '37594'}] * 4,
        {'trainID': 'RDG09', 'time': '37594', 'speed': '35'},
        {'trainID': 'RDG09', 'time': '37625'},
        {'trainID': 'RDG09', 'stationID': 'RDG', 'time': '37596'},
    ]


def test_open_track_callbacks_keep_route_occupation_and_timetable_evidence():
    events = [
        envelope('<simPaused time="37594.0"/>'),
        dime(envelope('<routeReserved routeID="R:RDG-WB" trainID="RDG09" time="37594.2"/>')),
        envelope('<routePartReleased routeID="R:RDG-WB" partID="RDG:21" trainID="RDG09" time="37620.0"/>'),
        envelope('<infraPartEntry infraPartID="RDG:9" trainID="RDG09" time="37618.0"/>'),
        envelope('<trainDeparture trainID="RDG09" stationID="RDG" time="37595.0" delay="-1.0"/>'),
    ]
    rows = [native_otd_callbacks.parse_callback(raw) for raw in events]
    assert rows == [
        {'event': 'simPaused', 'time_s': 37594.0},
        {'event': 'routeReserved', 'time_s': 37594.2, 'route_id': 'R:RDG-WB', 'course_id': 'RDG09'},
        {'event': 'routePartReleased', 'time_s': 37620.0, 'route_id': 'R:RDG-WB', 'route_part_id': 'RDG:21', 'course_id': 'RDG09'},
        {'event': 'infraPartEntry', 'time_s': 37618.0, 'infrastructure_part_id': 'RDG:9', 'course_id': 'RDG09'},
        {'event': 'trainDeparture', 'time_s': 37595.0, 'course_id': 'RDG09', 'station_id': 'RDG', 'delay_s': -1.0},
    ]


@pytest.mark.parametrize('body', [
    '<routeReserved routeID="R:1" trainID="1" time="nan"/>',
    '<simPaused time="37594.0" unexpected="1"/>',
    '<simPaused time="37594.0"/><simStarted time="37595.0"/>',
    '<infraPartEntry trainID="1" time="37594.0"/>',
])
def test_callback_requires_exact_native_event_shape(body):
    with pytest.raises(native_otd.OTDProtocolError):
        native_otd_callbacks.parse_callback(envelope(body))


def test_mismatched_status_or_nonempty_command_ack_rejected_without_retry(server):
    client, requests, responses, _ = server
    responses.extend([
        (200, envelope('<getLifeResponse><Watchdog value="4" module="OT"/></getLifeResponse>')),
        (200, b'unexpected'), (302, b''),
    ])
    with pytest.raises(native_otd.OTDProtocolError, match='watchdog echo'):
        client.watchdog(4)
    with pytest.raises(native_otd.OTDProtocolError, match='acknowledgement'):
        client.step()
    with pytest.raises(native_otd.OTDProtocolError, match='302'):
        client.pause(0)
    assert len(requests) == 3


@pytest.mark.parametrize('data', [
    b'<!DOCTYPE example><example/>',
    dime(envelope('<getOpenTrackVersionResponse version="1.7.6"/>'))[:31],
    envelope('<getOpenTrackVersionResponse version="1.7.6"/>') + b'_' * 17000,
])
def test_response_shape_and_size_are_bounded(server, data):
    client, requests, responses, _ = server
    responses.append((200, data))
    with pytest.raises(native_otd.OTDProtocolError):
        client.version()
    assert len(requests) == 1


def test_invalid_parameters_and_listener_failure_stop_before_http(server, monkeypatch):
    client, requests, _, _ = server
    with pytest.raises(ValueError, match='isolated test network'):
        native_otd.OTDClient(client.data_root, client.port, client.process_id, False)
    with pytest.raises(ValueError, match='finite nonnegative'):
        client.pause(float('inf'))
    with pytest.raises(ValueError, match='signed 32-bit increment'):
        client.watchdog(2_147_483_647)
    with pytest.raises(ValueError, match='exact printable'):
        client.route('reserve', 'RDG09', ' R:RDG-WB', 37594)
    with pytest.raises(ValueError, match='finite nonnegative'):
        client.requested_speed('RDG09', 37594, -1)

    def wrong_process(*scope):
        raise native_otd.OTDProtocolError('wrong process')

    monkeypatch.setattr(native_otd, '_verify_scoped_listener', wrong_process)
    with pytest.raises(native_otd.OTDProtocolError, match='wrong process'):
        client.step()
    assert not requests


def test_selected_listener_requires_exact_process_and_stock_image(tmp_path, monkeypatch):
    binary = tmp_path / 'OpenTrack.exe'
    binary.write_bytes(b'test executable identity')
    record = {'owners': [3141], 'image': str(binary)}

    def run(argv, **kwargs):
        assert 'Get-NetTCPConnection -State Listen -LocalPort 9002' in argv[-1]
        assert 'Get-Process -Id 3141' in argv[-1]
        assert kwargs['timeout'] == 8
        return SimpleNamespace(stdout=json.dumps(record))

    monkeypatch.setattr(native_otd, 'os', SimpleNamespace(name='nt', environ={'SystemRoot': str(tmp_path)}))
    monkeypatch.setattr(native_otd.subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    monkeypatch.setattr(native_otd.subprocess, 'run', run)
    monkeypatch.setattr(native_otd, 'EXPECTED_EXE_SHA256', sha256(binary.read_bytes()).hexdigest())
    native_otd._verify_scoped_listener(9002, 3141)

    record['owners'] = [3142]
    with pytest.raises(native_otd.OTDProtocolError, match='own the OTD listener'):
        native_otd._verify_scoped_listener(9002, 3141)

    record['owners'] = [3141]
    binary.write_bytes(b'other image')
    with pytest.raises(native_otd.OTDProtocolError, match='supported stock OpenTrack build'):
        native_otd._verify_scoped_listener(9002, 3141)
