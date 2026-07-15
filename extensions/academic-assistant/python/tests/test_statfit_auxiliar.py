import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import statfit_auxiliar as statfit


class StatFitAuxiliarTest(unittest.TestCase):
    def test_reads_csv_column_and_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_file = tmp_path / "tempos.csv"
            data_file.write_text(
                "tempo_atendimento,operador\n"
                "1.0,A\n"
                "2.0,A\n"
                "3.0,B\n"
                "4.0,B\n"
                "5.0,C\n",
                encoding="utf-8",
            )

            series = statfit.read_dataset(data_file, "tempo_atendimento")
            report = statfit.analyze_series(series)
            json_path, md_path = statfit.write_outputs(report, tmp_path / "out")
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = md_path.read_text(encoding="utf-8")
            histogram_svg_exists = Path(payload["chart_files"]["histogram_svg"]).exists()
            ecdf_svg_exists = Path(payload["chart_files"]["ecdf_svg"]).exists()
            qq_svg_exists = Path(payload["chart_files"]["qq_svg"]).exists()
            pp_svg_exists = Path(payload["chart_files"]["pp_svg"]).exists()

        self.assertEqual("tempo_atendimento", series.column)
        self.assertEqual(5, report.sample_size)
        self.assertIn(report.data_quality_level, {"fraca", "triagem_com_cautela", "triagem_consistente"})
        self.assertIn(report.best_distribution, {"normal", "lognormal", "exponential", "uniform", "triangular"})
        self.assertTrue(payload["candidates"])
        self.assertIn("histogram", payload)
        self.assertIn("empirical_cdf", payload)
        self.assertIn("qq_points", payload)
        self.assertIn("pp_points", payload)
        self.assertIn("diagnostics_by_distribution", payload)
        self.assertIn("chart_files", payload)
        self.assertEqual("continuous", payload["fit_kind"])
        self.assertEqual("auto", payload["support_mode"])
        self.assertIn("bic", payload["candidates"][0])
        self.assertEqual(3.0, payload["median"])
        self.assertIn("data_quality_level", payload)
        self.assertEqual(2.0, payload["interquartile_range"])
        self.assertEqual(0, payload["outlier_count"])
        self.assertTrue(histogram_svg_exists)
        self.assertTrue(ecdf_svg_exists)
        self.assertTrue(qq_svg_exists)
        self.assertTrue(pp_svg_exists)
        self.assertEqual(report.sample_size, len(payload["qq_points"]))
        self.assertEqual(report.sample_size, len(payload["pp_points"]))
        self.assertIn(report.best_distribution, payload["diagnostics_by_distribution"])
        self.assertEqual(
            report.sample_size,
            len(payload["diagnostics_by_distribution"][report.best_distribution]["qq_points"]),
        )
        self.assertIn("Ranking de distribuições", markdown)
        self.assertIn("Classificação local da qualidade", markdown)
        self.assertIn("Histograma textual", markdown)
        self.assertIn("Possíveis outliers por IQR", markdown)
        self.assertIn("Gráficos gerados", markdown)
        self.assertIn("BIC", markdown)
        self.assertIn("Formato aceito", markdown)
        self.assertIn("Snippet JaamSim sugerido", markdown)
        self.assertIn("Tipo de ajuste", markdown)
        self.assertIn("Suporte assumido", markdown)

    def test_requires_column_for_multicolumn_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_file = Path(tmp) / "tempos.csv"
            data_file.write_text("tempo,fila\n1.0,2\n2.0,3\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "--column"):
                statfit.read_dataset(data_file)

    def test_reads_single_numeric_value_per_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_file = Path(tmp) / "valores.txt"
            data_file.write_text("1.0\n2.0\n3.5\n", encoding="utf-8")

            series = statfit.read_dataset(data_file)

        self.assertEqual("valor", series.column)
        self.assertEqual([1.0, 2.0, 3.5], series.values)

    def test_example_mentions_required_column(self):
        example = statfit.render_example()

        self.assertIn("tempo_atendimento", example)
        self.assertIn("--column tempo_atendimento", example)

    def test_manual_values_are_supported_for_quick_checks(self):
        series = statfit.read_manual_values("1.0\n2.0\n3.0")
        report = statfit.analyze_series(series)

        self.assertEqual("manual", series.source)
        self.assertEqual(3, report.sample_size)
        self.assertTrue(report.candidates)

    def test_space_separated_manual_values_are_supported(self):
        series = statfit.read_manual_values("10 12 14 16 18 20")

        self.assertEqual([10.0, 12.0, 14.0, 16.0, 18.0, 20.0], series.values)

    def test_pasted_excel_column_is_cleaned_like_power_query_light(self):
        pasted = """
Cronometragem do Tempo de Atendimento Consultorio (s)
165
200
223
170
209
354
153
163

159
160
242
156
161
293
158
150
197
176
164
161
287
435
160
329
201
165
147
179
148
217
142
263
139
143
375
174
226
138
303
332
"""
        series = statfit.read_manual_values(pasted)

        self.assertEqual(40, len(series.values))
        self.assertEqual(8317, sum(series.values))
        self.assertAlmostEqual(207.925, statfit.mean(series.values), places=3)

    def test_auto_clean_detects_numeric_column_in_messy_copy(self):
        messy = """
linha\tCronometragem do Tempo de Atendimento Consultorio (s)\tobservacao
1\t165\tok
2\t200\tok
3\t223\tok
4\t170\tok
"""
        series = statfit.read_flexible_text(
            messy,
            "clipboard",
            "Cronometragem do Tempo de Atendimento Consultorio (s)",
        )

        self.assertEqual([165.0, 200.0, 223.0, 170.0], series.values)

    def test_auto_clean_file_can_ignore_header_and_index_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_file = Path(tmp) / "dados_sujos.csv"
            data_file.write_text(
                "Titulo exportado do Excel\n"
                "linha;tempo_atendimento;vazio\n"
                "1;165;\n"
                "2;200;\n"
                "3;223;\n",
                encoding="utf-8",
            )

            series = statfit.read_dataset(data_file, auto_clean=True)

        self.assertEqual("coluna_detectada_2", series.column)
        self.assertEqual([165.0, 200.0, 223.0], series.values)

    def test_writes_jaamsim_cfg_snippet_for_manual_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            series = statfit.read_manual_values("1.0;2.0;3.0;4.0;5.0")
            series.column = "tempo_atendimento"
            report = statfit.analyze_series(series)
            snippet_path = statfit.write_jaamsim_snippet(
                report,
                tmp_path,
                jaamsim_object_name="TempoAtendimentoDist",
                unit_type="TimeUnit",
                unit="s",
                random_seed=42,
            )
            snippet = snippet_path.read_text(encoding="utf-8")

        self.assertTrue(snippet_path.name.endswith("_jaamsim_distribution.cfg"))
        self.assertIn("Define", snippet)
        self.assertIn("TempoAtendimentoDist UnitType { TimeUnit }", snippet)
        self.assertIn("TempoAtendimentoDist RandomSeed { 42 }", snippet)
        self.assertIn("Não altera topologia", snippet)

    def test_triangular_candidate_and_histogram_are_reported(self):
        series = statfit.read_manual_values("1;2;2;3;3;4;4;5")
        report = statfit.analyze_series(series)

        distributions = {candidate.distribution for candidate in report.candidates}

        self.assertIn("triangular", distributions)
        self.assertEqual(2.0, report.q1)
        self.assertEqual(3.0, report.median)
        self.assertEqual(4.0, report.q3)
        self.assertTrue(report.histogram)
        self.assertTrue(report.empirical_cdf)

    def test_empty_manual_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Entrada sem valores numericos"):
            statfit.read_manual_values("   \n\n")

    def test_text_without_numbers_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Não encontrei valores numéricos"):
            statfit.read_flexible_text("tempo\nalto\nmedio\nbaixo", "clipboard")

    def test_single_value_is_rejected_by_analyzer(self):
        series = statfit.read_manual_values("42")

        with self.assertRaisesRegex(ValueError, "pelo menos 2 valores"):
            statfit.analyze_series(series)

    def test_small_sample_is_classified_as_weak(self):
        series = statfit.read_manual_values("1\n2\n3\n4")
        report = statfit.analyze_series(series)

        self.assertEqual("fraca", report.data_quality_level)

    def test_pedagogical_guidance_explains_process_plausibility(self):
        series = statfit.read_manual_values("4.8\n5.1\n5.5\n6.0\n6.3\n6.8\n7.1\n7.4")
        series.column = "tempo_atendimento_medico"
        report = statfit.analyze_series(series)
        markdown = statfit.render_markdown(report)
        guidance = "\n".join(report.pedagogical_guidance).lower()

        self.assertIn("plausibilidade", guidance)
        self.assertIn("atendimento", guidance)
        self.assertIn("Orientacao pedagogica offline", markdown)

    def test_decimal_comma_and_units_are_normalized(self):
        series = statfit.read_manual_values("1,5 s\n2,75 segundos\n3,0 min")

        self.assertEqual([1.5, 2.75, 3.0], series.values)

    def test_interval_text_is_normalized_as_midpoint(self):
        series = statfit.read_manual_values("3-4 minutos\n5 a 7 min\n8")

        self.assertEqual([3.5, 6.0, 8.0], series.values)

    def test_requested_column_accepts_decimal_units_and_intervals(self):
        text = "tempo_atendimento\n1,5 s\n2,75 segundos\n3-4 minutos\n5 a 7 min\n8\n"

        series = statfit.read_flexible_text(text, "clipboard", "tempo_atendimento")

        self.assertEqual([1.5, 2.75, 3.5, 6.0, 8.0], series.values)

    def test_thousand_separator_decimal_comma_and_units_are_normalized(self):
        series = statfit.read_manual_values("1.234,5 s\n2.000,0 s\n3.500 s")

        self.assertEqual([1234.5, 2000.0, 3500.0], series.values)

    def test_auto_clean_chooses_measurement_not_index_when_column_unspecified(self):
        messy = """
1\t165
2\t200
3\t223
4\t170
5\t209
6\t354
"""
        series = statfit.read_flexible_text(messy, "clipboard")

        self.assertEqual("coluna_detectada_2", series.column)
        self.assertEqual([165.0, 200.0, 223.0, 170.0, 209.0, 354.0], series.values)

    def test_requested_missing_column_falls_back_to_best_numeric_column(self):
        messy = """
linha;tempo;obs
1;10;ok
2;20;ok
3;30;ok
"""
        series = statfit.read_flexible_text(messy, "clipboard", "coluna_inexistente")

        self.assertEqual("coluna_inexistente", series.column)
        self.assertEqual([10.0, 20.0, 30.0], series.values)

    def test_constant_values_warn_about_repeated_values(self):
        series = statfit.read_manual_values("5\n5\n5\n5\n5")
        report = statfit.analyze_series(series)

        self.assertTrue(any("Poucos valores distintos" in warning for warning in report.warnings))

    def test_outliers_are_reported_for_manual_review(self):
        series = statfit.read_manual_values("10\n11\n10\n12\n11\n10\n400")
        report = statfit.analyze_series(series)

        self.assertEqual(1, report.outlier_count)
        self.assertEqual("triagem_com_cautela", report.data_quality_level)
        self.assertTrue(any("Possíveis outliers" in warning for warning in report.warnings))

    def test_cli_prints_quality_iqr_and_outlier_summary_for_native_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_file = tmp_path / "tempos.txt"
            data_file.write_text("10\n11\n10\n12\n11\n10\n400\n", encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = statfit.main([str(data_file), "--output-dir", str(tmp_path / "out")])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("Classificação qualidade:", output)
        self.assertIn("IQR:", output)
        self.assertIn("Outliers IQR:", output)
        self.assertIn("Gráfico Q-Q:", output)
        self.assertIn("Gráfico P-P:", output)

    def test_qq_and_pp_diagnostic_points_are_bounded_and_ordered(self):
        series = statfit.read_manual_values("10\n11\n12\n13\n14\n15\n16\n17")
        report = statfit.analyze_series(series)

        theoretical_quantiles = [item["theoretical"] for item in report.qq_points]
        pp_theoretical = [item["theoretical"] for item in report.pp_points]
        pp_empirical = [item["empirical"] for item in report.pp_points]

        self.assertEqual(report.sample_size, len(report.qq_points))
        self.assertEqual(report.sample_size, len(report.pp_points))
        self.assertEqual(sorted(theoretical_quantiles), theoretical_quantiles)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in pp_theoretical))
        self.assertTrue(all(0.0 < value < 1.0 for value in pp_empirical))

    def test_support_positive_prioritizes_positive_distributions(self):
        series = statfit.read_manual_values("10\n12\n14\n16\n18\n20")
        report = statfit.analyze_series(series, support_mode="positive")

        self.assertEqual("positive", report.support_mode)
        self.assertTrue(report.candidates)
        self.assertTrue(
            all(
                candidate.distribution in {"lognormal", "exponential", "gamma", "weibull", "erlang"}
                for candidate in report.candidates
            )
        )

    def test_positive_catalog_includes_gamma_weibull_and_erlang(self):
        series = statfit.read_manual_values("10\n12\n14\n16\n18\n20")
        report = statfit.analyze_series(series, support_mode="positive")
        distributions = {candidate.distribution for candidate in report.candidates}

        self.assertIn("gamma", distributions)
        self.assertIn("weibull", distributions)
        self.assertIn("erlang", distributions)

    def test_bounded_catalog_includes_beta(self):
        series = statfit.read_manual_values("10\n12\n13\n17\n19\n21\n22\n24")
        report = statfit.analyze_series(series, support_mode="bounded")
        distributions = {candidate.distribution for candidate in report.candidates}

        self.assertIn("beta", distributions)
        beta = next(candidate for candidate in report.candidates if candidate.distribution == "beta")
        self.assertTrue(beta.display_expression.startswith("Beta("))

    def test_discrete_mode_is_marked_as_triage(self):
        series = statfit.read_manual_values("1\n2\n3\n4\n5\n6")
        report = statfit.analyze_series(series, fit_kind="discrete")

        self.assertEqual("discrete", report.fit_kind)
        self.assertTrue(
            any(candidate.distribution in {"poisson", "discrete_uniform", "empirical_discrete"} for candidate in report.candidates)
        )
        self.assertTrue(any("Modo discreto" in warning for warning in report.warnings))

    def test_poisson_candidate_for_integer_counts(self):
        series = statfit.read_manual_values("2\n3\n4\n5\n3\n2\n4\n3\n5\n4")
        report = statfit.analyze_series(series, fit_kind="discrete", support_mode="unbounded")
        distributions = {candidate.distribution for candidate in report.candidates}

        self.assertIn("poisson", distributions)
        poisson = next(candidate for candidate in report.candidates if candidate.distribution == "poisson")
        self.assertAlmostEqual(3.5, poisson.parameters["mean"], places=6)
        self.assertEqual("Poisson(λ=3,5)", poisson.display_expression)

    def test_empirical_discrete_snippet_uses_value_and_probability_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            series = statfit.read_manual_values("1\n1\n2\n3")
            report = statfit.analyze_series(series, fit_kind="discrete", support_mode="bounded")
            empirical = next(candidate for candidate in report.candidates if candidate.distribution == "empirical_discrete")
            report.candidates = [empirical]
            snippet_path = statfit.write_jaamsim_snippet(
                report,
                tmp_path,
                jaamsim_object_name="ComprasPorCliente",
                unit_type="DimensionlessUnit",
                unit="",
            )
            snippet = snippet_path.read_text(encoding="utf-8")

        self.assertIn("Define DiscreteDistribution", snippet)
        self.assertIn("ComprasPorClienteDist UnitType { DimensionlessUnit }", snippet)
        self.assertIn("ComprasPorClienteDist ValueList { 1 2 3 }", snippet)
        self.assertIn("ComprasPorClienteDist ProbabilityList { 0.5 0.25 0.25 }", snippet)

    def test_gamma_snippet_uses_jaamsim_mean_and_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            series = statfit.read_manual_values("10\n12\n14\n16\n18\n20")
            report = statfit.analyze_series(series, support_mode="positive")
            gamma = next(candidate for candidate in report.candidates if candidate.distribution == "gamma")
            report.candidates = [gamma]
            snippet_path = statfit.write_jaamsim_snippet(
                report,
                tmp_path,
                jaamsim_object_name="TempoPositivo",
                unit_type="TimeUnit",
                unit="min",
            )
            snippet = snippet_path.read_text(encoding="utf-8")

        self.assertIn("Define GammaDistribution", snippet)
        self.assertIn("TempoPositivoDist Mean {", snippet)
        self.assertIn("TempoPositivoDist Shape {", snippet)

    def test_beta_snippet_uses_location_scale_and_shape_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            series = statfit.read_manual_values("10\n12\n13\n17\n19\n21\n22\n24")
            report = statfit.analyze_series(series, support_mode="bounded")
            beta = next(candidate for candidate in report.candidates if candidate.distribution == "beta")
            report.candidates = [beta]
            snippet_path = statfit.write_jaamsim_snippet(
                report,
                tmp_path,
                jaamsim_object_name="TempoLimitado",
                unit_type="TimeUnit",
                unit="s",
            )
            snippet = snippet_path.read_text(encoding="utf-8")

        self.assertIn("Define BetaDistribution", snippet)
        self.assertIn("TempoLimitadoDist Location {", snippet)
        self.assertIn("TempoLimitadoDist Scale {", snippet)
        self.assertIn("TempoLimitadoDist AlphaParam {", snippet)
        self.assertIn("TempoLimitadoDist BetaParam {", snippet)

    def test_candidates_include_triage_decision_fields(self):
        series = statfit.DataSeries(
            source="inline",
            column="tempo",
            values=[165, 200, 223, 170, 209, 354, 153, 163, 159, 160, 242, 156],
        )

        report = statfit.analyze_series(series)

        self.assertTrue(report.candidates)
        for candidate in report.candidates:
            self.assertIsNotNone(candidate.ks_critical)
            self.assertIn(candidate.fit_decision, {"nao_rejeitada", "rejeitada", "inconclusiva"})
            self.assertIsNotNone(candidate.score)
            self.assertTrue(candidate.display_expression)


if __name__ == "__main__":
    unittest.main()
