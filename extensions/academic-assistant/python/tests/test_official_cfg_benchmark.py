import csv
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import official_cfg_benchmark as benchmark


MINIMAL = """RecordEdits
Define EntityGenerator { Gen }
Define Queue { Fila }
Define Server { Atendimento }
Define EntitySink { Saida }
Gen NextComponent { Fila }
Atendimento WaitQueue { Fila }
Atendimento NextComponent { Saida }
"""


def corpus(tmp: Path, *, corrupt_hash=False, name="simple.cfg"):
    archive = tmp / "official.zip"
    index = tmp / "official_examples_index.csv"
    payload = MINIMAL.encode("utf-8")
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr(name, payload)
    with index.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ["relative_path", "size_bytes", "sha256"])
        writer.writeheader()
        writer.writerow({
            "relative_path": name,
            "size_bytes": len(payload),
            "sha256": "0" * 64 if corrupt_hash else hashlib.sha256(payload).hexdigest(),
        })
    return archive, index


class OfficialCfgBenchmarkTest(unittest.TestCase):
    def test_small_offline_fixture_passes_and_does_not_publish_cfg_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, index = corpus(Path(folder))
            report = benchmark.run_benchmark(
                archive,
                index,
                expected_count=1,
                min_with_components=1,
                min_with_connections=1,
            )
        self.assertTrue(report["passed"])
        self.assertEqual(1, report["summary"]["totals"]["parsed"])
        self.assertEqual(1, report["corpus"]["file_count"])
        self.assertEqual(0, report["summary"]["warning_counts"].get("UNPARSED_STATEMENT", 0))
        self.assertNotIn("Gen NextComponent", json.dumps(report))
        self.assertNotIn("Define EntityGenerator", json.dumps(report))
        self.assertEqual(1, len(report["models"]))

    def test_tampered_file_hash_blocks_benchmark(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, index = corpus(Path(folder), corrupt_hash=True)
            with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
                benchmark.run_benchmark(archive, index, expected_count=1)

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, index = corpus(Path(folder), name="../escape.cfg")
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                benchmark.run_benchmark(archive, index, expected_count=1)

    def test_reference_is_compared_without_changing_original_files(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, index = corpus(Path(folder))
            original_bytes = archive.read_bytes()
            report = benchmark.run_benchmark(
                archive,
                index,
                reference_parser_path=Path(benchmark.bridge.__file__),
                expected_count=1,
                min_with_components=1,
                min_with_connections=1,
            )
            self.assertEqual(original_bytes, archive.read_bytes())
        self.assertTrue(report["passed"])
        self.assertEqual(0, report["comparison"]["missing_reference_edges"])
        self.assertEqual(0, report["comparison"]["missing_reference_components"])
        self.assertEqual([], report["comparison"]["files_with_structural_or_warning_differences"])

    def test_coverage_gate_fails_without_required_intermediate_models(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, index = corpus(Path(folder))
            report = benchmark.run_benchmark(
                archive,
                index,
                expected_count=1,
                min_with_components=2,
                min_with_connections=2,
            )
        self.assertFalse(report["passed"])
        self.assertFalse(report["gates"]["components_min"])
        self.assertFalse(report["gates"]["connections_min"])


if __name__ == "__main__":
    unittest.main()
