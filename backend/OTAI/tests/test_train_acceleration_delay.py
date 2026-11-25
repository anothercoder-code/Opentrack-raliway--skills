"""Train acceleration-delay archive field, including its native negative clamp."""

import asyncio
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading

import pytest

from opentrack_ai.current_archive import train_fields as fields
from opentrack_ai.current_archive import writer


REAL_TRAINS = Path(r"D:\opentrack\deliverables\opentrack-cross-document-edit-20261114\native-baseline-stock\inputs\OTData\chain.trains")
READING_TRAINS = Path(r"D:\opentrack\OTAI\workspaces\ReadingP9_20261123\OTData\chain.trains")
READING_SHA = "996d9ac9927c91cd9a916638f9051bb856f6bc8f10328c8cc5bf6acfa1b214a7"
DATA_ROOT = Path(r"D:\opentrack")
SERVER = Path(__file__).resolve().parents[1] / "server.py"
STDIO_TIMEOUT_S = 45


def run_stdio(coroutine):
    """Run the SDK transport with a hard timeout on loop creation and teardown."""
    outcome = {}

    def runner():
        try:
            outcome["value"] = asyncio.run(
                asyncio.wait_for(coroutine, timeout=STDIO_TIMEOUT_S)
            )
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=runner, name="mcp-stdio-test", daemon=True)
    thread.start()
    thread.join(STDIO_TIMEOUT_S + 5)
    if thread.is_alive():
        raise AssertionError(
            "MCP stdio transport exceeded its hard timeout; "
            "the test thread was abandoned and cannot block interpreter exit"
        )
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def host_event_loop_available():
    """Probe event-loop creation out of process because WinSock denial can hang."""
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                "-c",
                "import asyncio; asyncio.run(asyncio.sleep(0))",
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def raw_stdio_call(request):
    """Exercise the production protocol without using an asyncio event loop."""
    process = subprocess.Popen(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            str(SERVER),
            "--root",
            str(DATA_ROOT),
            "--profile",
            "all",
            "stdio",
        ],
        cwd=SERVER.parent,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    assert process.stdin is not None
    assert process.stdout is not None
    try:
        initialize = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "acceleration-delay-test", "version": "1"},
            },
        }
        process.stdin.write((json.dumps(initialize) + "\n").encode("utf-8"))
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        assert response["id"] == 0
        assert response["result"]["serverInfo"]["name"] == "opentrack_mcp"
        process.stdin.write(
            b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        )
        process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        assert response["id"] == request["id"]
        return response
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def real_train():
    if not REAL_TRAINS.is_file():
        pytest.skip("The reviewed populated BJTU Train16 fixture is unavailable")
    blob = REAL_TRAINS.read_bytes()
    root, version = writer.load_next_compatible(blob)
    name = next(iter(fields.c.train_items(root)))
    return blob, fields.c.text(name.contents[0].value), root, version


