import tempfile
import unittest
from pathlib import Path

import jaamsim_cfg_to_snapshot as converter
import snapshot_analyzer


class JaamSimCfgToSnapshotTest(unittest.TestCase):
    def test_converts_simple_server_queue_model(self):
        cfg = """RecordEdits
# ASSUMPTION: Clientes seguem fluxo unico de atendimento.
Define EntityConveyor { ConveyorEntrada ConveyorSaida }
Define EntityGenerator { GeneratorClientes }
Define EntitySink { SinkClientes }
Define Queue { QueueEspera }
Define Server { ServerAtendimento }
Define SimEntity { Cliente }
Define ExponentialDistribution { DistChegadas }
Define Text { MetricTempoEspera MetricClientesAtendidos MetricUtilizacaoServidor }

Simulation RunDuration { 8 h }
GeneratorClientes NextComponent { ConveyorEntrada }
GeneratorClientes PrototypeEntity { Cliente }
GeneratorClientes InterArrivalTime { DistChegadas }
DistChegadas Mean { 5 min }
DistChegadas RandomSeed { 2 }
ConveyorEntrada NextComponent { QueueEspera }
ServerAtendimento WaitQueue { QueueEspera }
ServerAtendimento ServiceTime { 4 min }
ServerAtendimento NextComponent { ConveyorSaida }
ConveyorSaida NextComponent { SinkClientes }
MetricTempoEspera Format { 'Tempo medio de espera = %.2f s' }
MetricTempoEspera DataSource { [QueueEspera].AverageQueueTime }
MetricClientesAtendidos Format { 'Clientes atendidos = %,.0f' }
MetricClientesAtendidos DataSource { [QueueEspera].NumberProcessed }
MetricUtilizacaoServidor Format { 'Utilizacao do servidor = %s' }
MetricUtilizacaoServidor DataSource { [ServerAtendimento].State }
"""

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c1.cfg"
            path.write_text(cfg, encoding="utf-8")
            snapshot = converter.convert_cfg_to_snapshot(path)

        components = {item["id"]: item["type"] for item in snapshot["components"]}
        self.assertEqual(
            {
                "generator_clientes": "source",
                "sink_clientes": "sink",
                "queue_espera": "queue",
                "server_atendimento": "process",
            },
            components,
        )
        self.assertEqual(
            [
                {"from": "generator_clientes", "to": "queue_espera", "type": "entity_flow"},
                {"from": "queue_espera", "to": "server_atendimento", "type": "entity_flow"},
                {"from": "server_atendimento", "to": "sink_clientes", "type": "entity_flow"},
            ],
            snapshot["connections"],
        )
        # A Server is not an explicitly declared JaamSim Resource.
        self.assertEqual([], snapshot["resources"])
        self.assertEqual(
            ["Tempo medio de espera", "Clientes atendidos", "Utilizacao do servidor"],
            [item["name"] for item in snapshot["metrics"]],
        )
        self.assertEqual(["Clientes seguem fluxo unico de atendimento."], snapshot["assumptions"])
        component_items = {item["id"]: item for item in snapshot["components"]}
        self.assertEqual("Cliente", component_items["generator_clientes"]["parameters"]["PrototypeEntity"])
        self.assertEqual("DistChegadas", component_items["generator_clientes"]["parameters"]["InterArrivalTime"])
        self.assertEqual("4 min", component_items["server_atendimento"]["parameters"]["ServiceTime"])
        self.assertEqual("8 h", snapshot["simulation"]["RunDuration"])
        self.assertEqual("ExponentialDistribution", snapshot["distributions"][0]["type"])
        self.assertEqual("2", snapshot["distributions"][0]["parameters"]["RandomSeed"])

    def test_missing_jaamsim_inputs_are_visible_to_rcl(self):
        cfg = """RecordEdits
Define EntityGenerator { Gerador }
Define Queue { Fila }
Define Server { Atendimento }
Define EntitySink { Saida }
Gerador InterArrivalTime { 5 min }
Gerador NextComponent { Fila }
Atendimento WaitQueue { Fila }
Atendimento NextComponent { Saida }
"""

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incompleto.cfg"
            path.write_text(cfg, encoding="utf-8")
            snapshot = converter.convert_cfg_to_snapshot(path)

        triggered = {item.rule_id for item in snapshot_analyzer.analyze_snapshot(snapshot)}
        self.assertIn("RCL11", triggered)
        self.assertIn("RCL13", triggered)
        self.assertIn("RCL26", triggered)
        self.assertNotIn("RCL12", triggered)


    def test_declared_resources_use_seize_release_and_pool_references(self):
        cfg = """RecordEdits
Define EntityGenerator { SourceA }
Define EntitySink { SinkA }
Define Resource { WorkerA WorkerAA WorkerUnused }
Define ResourcePool { CrewPool }
Define ResourceUnit { CrewUnit }
Define Seize { SeizeWorker SeizePool }
Define Release { ReleaseWorker }
SourceA NextComponent { SinkA }
SeizeWorker ResourceList { WorkerA WorkerAA }
ReleaseWorker Resource { WorkerA }
SeizePool ResourceList { CrewPool }
CrewUnit ResourcePool { CrewPool }
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resource-links.cfg"
            path.write_text(cfg, encoding="utf-8")
            snapshot = converter.convert_cfg_to_snapshot(path)

        resources = {item["id"]: item for item in snapshot["resources"]}
        self.assertEqual(
            {"worker_a", "worker_aa", "worker_unused", "crew_pool", "crew_unit"},
            set(resources),
        )
        self.assertEqual(["seize_worker", "release_worker"], resources["worker_a"]["used_by"])
        self.assertEqual(["seize_worker"], resources["worker_aa"]["used_by"])
        self.assertEqual([], resources["worker_unused"]["used_by"])
        self.assertEqual(["seize_pool"], resources["crew_pool"]["used_by"])
        self.assertEqual(["seize_pool"], resources["crew_unit"]["used_by"])
        self.assertEqual("Resource", resources["worker_a"]["jaamsim_class"])
        resource_alerts = {
            item.component_id
            for item in snapshot_analyzer.analyze_snapshot(snapshot)
            if item.rule_id == "RCL03"
        }
        self.assertEqual({"worker_unused"}, resource_alerts)

    def test_resource_reference_uses_exact_object_name(self):
        cfg = """RecordEdits
