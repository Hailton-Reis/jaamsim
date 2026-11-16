import unittest

import snapshot_analyzer as analyzer


class SnapshotAnalyzerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expectations = analyzer.load_expectations(analyzer.MATRIX_PATH)

    def analyze_case(self, filename):
        return analyzer.analyze_file(analyzer.CASES_DIR / filename, self.expectations)

    def test_reference_snapshots_do_not_emit_alerts(self):
        for filename in [
            "c1_fila_simples_referencia.json",
            "c2_processo_sequencial_referencia.json",
            "c3_modelo_ambiguo_referencia.json",
        ]:
            with self.subTest(filename=filename):
                analysis = self.analyze_case(filename)
                self.assertEqual([], analysis.alerts)
                self.assertEqual([], analysis.omissions)
                self.assertEqual([], analysis.false_positives)

    def test_inconsistent_snapshots_match_expected_rules(self):
        cases = {
            "c1_fila_simples_inconsistente.json": {"RCL03", "RCL04", "RCL07", "RCL10"},
            "c2_processo_sequencial_inconsistente.json": {
                "RCL01",
                "RCL02",
                "RCL05",
                "RCL07",
                "RCL09",
            },
            "c3_modelo_ambiguo_inconsistente.json": {"RCL06", "RCL08", "RCL10"},
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                analysis = self.analyze_case(filename)
                triggered = {alert.rule_id for alert in analysis.alerts}
                self.assertEqual(expected, triggered)
                self.assertEqual([], analysis.omissions)
                self.assertEqual([], analysis.false_positives)

    def test_rcl2_optional_fields_trigger_new_offline_rules(self):
        components = [
            {"id": "src", "name": "Chegada", "type": "source", "parameters": {"load": "12"}},
            {"id": "proc", "name": "Atendimento", "type": "process", "parameters": {"setup_time": "12"}},
            {"id": "fila", "name": "Fila", "type": "queue", "parameters": {"max_size": "100"}},
            {"id": "dec", "name": "Decisao", "type": "decision", "parameters": {"mode": "auto"}},
            {"id": "sink", "name": "Saida", "type": "sink"},
        ]
        components.extend(
            {"id": f"ann{i}", "name": f"Nota {i}", "type": "annotation"}
            for i in range(7)
        )
        snapshot = {
            "model_id": "nat17_rcl2",
            "case_id": "NAT17",
            "variant": "synthetic",
            "title": "Teste RCL 2.0",
            "objective": "Comparar cenarios para reduzir tempo de espera",
            "components": components,
            "connections": [
                {"from": "src", "to": "proc", "type": "entity_flow"},
                {"from": "proc", "to": "fila", "type": "entity_flow"},
                {"from": "fila", "to": "dec", "type": "entity_flow"},
                {"from": "dec", "to": "sink", "type": "entity_flow"},
            ],
            "resources": [
                {"id": "rec", "name": "Atendente", "used_by": ["proc"], "parameters": {"turno": "manha"}}
            ],
            "metrics": [
                {"id": "m1", "name": "tempo medio", "requires_target": True, "requires_data_source": True}
            ],
            "assumptions": [],
            "simulation": {"validation_required": True, "metric_targets_required": True},
            "distributions": [{"id": "dist", "name": "TempoAtendimento"}],
            "data_quality_level": "fraca",
            "user_profile": "beginner",
        }

        triggered = {alert.rule_id for alert in analyzer.analyze_snapshot(snapshot)}

        self.assertTrue(
            {
                "RCL11",
                "RCL12",
                "RCL13",
                "RCL14",
                "RCL15",
                "RCL16",
                "RCL17",
                "RCL18",
                "RCL19",
                "RCL20",
                "RCL21",
                "RCL22",
                "RCL23",
                "RCL24",
                "RCL25",
            }
            <= triggered
        )


    def test_rcl23_requires_capacity_for_real_used_resource_not_pool_or_unit(self):
        snapshot = {
            "model_id": "resource_types",
            "case_id": "RESOURCE",
            "variant": "synthetic",
            "title": "Resource semantics",
            "objective": "Test capacity keyword contract",
            "components": [],
            "connections": [],
            "resources": [
                {
                    "id": "worker_missing",
                    "name": "Worker Missing",
                    "jaamsim_class": "Resource",
                    "provenance": "CFG_DECLARED_RESOURCE",
                    "parameters": {"SomeInput": "x"},
                    "used_by": ["seize_a"],
                },
                {
                    "id": "worker_defined",
                    "name": "Worker Defined",
                    "jaamsim_class": "Resource",
                    "parameters": {"Capacity": "3"},
                    "used_by": ["seize_a"],
                },
                {
                    "id": "pool",
                    "name": "Pool",
                    "jaamsim_class": "ResourcePool",
                    "parameters": {"Note": "members"},
                    "used_by": ["seize_a"],
                },
                {
                    "id": "unit",
                    "name": "Unit",
                    "jaamsim_class": "ResourceUnit",
                    "parameters": {"ResourcePool": "Pool"},
                    "used_by": ["seize_a"],
                },
                {
                    "id": "old_placeholder",
                    "name": "Old Placeholder",
                    "provenance": "DERIVED_PROCESS_CAPACITY_PLACEHOLDER",
                    "parameters": {"SomeInput": "historical"},
                    "used_by": ["server"],
                },
            ],
            "metrics": [],
            "assumptions": [],
        }
        alerts = analyzer.analyze_snapshot(snapshot)
        missing_capacity_ids = {
            item.component_id for item in alerts if item.rule_id == "RCL23"
        }
        self.assertEqual({"worker_missing"}, missing_capacity_ids)


    def test_rcl24_checks_temporal_values_and_named_distributions(self):
        def check(service_time, *, setup_time=None):
            params = {"ServiceTime": service_time}
            if setup_time is not None:
                params["SetupTime"] = setup_time
            snapshot = {
                "model_id": "temporal",
                "case_id": "RCL24",
                "variant": "synthetic",
                "title": "Temporal units",
                "objective": "Teste",
                "components": [
                    {
                        "id": "source", "name": "Chegada", "type": "source",
                        "parameters": {"InterArrivalTime": "DistChegadas"},
                    },
                    {
                        "id": "server", "name": "Atendimento", "type": "process",
                        "parameters": params,
                    },
                    {"id": "sink", "name": "Saida", "type": "sink"},
                ],
                "connections": [
                    {"from": "source", "to": "server", "type": "entity_flow"},
                    {"from": "server", "to": "sink", "type": "entity_flow"},
                ],
                "resources": [],
                "metrics": [],
                "assumptions": [],
                "distributions": [
                    {
                        "id": "dist_chegadas",
                        "name": "Dist Chegadas",
                        "jaamsim_name": "DistChegadas",
                        "type": "ExponentialDistribution",
                        "parameters": {"Mean": "2 min"},
                    }
                ],
            }
            return [
                item for item in analyzer.analyze_snapshot(snapshot)
                if item.rule_id == "RCL24"
            ]

        self.assertEqual([], check("0.85 s"))
        self.assertEqual([], check("5 min"))
        self.assertEqual([], check("DistChegadas"))
        self.assertEqual([], check("Dist Chegadas"))
        without_unit = check("0.85 s", setup_time="7")
        self.assertEqual(1, len(without_unit))
        self.assertEqual(
            [{"parameter": "SetupTime", "value": "7"}],
            without_unit[0].evidence["temporal_parameters_without_evident_unit"],
        )
        self.assertEqual(1, len(check("1")))
        self.assertEqual(1, len(check("UndefinedDistribution")))


if __name__ == "__main__":
    unittest.main()