def test_raw_stdio_protocol_exposes_current_stock_writer():
    if not SERVER.is_file():
        pytest.skip("The paired MCP server is unavailable")
    if not host_event_loop_available():
        pytest.skip(
            "This host cannot initialize the asyncio self-pipe under its WinSock policy; "
            "the production stdio transport requires a functioning event loop"
        )
    response = raw_stdio_call(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    edit = tools["opentrack_edit_current_stock_fields"]
    assert edit["annotations"]["readOnlyHint"] is False
    assert "accelerationDelay_s" in json.dumps(edit["inputSchema"])


def test_finite_positive_is_written_and_independently_reloaded():
    blob, name, _, _ = real_train()
    output, receipt = fields.patch_fields(blob, name, {"accelerationDelay_s": 12.5})
    assert blob != output
    assert fields.read_fields(output, name, ["accelerationDelay_s"])["accelerationDelay_s"] == pytest.approx(12.5)
    assert receipt["fresh_reload_verified"] is True
    assert receipt["unselected_graph_verified"] is True
    assert receipt["changes"] == [{
        "field": "accelerationDelay_s",
        "group": 9,
        "slot": 0,
        "encoding": "f",
        "setter": "F-006c14b0",
        "getter": "F-006c14a4",
        "before": receipt["changes"][0]["before"],
        "after": 12.5,
    }]


@pytest.mark.parametrize(
    ("requested", "stored"),
    [
        (-1.0, 0.0),
        (-1e-30, 0.0),
        (-1e-50, -0.0),
        (-0.0, -0.0),
        (0.0, 0.0),
        (1e-50, 0.0),
        (3.4028234663852886e38, 3.4028234663852886e38),
    ],
)
def test_native_float_domain_rounding_and_negative_clamp(requested, stored):
    blob, name, _, _ = real_train()
    output, _ = fields.patch_fields(blob, name, {"accelerationDelay_s": requested})
    assert struct.pack("<f", fields.read_fields(output, name, ["accelerationDelay_s"])["accelerationDelay_s"]) == struct.pack("<f", stored)


@pytest.mark.parametrize("value", [True, False, "1", None, float("nan"), float("inf"), float("-inf"), 1e39])
def test_invalid_values_are_rejected_without_output(value):
    blob, name, _, _ = real_train()
    with pytest.raises(ValueError):
        fields.patch_fields(blob, name, {"accelerationDelay_s": value})


def test_unselected_train_fields_are_unchanged():
    blob, name, before_root, _ = real_train()
    before = fields.read_fields(blob, name, list(fields.FIELDS))
    output, _ = fields.patch_fields(blob, name, {"accelerationDelay_s": 7.25})
    after = fields.read_fields(output, name, list(fields.FIELDS))
    before.pop("accelerationDelay_s")
    after.pop("accelerationDelay_s")
    assert after == before


def test_real_mcp_save_and_independent_readback():
    if not READING_TRAINS.is_file() or not SERVER.is_file():
        pytest.skip("The reviewed Reading P9 Train16 fixture or paired server is unavailable")
    if not host_event_loop_available():
        pytest.skip(
            "This host cannot create an asyncio self-pipe under its WinSock policy; "
            "raw JSON-RPC coverage remains enabled"
        )
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    workspace = DATA_ROOT / "OTAI" / "workspaces"
    workspace.mkdir(parents=True, exist_ok=True)

    async def exercise(target_path):
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-X", "utf8", "-B", str(SERVER),
                "--root", str(DATA_ROOT),
                "--profile", "all",
                "stdio",
            ],
            cwd=str(SERVER.parent),
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                before = await client.call_tool(
                    "opentrack_inspect_current_stock_fields",
                    {
                        "source_path": "OTAI/workspaces/ReadingP9_20261123/OTData/chain.trains",
                        "kind": "OTTrain",
                        "name": "REF_TRAIN",
                        "fields": ["accelerationDelay_s"],
                    },
                )
                assert not before.isError
                before_value = json.loads(before.content[0].text)["result"]["fields"]["accelerationDelay_s"]

                edited = await client.call_tool(
                    "opentrack_edit_current_stock_fields",
                    {
                        "source": {
                            "path": "OTAI/workspaces/ReadingP9_20261123/OTData/chain.trains",
                            "sha256": READING_SHA,
                        },
                        "kind": "OTTrain",
                        "name": "REF_TRAIN",
                        "changes": {"accelerationDelay_s": -3.5},
                        "preview_only": False,
                        "target_path": target_path,
                    },
                )
                assert not edited.isError
                edit_result = json.loads(edited.content[0].text)["result"]
                assert edit_result["saved"] is True
                assert edit_result["source_unchanged"] is True
                assert edit_result["atomic_no_replace"] is True
                assert edit_result["change_report"]["changes"][0]["setter"] == "F-006c14b0"
                assert edit_result["change_report"]["changes"][0]["after"] == 0.0

                after = await client.call_tool(
                    "opentrack_inspect_current_stock_fields",
                    {
                        "source_path": target_path,
                        "kind": "OTTrain",
                        "name": "REF_TRAIN",
                        "fields": ["accelerationDelay_s"],
                    },
                )
                assert not after.isError
                after_result = json.loads(after.content[0].text)["result"]
                assert after_result["source_sha256"] == edit_result["output_sha256"]
                assert edit_result["source_sha256"] == READING_SHA
                assert after_result["source_path"].replace("/", "\\") == target_path.replace("/", "\\")
                assert after_result["fields"]["accelerationDelay_s"] == 0.0
                return before_value, edit_result

    with tempfile.TemporaryDirectory(prefix="acceleration-delay-", dir=workspace) as raw:
        scratch = Path(raw).resolve()
        if not scratch.is_relative_to(workspace.resolve()):
            raise AssertionError("Temporary target escaped the OpenTrack workspace")
        relative_target = (scratch / "chain.trains").relative_to(DATA_ROOT).as_posix()
        before_value, edit_result = run_stdio(exercise(relative_target))
        assert fields.read_fields(
            (DATA_ROOT / relative_target).read_bytes(),
            "REF_TRAIN",
            ["accelerationDelay_s"],
        )["accelerationDelay_s"] == 0.0
        assert before_value in (0.0, -0.0)
        assert edit_result["target_path"] == relative_target.replace("/", "\\")
