#!/usr/bin/env python3
"""Verify immutable native-backend admission without building or downloading."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
from subprocess import run as run_process
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_backend', ROOT/'packaging/launch-backend.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class NativeBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='audio-native-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)/'plugin with spaces'
        self.root.mkdir()
        self.source = self.root/'source'
        self.source.write_text('reviewed source')
        self.inspected = []
        self.tools = SimpleNamespace(source_id=self.source_id, inspect=self.inspect)
        self.addCleanup(patch.stopall)
        patch.object(launcher, 'release_tools', return_value=self.tools).start()
        patch.object(launcher.platform, 'system', return_value='Linux').start()

    def source_id(self, _root):
        return hashlib.sha256(self.source.read_bytes()).hexdigest()

    def write_binary(self, machine='x86_64', build_id=None):
        target, elf_machine = launcher.TARGETS[machine]
        binary = self.root/'bin/omarchy-audio-service'
        header = bytearray(20)
        header[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', header, 18, elf_machine)
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(header + json.dumps({
            'buildId': build_id or self.source_id(self.root),
            'target': target,
            'protocolVersion': 1,
        }).encode())
        binary.chmod(0o755)
        self.write_metadata(binary, target)
        return binary

    def write_metadata(self, binary, expected_target, **changes):
        value = dict(
            buildId=self.source_id(self.root),
            target=expected_target,
            sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        )
        value.update(changes)
        (self.root/'backend-release.json').write_text(json.dumps(value))

    def inspect(self, path):
        self.inspected.append(path)
        return json.loads(path.read_bytes()[20:])

    def prepare(self, machine='x86_64'):
        return launcher.prepare(self.root, machine=machine)

    def test_matching_reviewed_bundle_is_admitted(self):
        for machine in launcher.TARGETS:
            with self.subTest(machine=machine):
                binary = self.write_binary(machine)
                self.assertEqual(self.prepare(machine), binary)
                self.assertEqual(self.inspected[-1], binary)

    def test_source_target_protocol_and_hash_must_all_match(self):
        binary = self.write_binary()
        target = launcher.TARGETS['x86_64'][0]
        for changes in (dict(buildId='0'*64),
                        dict(target='aarch64-unknown-linux-gnu'),
                        dict(sha256='0'*64)):
            with self.subTest(changes=changes):
                self.write_metadata(binary, target, **changes)
                with self.assertRaisesRegex(ValueError, 'metadata|verification'):
                    self.prepare()
        self.write_metadata(binary, target)
        data = json.loads(binary.read_bytes()[20:])
        data['protocolVersion'] = 2
        binary.write_bytes(binary.read_bytes()[:20] + json.dumps(data).encode())
        binary.chmod(0o755)
        self.write_metadata(binary, target)
        with self.assertRaisesRegex(ValueError, 'verification'):
            self.prepare()

    def test_unsafe_files_are_rejected_without_inspection(self):
        binary = self.write_binary()
        target = launcher.TARGETS['x86_64'][0]
        original = binary.read_bytes()
        outside = self.root/'outside'
        outside.write_bytes(original)
        outside.chmod(0o755)
        for kind in ('symlink', 'hardlink', 'writable', 'non-executable'):
            with self.subTest(kind=kind):
                if binary.exists() or binary.is_symlink():
                    binary.unlink()
                if kind == 'symlink':
                    binary.symlink_to(outside)
                elif kind == 'hardlink':
                    os.link(outside, binary)
                else:
                    binary.write_bytes(original)
                    binary.chmod(0o777 if kind == 'writable' else 0o644)
                self.write_metadata(binary, target)
                self.inspected.clear()
                with self.assertRaisesRegex(ValueError, 'verification'):
                    self.prepare()
                self.assertFalse(self.inspected)

    def test_fifo_is_rejected_without_blocking(self):
        binary = self.root/'bin/omarchy-audio-service'
        binary.parent.mkdir()
        os.mkfifo(binary)
        (self.root/'backend-release.json').write_text(json.dumps(dict(
            buildId=self.source_id(self.root), target=launcher.TARGETS['x86_64'][0],
            sha256='0'*64)))
        probe = ('import runpy; from pathlib import Path; '
                 'module=runpy.run_path('+repr(str(ROOT/'packaging/launch-backend.py'))+'); '
                 'print(module["matches"](Path('+repr(str(binary))+'), '
                 '"x86_64-unknown-linux-gnu", 62, "unused", "0"*64, '
                 'type("T",(),{"inspect":staticmethod(lambda _: {})})()))')
        result = run_process([sys.executable, '-c', probe], capture_output=True,
                             text=True, timeout=2, check=True)
        self.assertEqual(result.stdout.strip(), 'False')

    def test_missing_or_malformed_metadata_fails_closed(self):
        self.write_binary()
        metadata = self.root/'backend-release.json'
        for content in (None, '', '{}', '[]', '{broken'):
            with self.subTest(content=content):
                if content is None:
                    metadata.unlink(missing_ok=True)
                else:
                    metadata.write_text(content)
                with self.assertRaisesRegex(ValueError, 'metadata'):
                    self.prepare()

    def test_launcher_contains_no_build_download_or_replacement_path(self):
        source = (ROOT/'packaging/launch-backend.py').read_text()
        for forbidden in ('cargo build', 'cargo fetch', 'urlopen(', 'requests.',
                          'shutil.copy', 'os.replace(', 'NamedTemporaryFile'):
            self.assertNotIn(forbidden, source)

    def test_bluetooth_helpers_use_reviewed_native_launcher(self):
        scripts = self.root/'scripts'
        scripts.mkdir()
        for name in ('audio-bluetooth-default-compat', 'audio-output-set-default',
                     'audio-input-set-default'):
            helper = scripts/name
            helper.write_bytes((ROOT/'scripts'/name).read_bytes())
            helper.chmod(0o755)
        native_launcher = scripts/'audio-service'
        native_launcher.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$AUDIO_NATIVE_ARGUMENTS"\n')
        native_launcher.chmod(0o755)
        build_id = self.source_id(self.root)
        (self.root/'backend-release.json').write_text(json.dumps(dict(buildId=build_id)))
        arguments = self.root/'arguments'
        env = dict(os.environ, XDG_RUNTIME_DIR=self.temporary.name,
                   AUDIO_NATIVE_ARGUMENTS=str(arguments))
        for direction in ('output', 'input'):
            with self.subTest(direction=direction):
                run_process([str(scripts/('audio-'+direction+'-set-default')), '42',
                             'Endpoint with spaces', 'Previous endpoint'],
                            env=env, check=True, capture_output=True, text=True)
                socket_flag, socket, request_flag, method, params = arguments.read_text().splitlines()
                self.assertEqual((socket_flag, request_flag, method),
                                 ('--socket', '--request', 'default.compat'))
                self.assertEqual(socket, str(Path(self.temporary.name)/'omarchy-audio-control'/
                                             ('backend-'+build_id[:24]+'.sock')))
                self.assertEqual(json.loads(params), dict(direction=direction, id=42,
                    name='Endpoint with spaces', previous='Previous endpoint'))

    def test_unsupported_cpu_is_rejected_before_inspection(self):
        self.write_binary()
        self.inspected.clear()
        with self.assertRaisesRegex(ValueError, 'Unsupported audio backend platform'):
            self.prepare('riscv64')
        self.assertFalse(self.inspected)


if __name__ == '__main__':
    unittest.main()