Define Resource { Worker Worker2 }
Define Seize { SeizeWorker2 }
SeizeWorker2 ResourceList { Worker2 }
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resource-exact.cfg"
            path.write_text(cfg, encoding="utf-8")
            snapshot = converter.convert_cfg_to_snapshot(path)

        resources = {item["id"]: item for item in snapshot["resources"]}
        self.assertEqual([], resources["worker"]["used_by"])
        self.assertEqual(["seize_worker2"], resources["worker2"]["used_by"])


    def test_multiline_cp1252_quoted_names_and_resource_capacity(self):
        cfg = """RecordEdits
# Premissa: Atendimento com referência explícita à equipe.
Define EntityGenerator { 'Gerador Principal' }
Define Queue {
    'Fila de Espera'
}
Define Seize { 'Seize Worker' }
Define EntitySink { 'Saida Final' }
Define Resource { Worker1 }
'Gerador Principal' NextComponent {
    'Fila de Espera'
}
'Seize Worker' WaitQueue { 'Fila de Espera' }
'Seize Worker' NextComponent { 'Saida Final' }
'Seize Worker' ResourceList { Worker1 }
Worker1 Capacity { 2 }
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "multiline_quoted.cfg"
            path.write_bytes(cfg.encode("cp1252"))
            snapshot = converter.convert_cfg_to_snapshot(path)

        self.assertEqual("R001-v6-bridge", snapshot["parser_schema_version"])
        self.assertEqual(4, len(snapshot["components"]))
        self.assertEqual(
            [
                {"from": "gerador_principal", "to": "fila_de_espera", "type": "entity_flow"},
                {"from": "fila_de_espera", "to": "seize_worker", "type": "entity_flow"},
                {"from": "seize_worker", "to": "saida_final", "type": "entity_flow"},
            ],
            snapshot["connections"],
        )
        self.assertEqual(["Atendimento com referência explícita à equipe."], snapshot["assumptions"])
        resource = snapshot["resources"][0]
        self.assertEqual(["seize_worker"], resource["used_by"])
        self.assertEqual({"Capacity": "2"}, resource["parameters"])
        self.assertEqual("CFG_DECLARED_RESOURCE", resource["provenance"])
        self.assertNotIn(
            "UNSUPPORTED_OR_UNRESOLVED_FLOW_TARGET",
            [w["type"] for w in snapshot["parser_warnings"]],
        )
        self.assertIn(
            "SOURCE_ENCODING_FALLBACK",
            [w["type"] for w in snapshot["parser_warnings"]],
        )
        rules = {a.rule_id for a in snapshot_analyzer.analyze_snapshot(snapshot)}
        self.assertNotIn("RCL04", rules)
        self.assertNotIn("RCL23", rules)

    def test_utf8_bom_and_metric_lineage(self):
        cfg = """RecordEdits
