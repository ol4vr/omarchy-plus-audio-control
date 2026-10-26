#!/usr/bin/env python3
"""Verify the reviewed bundled backend without building or replacing it."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import stat
import struct
import subprocess
import sys

TARGETS = {
    'x86_64': ('x86_64-unknown-linux-gnu', 62),
    'aarch64': ('aarch64-unknown-linux-gnu', 183),
}


def release_tools(root):
    spec = importlib.util.spec_from_file_location('audio_release', root/'packaging/build-release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matches(binary, target, machine, build_id, expected_sha256, tools):
    try:
        descriptor = os.open(binary, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                return False
            if (metadata.st_uid != os.getuid() or metadata.st_nlink != 1
                    or metadata.st_mode & 0o022):
                return False
            header = stream.read(20)
            stream.seek(0)
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        # Never execute a foreign ELF (including via binfmt/QEMU).
        if (len(header) != 20 or header[:6] != b'\x7fELF\x02\x01'
                or struct.unpack_from('<H', header, 18)[0] != machine
                or not os.access(binary, os.X_OK) or digest != expected_sha256):
            return False
        info = tools.inspect(binary)
        return (isinstance(info, dict) and info.get('buildId') == build_id and info.get('target') == target
                and info.get('protocolVersion') == 1)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def prepare(root, machine=None, cache_home=None):
    machine = platform.machine() if machine is None else machine
    if platform.system() != 'Linux' or machine not in TARGETS:
        raise ValueError(f'Unsupported audio backend platform: {platform.system()} {machine}')
    target, elf_machine = TARGETS[machine]
    tools = release_tools(root)
    build_id = tools.source_id(root)
    bundled = root/'bin/omarchy-audio-service'
    try:
        metadata = json.loads((root/'backend-release.json').read_text())
        expected_sha256 = metadata['sha256']
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('Reviewed native backend metadata is unavailable') from error
    if (metadata.get('buildId') != build_id or metadata.get('target') != target
            or not isinstance(expected_sha256, str) or len(expected_sha256) != 64):
        raise ValueError('Native backend metadata does not match this plugin source')
    if matches(bundled, target, elf_machine, build_id, expected_sha256, tools):
        return bundled
    raise ValueError(
        'Bundled native backend failed immutable source, target, or SHA-256 verification; '
        'reconcile the pinned Omarchy+ plugin release'
    )


if __name__ == '__main__':
    try:
        root = Path(sys.argv[1]).resolve()
        arguments = sys.argv[2:]
        binary = prepare(root)
        if arguments == ['--prepare']:
            print(binary)
        else:
            os.execv(binary, [str(binary), *arguments])
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'Audio backend preparation failed: {error}', file=sys.stderr)
        raise SystemExit(1)
