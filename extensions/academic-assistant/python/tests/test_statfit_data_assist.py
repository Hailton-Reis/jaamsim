import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import statfit_data_assist as assist


class StatFitDataAssistTest(unittest.TestCase):
    def build_args(self, tmp_path: Path, values: str, **overrides):
        defaults = {
            "input_file": None,
            "values": values,
            "column": None,
            "output_dir": tmp_path,
            "online": False,
            "require_online": False,
            "provider_order": "nvidia,cerebras,groq",
            "env_file": None,
            "max_tokens": 300,
            "dry_run_llm": False,
            "allow_index_column": False,
        }
        defaults.update(overrides)
        return Namespace(**defaults)

    def test_offline_default_makes_no_provider_calls(self):
        """Preparing local data must never contact a provider without --online."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                assist,
                "run_online_assist",
                side_effect=AssertionError("Unexpected external AI request"),
            ) as online:
                report, attempts = assist.prepare_data(
                    self.build_args(Path(tmp), "tempo\n1\n2\n3\n4\n5\n")
                )
                online.assert_not_called()

        self.assertFalse(report.online_assist_enabled)
        self.assertFalse(report.online_assist_used)
        self.assertEqual([], attempts)

    def test_prepares_pasted_excel_column_as_clean_csv(self):
        pasted = """
Cronometragem do Tempo de Atendimento Consultorio (s)
165
200
223
170
209
"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report, attempts = assist.prepare_data(self.build_args(tmp_path, pasted))
            csv_text = Path(report.cleaned_csv_path).read_text(encoding="utf-8")
            payload = json.loads(Path(report.json_path).read_text(encoding="utf-8"))

        self.assertEqual([], attempts)
        self.assertEqual("Cronometragem do Tempo de Atendimento Consultorio (s)", report.selected_column)
        self.assertEqual(5, report.sample_size)
        self.assertIn(report.data_quality_level, {"fraca", "preparacao_com_cautela", "preparacao_consistente"})
        self.assertEqual(0, report.outlier_count)
        self.assertIn("165", csv_text)
        self.assertEqual(report.selected_column, payload["selected_column"])
        self.assertIn("data_quality_level", payload)
        self.assertEqual(0, payload["outlier_count"])
        self.assertEqual("jaam.ai.python_runtime.v1", payload["python_runtime"]["schema"])
        self.assertEqual(64, len(payload["python_runtime"]["entry_script_sha256"]))

    def test_selects_requested_column_and_ignores_index_column(self):
        pasted = """
linha;tempo_atendimento;observacao
1;165;ok
2;200;ok
3;223;ok
4;170;ok
5;209;ok
"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report, _attempts = assist.prepare_data(
                self.build_args(tmp_path, pasted, column="tempo_atendimento")
            )

        self.assertEqual("tempo_atendimento", report.selected_column)
        self.assertEqual(2, report.selected_column_index)
        self.assertEqual(5, report.sample_size)
        self.assertTrue(any(profile.probable_index for profile in report.column_profiles))

    def test_online_dry_run_does_not_call_provider_or_require_tokens(self):
        pasted = "tempo\n1\n2\n3\n4\n5\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report, attempts = assist.prepare_data(
                self.build_args(tmp_path, pasted, online=True, dry_run_llm=True)
            )
            markdown = Path(report.markdown_path).read_text(encoding="utf-8")

        self.assertFalse(report.online_assist_used)
        self.assertIn("DRY RUN", report.llm_summary)
        self.assertIn("Resposta IA", markdown)
        self.assertIsInstance(attempts, list)

    def test_empty_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaisesRegex(ValueError, "Informe um arquivo de dados ou --values"):
                assist.prepare_data(self.build_args(tmp_path, "   \n\n"))

    def test_small_sample_is_classified_as_weak(self):
        pasted = "tempo\n1\n2\n3\n4\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report, _attempts = assist.prepare_data(self.build_args(tmp_path, pasted))

        self.assertEqual("fraca", report.data_quality_level)

    def test_input_without_numeric_values_is_rejected(self):
        pasted = "tempo\nalto\nmedio\nbaixo\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaisesRegex(ValueError, "Nenhum valor numérico"):
                assist.prepare_data(self.build_args(tmp_path, pasted))

    def test_incomplete_rows_count_ignored_values_and_warn(self):
        pasted = """
linha;tempo;obs
1;10;ok
2;erro;ruim
3;;vazio
4;40;ok
5;50;ok
"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report, _attempts = assist.prepare_data(
                self.build_args(tmp_path, pasted, column="tempo")
            )

        self.assertEqual(3, report.sample_size)
        self.assertEqual(1, report.ignored_values)
        self.assertTrue(any("ignoradas" in warning for warning in report.warnings))

    def test_negative_values_are_preserved_but_warned(self):
        pasted = "saldo\n-5\n0\n10\n15\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report, _attempts = assist.prepare_data(self.build_args(tmp_path, pasted))
            csv_text = Path(report.cleaned_csv_path).read_text(encoding="utf-8")

        self.assertIn("-5", csv_text)
        self.assertTrue(any("negativos" in warning for warning in report.warnings))

    def test_constant_values_warn_as_deterministic_candidate(self):
        pasted = "tempo\n5\n5\n5\n5\n5\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report, _attempts = assist.prepare_data(self.build_args(tmp_path, pasted))

        self.assertTrue(any("determinística" in warning for warning in report.warnings))

    def test_requested_column_by_number(self):
        pasted = """
linha;tempo;fila
1;10;2
2;20;4
3;30;6
"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report, _attempts = assist.prepare_data(self.build_args(tmp_path, pasted, column="3"))

        self.assertEqual("fila", report.selected_column)
        self.assertEqual(3, report.sample_size)

    def test_interval_values_are_prepared_as_midpoints(self):
        pasted = """
tempo_estimado
3-4 min
5 a 7 min
8 min
"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report, _attempts = assist.prepare_data(self.build_args(tmp_path, pasted))
            csv_text = Path(report.cleaned_csv_path).read_text(encoding="utf-8")

        self.assertEqual(3, report.sample_size)
        self.assertIn("3.5", csv_text)
        self.assertIn("6", csv_text)

    def test_outliers_are_flagged_before_fit(self):
        pasted = "tempo\n10\n11\n10\n12\n11\n10\n400\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report, _attempts = assist.prepare_data(self.build_args(tmp_path, pasted))
            markdown = Path(report.markdown_path).read_text(encoding="utf-8")

        self.assertEqual(1, report.outlier_count)
        self.assertEqual("preparacao_com_cautela", report.data_quality_level)
        self.assertIn("Classificação local da preparação", markdown)
        self.assertIn("Possíveis outliers por IQR", markdown)
        self.assertTrue(any("Possíveis outliers" in warning for warning in report.warnings))

    def test_cli_prints_quality_and_outlier_summary_for_native_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            values = "tempo\n10\n11\n10\n12\n11\n10\n400\n"
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = assist.main([
                    "--values",
                    values,
                    "--output-dir",
                    str(tmp_path / "out"),
                ])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("Classificação preparação:", output)
        self.assertIn("Outliers IQR:", output)


if __name__ == "__main__":
    unittest.main()
