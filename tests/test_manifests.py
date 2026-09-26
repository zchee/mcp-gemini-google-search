# Copyright 2026 The mcp-gemini-google-search Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Cross-file consistency checks for the bundled plugin manifests.

The Claude Code and Codex plugins are built from this repository, so the
version and server name they declare live in several JSON files at once.
Nothing at runtime reads them together; this module is what keeps them from
drifting apart between releases.
"""

from __future__ import annotations

from itertools import starmap
from pathlib import Path
import re
from typing import Any

import orjson
import pytest

from mcp_gemini_search.server import SERVER_NAME


REPO_ROOT = Path(__file__).resolve().parent.parent

CLAUDE_PLUGIN = ".claude-plugin/plugin.json"
CLAUDE_MARKETPLACE = ".claude-plugin/marketplace.json"
CODEX_PLUGIN = ".codex-plugin/plugin.json"
CODEX_MARKETPLACE = ".agents/plugins/marketplace.json"
MCP_CONFIG = ".mcp.json"
README = "README.md"

# Every field that declares the plugin version. The release workflow refuses
# to publish a final release whose tag differs from these.
VERSION_FIELDS: tuple[tuple[str, tuple[str | int, ...]], ...] = (
    (CLAUDE_PLUGIN, ("version",)),
    (CODEX_PLUGIN, ("version",)),
    (CLAUDE_MARKETPLACE, ("plugins", 0, "version")),
    (CLAUDE_MARKETPLACE, ("version",)),
)

# Every field that names the plugin, its marketplace entry, or its MCP server.
NAME_FIELDS: tuple[tuple[str, tuple[str | int, ...]], ...] = (
    (CLAUDE_PLUGIN, ("name",)),
    (CODEX_PLUGIN, ("name",)),
    (CLAUDE_MARKETPLACE, ("name",)),
    (CLAUDE_MARKETPLACE, ("plugins", 0, "name")),
    (CODEX_MARKETPLACE, ("name",)),
    (CODEX_MARKETPLACE, ("plugins", 0, "name")),
)

_RELEASE_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def _load(relative_path: str) -> Any:
    """Parse a JSON file relative to the repository root."""
    return orjson.loads((REPO_ROOT / relative_path).read_bytes())


def _dig(document: Any, path: tuple[str | int, ...]) -> Any:
    """Follow ``path`` (mapping keys and sequence indexes) into ``document``."""
    for key in path:
        document = document[key]
    return document


def _describe(relative_path: str, path: tuple[str | int, ...]) -> str:
    """Render a manifest field as ``file:key[0].key`` for assertion messages."""
    rendered = "".join(f"[{key}]" if isinstance(key, int) else f".{key}" for key in path)
    return f"{relative_path}{rendered}"


def test_manifest_versions_agree() -> None:
    """Every plugin manifest declares the same release version."""
    declared = {_describe(file, path): _dig(_load(file), path) for file, path in VERSION_FIELDS}

    assert len(set(declared.values())) == 1, f"plugin manifest versions differ: {declared}"


@pytest.mark.parametrize(("file", "path"), VERSION_FIELDS, ids=list(starmap(_describe, VERSION_FIELDS)))
def test_manifest_version_is_a_final_release(file: str, path: tuple[str | int, ...]) -> None:
    """Plugin versions are ``MAJOR.MINOR.PATCH``; pre-release tags publish to PyPI only."""
    version = _dig(_load(file), path)

    assert isinstance(version, str)
    assert _RELEASE_VERSION.match(version), f"{_describe(file, path)} = {version!r} is not MAJOR.MINOR.PATCH"


@pytest.mark.parametrize(("file", "path"), NAME_FIELDS, ids=list(starmap(_describe, NAME_FIELDS)))
def test_manifest_names_match_server_name(file: str, path: tuple[str | int, ...]) -> None:
    """The plugin and marketplace entries carry the MCP server's own name."""
    assert _dig(_load(file), path) == SERVER_NAME


def test_mcp_config_registers_exactly_the_server() -> None:
    """The bundled ``.mcp.json`` registers this server under its own name and nothing else."""
    servers = _load(MCP_CONFIG)["mcpServers"]

    assert set(servers) == {SERVER_NAME}


def test_readme_embeds_the_bundled_mcp_config() -> None:
    """The README's copy of ``.mcp.json`` is byte-for-byte the shipped file, modulo formatting."""
    readme = (REPO_ROOT / README).read_text(encoding="utf-8")
    match = re.search(r"register the server from the same `\.mcp\.json`[^\n]*\n\n```json\n(.*?)```", readme, re.DOTALL)

    assert match is not None, "README no longer embeds .mcp.json after the 'same .mcp.json' sentence"
    assert orjson.loads(match.group(1)) == _load(MCP_CONFIG)