Define Queue { QueueA }
Define Text { 'Metric Queue' }
'Metric Queue' Format { 'Tempo medio = %.2f s' }
'Metric Queue' DataSource { [QueueA].AverageQueueTime }
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metric.cfg"
            path.write_text(cfg, encoding="utf-8-sig")
            snapshot = converter.convert_cfg_to_snapshot(path)

        self.assertEqual([], snapshot["parser_warnings"])
        self.assertEqual(1, len(snapshot["metrics"]))
        metric = snapshot["metrics"][0]
        self.assertEqual("metric_metric_queue", metric["id"])
        self.assertEqual("queue_a", metric["target"])
        self.assertEqual("[QueueA].AverageQueueTime", metric["data_source"])
        self.assertEqual("Metric Queue", metric["source_object"])
        self.assertEqual("Text", metric["source_class"])
        self.assertTrue(metric["requires_data_source"])
        self.assertEqual("CFG_DATASOURCE", metric["provenance"])

    def test_unparsed_statements_and_unresolved_links_are_reported(self):
        cfg = """RecordEdits
Define EntityGenerator { Generator }
Define Mystery { Secret }
Generator NextComponent { Secret }
Broken invalid input
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unknown.cfg"
            path.write_text(cfg, encoding="utf-8")
            snapshot = converter.convert_cfg_to_snapshot(path)

        warnings = snapshot["parser_warnings"]
        self.assertEqual(
            {"UNPARSED_STATEMENT", "UNSUPPORTED_OR_UNRESOLVED_FLOW_TARGET"},
            {item["type"] for item in warnings},
        )
        self.assertEqual([], snapshot["connections"])
        link = next(item for item in warnings if item["type"] == "UNSUPPORTED_OR_UNRESOLVED_FLOW_TARGET")
        self.assertEqual("Secret", link["target"])
        self.assertEqual("Mystery", link["target_class"])

    def test_duplicate_edges_and_custom_submodel_partial_warning(self):
        cfg = """RecordEdits
Define SubModel { Workstation }
Define Workstation { Workstation1 }
Define EntityGenerator { Source }
Define Duplicate { Split }
Define EntitySink { Sink1 Sink2 }
Source NextComponent { Split }
Split NextComponent { Sink1 }
Split TargetComponentList { Workstation1 Sink2 }
Workstation1 NextComponent { Sink2 }
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate_submodel.cfg"
            path.write_text(cfg, encoding="utf-8")
            snapshot = converter.convert_cfg_to_snapshot(path)

        comps = {c["id"]: c for c in snapshot["components"]}
        self.assertEqual("operation", comps["split"]["type"])
        self.assertEqual("operation", comps["workstation1"]["type"])
        self.assertEqual("CUSTOM_SUBMODEL_INSTANCE", comps["workstation1"]["provenance"])
        self.assertEqual("SUBMODEL_SUMMARY_ONLY", comps["workstation1"]["semantic_scope"])
        self.assertIn(
            {"from": "split", "to": "workstation1", "type": "duplicate_flow"},
            snapshot["connections"],
        )
        self.assertIn(
            {"from": "split", "to": "sink2", "type": "duplicate_flow"},
            snapshot["connections"],
        )
        self.assertEqual(
            {"Workstation", "Workstation1"},
            {w["object"] for w in snapshot["parser_warnings"] if w["type"] == "SUBMODEL_SEMANTICS_PARTIAL"},
        )
        self.assertFalse(
            any(w["type"] == "UNSUPPORTED_OR_UNRESOLVED_FLOW_TARGET" for w in snapshot["parser_warnings"])
        )

    def test_resource_pool_with_unit_does_not_require_artificial_capacity(self):
        cfg = """RecordEdits
Define ResourcePool { PoolA }
Define ResourceUnit { UnitA }
Define Seize { SeizePool }
UnitA ResourcePool { PoolA }
SeizePool ResourceList { PoolA }
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pool.cfg"
            path.write_text(cfg, encoding="utf-8")
            snapshot = converter.convert_cfg_to_snapshot(path)

        resources = {r["id"]: r for r in snapshot["resources"]}
        self.assertEqual(["seize_pool"], resources["unit_a"]["used_by"])
        self.assertEqual({"ResourcePool": "PoolA"}, resources["unit_a"]["parameters"])
        triggered = {a.rule_id for a in snapshot_analyzer.analyze_snapshot(snapshot)}
        self.assertNotIn("RCL03", triggered)
        self.assertNotIn("RCL23", triggered)


if __name__ == "__main__":
    unittest.main()
