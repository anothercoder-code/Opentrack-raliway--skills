"""Validate the sealed source, replay and actual launch of owned original jobs."""

import json
from pathlib import Path

from .. import native_execution as native
from . import dispatching_rules_otd as otd, native_evaluation_formats as fmt
from .native_run_evaluation import digest, read_member


class FrozenJobInputs:
    exe_sha256 = native.STOCK_EXE_SHA

    def __init__(self, data_root, job, source, request, secure_bytes):
        self.source = source
        self.request = request
        self.secure_bytes = secure_bytes
        self.inventory = request['source_sha256']
        self.snapshot = {name: self.read(job / 'source', name, nested=True) for name in self.inventory}
        fmt.require({name: digest(data) for name, data in self.snapshot.items()} == self.inventory,
                    'Frozen job source members differ from the request SHA-256 manifest')
        self.exe = native.child_path(data_root, request['executable'])
        self.binding = request.get('dispatching_rules')
        self.dispatching_xml = None
        self.effective_inventory = dict(self.inventory)
        if self.binding is not None:
            files = {name: self.read(job / native.OTD_DIRECTORY, name) for name in (otd.LAUNCH_FILE, otd.XML_FILE)}
            fmt.require(0 < len(files[otd.LAUNCH_FILE]) <= native.OTD_MANIFEST_LIMIT
                        and 0 < len(files[otd.XML_FILE]) <= otd.XML_LIMIT, 'Invalid frozen OTD bundle size')
            verified = native.bind_dispatching_rules(data_root, source, request['run_file'], self.snapshot,
                                                    self.binding['manifest_source'], files)
            fmt.require(verified == self.binding, 'Frozen OTD launch binding differs from the request')
            self.dispatching_xml = files[otd.XML_FILE]
            self.effective_inventory[native.OTD_RULE_MEMBER] = verified['xml_sha256']

    def read(self, folder, name, *, nested=False):
        return read_member(folder, name, nested=nested, secure_bytes=self.secure_bytes)

    def reproduce(self, project, scenario, *, headway_s=None):
        members, _, _ = native.scenario_members(self.source, project, self.snapshot, self.request, scenario,
                                                headway_s=headway_s, dispatching_xml=self.dispatching_xml)
        return {name: digest(raw) for name, raw in members.items()}

    def validate_launch(self, project, evidence, scenario, *, headway_s=None):
        manifest = evidence['input_sha256']
        fmt.require(evidence['executable_sha256'] == self.exe_sha256,
                    'Recorded native executable differs from the supported original fingerprint')
        fmt.require(isinstance(manifest, dict) and manifest.keys() == self.effective_inventory.keys(),
                    'Scenario member inventory differs from the sealed project and rule inputs')
        fmt.require(evidence.get('dispatching_rules') == self.binding,
                    'Recorded OTD launch binding differs from the job source')
        rule_members = {} if self.binding is None else {native.OTD_RULE_MEMBER: self.dispatching_xml}
        expected = native.scenario_command(self.exe, project, self.request, rule_members)
        command = evidence['command']
        fmt.require(isinstance(command, list) and command and isinstance(command[0], str)
                    and Path(command[0]) == self.exe and command[1:] == expected[1:],
                    'Recorded command differs from the exact owned native launch options')
        if self.binding is not None:
            writebacks = evidence['input_writebacks']
            fmt.require(manifest[native.OTD_RULE_MEMBER] == self.binding['xml_sha256']
                        and isinstance(writebacks, dict) and native.OTD_RULE_MEMBER not in writebacks,
                        'Scenario used modified OTD rules')
            receipt = json.loads(self.read(evidence['evidence_directory'], 'relocation.json'))
            fmt.require(receipt['dispatching_rules'] == self.binding
                        and receipt['source_sha256'] == self.inventory
                        and receipt['effective_input_sha256'] == manifest
                        and Path(receipt['execution_root']) == project
                        and receipt['run_file'] == self.request['run_file']
                        and receipt['delay_scenario'] == scenario
                        and receipt.get('planned_departure_headway_s') == headway_s,
                        'Scenario relocation receipt differs from its OTD launch or source')
