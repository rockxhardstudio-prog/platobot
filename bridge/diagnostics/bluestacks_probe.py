"""Read-only Android UI diagnostic for the Plato bridge.

This tool uses normal ADB and UIAutomator inspection surfaces only.
It never reads network traffic, changes authentication, sends input, or calls Plato APIs.

Run this while Plato is open to a group chat:
    python bridge/diagnostics/bluestacks_probe.py --output plato-ui.json --print-tree
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

DEFAULT_ADB_PATHS = (
    Path(__file__).resolve().parents[3] / "platform-tools" / "adb.exe",
    Path(r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"),
    Path(r"C:\Program Files\BlueStacks\HD-Adb.exe"),
)


def discover_adb(explicit_path: str | None = None) -> str | None:
    """Find ADB without requiring it on PATH."""
    if explicit_path:
        path = Path(explicit_path)
        return str(path) if path.is_file() else None
    configured = os.getenv("PLATO_ADB_PATH")
    if configured and Path(configured).is_file():
        return configured
    for candidate in DEFAULT_ADB_PATHS:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("adb")


def run_adb(adb: str, serial: str | None, *arguments: str) -> tuple[int, str, str]:
    command = [adb]
    if serial:
        command.extend(["-s", serial])
    command.extend(arguments)
    completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def connected_devices(adb: str) -> list[dict[str, str]]:
    _, stdout, stderr = run_adb(adb, None, "devices", "-l")
    devices = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or line.startswith("List of devices") or parts[1] != "device":
            continue
        serial, details = parts[0], parts[2:]
        record = {"serial": serial}
        record.update(dict(item.split(":", 1) for item in details if ":" in item))
        devices.append(record)
    if not devices and stderr:
        raise RuntimeError(f"ADB did not list a device: {stderr}")
    return devices


def parse_ui_xml(xml_text: str) -> list[dict[str, object]]:
    """Flatten UIAutomator XML while retaining parent/child relationships."""
    root = ElementTree.fromstring(xml_text)
    nodes: list[dict[str, object]] = []

    def visit(element: ElementTree.Element, parent: int | None, depth: int) -> None:
        node_id = len(nodes)
        record: dict[str, object] = {
            "id": node_id,
            "parent_id": parent,
            "depth": depth,
            "class": element.attrib.get("class", ""),
            "text": element.attrib.get("text", ""),
            "content_description": element.attrib.get("content-desc", ""),
            "resource_id": element.attrib.get("resource-id", ""),
            "clickable": element.attrib.get("clickable") == "true",
            "focusable": element.attrib.get("focusable") == "true",
            "scrollable": element.attrib.get("scrollable") == "true",
            "enabled": element.attrib.get("enabled") == "true",
            "bounds": element.attrib.get("bounds", ""),
            "child_ids": [],
        }
        nodes.append(record)
        if parent is not None:
            nodes[parent]["child_ids"].append(node_id)
        for child in element.findall("node"):
            visit(child, node_id, depth + 1)

    for child in root.findall("node"):
        visit(child, None, 0)
    return nodes


def extract_focus(window_dump: str) -> str | None:
    match = re.search(r"mCurrentFocus=.*?\s([\w.]+/[\w.$]+)", window_dump)
    return match.group(1) if match else None


def _shell_output(adb: str, serial: str, *command: str) -> dict[str, object]:
    code, stdout, stderr = run_adb(adb, serial, "shell", *command)
    return {"exit_code": code, "stdout": stdout, "stderr": stderr}


def probe(adb: str, serial: str, dump_file: Path | None = None) -> dict[str, object]:
    """Collect visible state. The only device write is a temporary UI dump file."""
    focus = _shell_output(adb, serial, "dumpsys", "window", "windows")
    packages = _shell_output(adb, serial, "pm", "list", "packages")
    result: dict[str, object] = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "serial": serial,
        "foreground_window": extract_focus(str(focus["stdout"])),
        "plato_package_candidates": [
            line.removeprefix("package:") for line in str(packages["stdout"]).splitlines()
            if "plato" in line.lower()
        ],
        "adb_diagnostics": {"focus": focus, "packages": packages},
        "nodes": [],
    }

    if dump_file:
        xml_text = dump_file.read_text(encoding="utf-8")
        result["ui_dump_source"] = str(dump_file)
        result["nodes"] = parse_ui_xml(xml_text)
        return result

    remote_dump = "/sdcard/plato_bridge_diagnostic.xml"
    dump = _shell_output(adb, serial, "uiautomator", "dump", remote_dump)
    code, xml_text, stderr = run_adb(adb, serial, "exec-out", "cat", remote_dump)
    result["adb_diagnostics"]["uiautomator_dump"] = dump
    result["adb_diagnostics"]["uiautomator_read"] = {"exit_code": code, "stderr": stderr}
    if code == 0 and xml_text.lstrip().startswith("<?xml"):
        result["nodes"] = parse_ui_xml(xml_text)
    else:
        result["ui_dump_error"] = "UIAutomator XML was not returned. Keep Plato visible and rerun the diagnostic."
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Android UIAutomator diagnostic")
    parser.add_argument("--adb", help="Path to adb/HD-Adb.exe; auto-detected by default")
    parser.add_argument("--serial", help="ADB serial; defaults to the only connected Android device")
    parser.add_argument("--output", type=Path, default=Path("plato-ui-diagnostic.json"))
    parser.add_argument("--dump-file", type=Path, help="Parse an already-captured UIAutomator XML file without ADB")
    parser.add_argument("--print-tree", action="store_true", help="Print nodes with text, IDs, and parent relationships")
    args = parser.parse_args()

    adb = discover_adb(args.adb)
    if not adb:
        print("No ADB executable found. Install platform-tools or pass --adb PATH.", file=sys.stderr)
        return 2
    try:
        devices = connected_devices(adb)
        serial = args.serial or (devices[0]["serial"] if len(devices) == 1 else None)
        if not serial:
            print("Specify --serial because zero or multiple Android devices are connected.", file=sys.stderr)
            return 2
        result = probe(adb, serial, args.dump_file)
    except (OSError, subprocess.TimeoutExpired, RuntimeError, ElementTree.ParseError) as error:
        print(f"Diagnostic failed: {error}", file=sys.stderr)
        return 1

    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved diagnostic: {args.output.resolve()}")
    print(f"Foreground window: {result['foreground_window'] or 'not detected'}")
    print(f"Plato package candidates: {result['plato_package_candidates'] or 'none detected'}")
    print(f"UI nodes captured: {len(result['nodes'])}")
    if result.get("ui_dump_error"):
        print(result["ui_dump_error"])
    if args.print_tree:
        for node in result["nodes"]:
            print(
                f"#{node['id']} parent={node['parent_id']} {node['class']} "
                f"text={node['text']!r} desc={node['content_description']!r} "
                f"id={node['resource_id']!r} clickable={node['clickable']} "
                f"focusable={node['focusable']} bounds={node['bounds']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
