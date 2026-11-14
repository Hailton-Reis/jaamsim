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


if __name__ == "__main__":
    unittest.main()
