import os
import tempfile
import pytest
from tor_exit_block.list_store import read_list_from_file, write_list_to_file


class TestListStore:
    def test_write_and_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "list.txt")
            ips = {"192.168.1.1", "10.0.0.1"}
            write_list_to_file(path, ips)
            result = read_list_from_file(path)
            assert len(result) == 2
            assert "192.168.1.1" in result
            assert "10.0.0.1" in result

    def test_read_missing_file_returns_empty_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nonexistent.txt")
            result = read_list_from_file(path)
            assert len(result) == 0

    def test_write_empty_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.txt")
            write_list_to_file(path, set())
            result = read_list_from_file(path)
            assert result == set()
            assert os.path.isfile(path)

    def test_output_is_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "list.txt")
            ips = {"10.0.0.1", "192.168.1.1", "172.16.0.1"}
            write_list_to_file(path, ips)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            lines = [line for line in content.strip().split("\n") if line]
            assert lines == sorted(lines)

    def test_write_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "subdir", "nested", "list.txt")
            write_list_to_file(path, {"1.2.3.4"})
            assert os.path.isfile(path)
            result = read_list_from_file(path)
            assert result == {"1.2.3.4"}
