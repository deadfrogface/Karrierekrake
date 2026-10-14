"""Guard duration export against duplicate JUnit cases (T01)."""
from argparse import Namespace
from xml.etree.ElementTree import Element, SubElement, ElementTree

from scripts.unit_test_shards import cmd_build_durations


def _junit(path, nodeid):
    suite = Element("testsuite")
    case = SubElement(suite, "testcase", classname="tests.test_example", name="test_ok", time="0.5")
    props = SubElement(case, "properties")
    SubElement(props, "property", name="nodeid", value=nodeid)
    ElementTree(suite).write(path, encoding="unicode")


def test_duration_export_rejects_duplicate_nodeid(tmp_path):
    nodeid = "tests/test_example.py::test_ok"
    collected = tmp_path / "collected.txt"
    collected.write_text(nodeid + "\n", encoding="utf-8")
    one, two = tmp_path / "one.xml", tmp_path / "two.xml"
    _junit(one, nodeid)
    _junit(two, nodeid)
    output = tmp_path / "durations.json"
    args = Namespace(collected=str(collected), junit=[str(one), str(two)], output=str(output))
    assert cmd_build_durations(args) == 1
    assert not output.exists()


def test_duration_export_writes_complete_unique_nodeids(tmp_path):
    nodeid = "tests/test_example.py::test_ok"
    collected = tmp_path / "collected.txt"
    collected.write_text(nodeid + "\n", encoding="utf-8")
    junit = tmp_path / "one.xml"
    _junit(junit, nodeid)
    output = tmp_path / "durations.json"
    args = Namespace(collected=str(collected), junit=[str(junit)], output=str(output))
    assert cmd_build_durations(args) == 0
    import json
    assert json.loads(output.read_text(encoding="utf-8")) == {nodeid: 0.5}


def test_duration_export_rejects_failed_case(tmp_path):
    nodeid = "tests/test_example.py::test_ok"
    collected = tmp_path / "collected.txt"
    collected.write_text(nodeid + "\n", encoding="utf-8")
    junit = tmp_path / "failed.xml"
    _junit(junit, nodeid)
    from xml.etree.ElementTree import parse
    tree = parse(junit)
    SubElement(tree.getroot().find("testcase"), "failure", message="regression")
    tree.write(junit, encoding="unicode")
    output = tmp_path / "durations.json"
    args = Namespace(collected=str(collected), junit=[str(junit)], output=str(output))
    assert cmd_build_durations(args) == 1
    assert not output.exists()


def test_duration_export_rejects_invalid_duration(tmp_path):
    import pytest
    nodeid = "tests/test_example.py::test_ok"
    collected = tmp_path / "collected.txt"
    collected.write_text(nodeid + "\n", encoding="utf-8")
    junit = tmp_path / "invalid.xml"
    _junit(junit, nodeid)
    from xml.etree.ElementTree import parse
    tree = parse(junit)
    tree.getroot().find("testcase").set("time", "nan")
    tree.write(junit, encoding="unicode")
    args = Namespace(collected=str(collected), junit=[str(junit)], output=str(tmp_path / "durations.json"))
    with pytest.raises(ValueError, match="invalid JUnit testcase duration"):
        cmd_build_durations(args)
