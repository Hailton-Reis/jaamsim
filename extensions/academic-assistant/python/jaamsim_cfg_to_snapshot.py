#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""
Conversor inicial de arquivos JaamSim .cfg para um snapshot JSON estruturado.

Escopo desta versao:
- ler arquivos .cfg textuais do JaamSim;
- mapear EntityGenerator, Queue, Server, EntityProcessor, Branch e EntitySink;
- achatar EntityConveyor como elemento de passagem no fluxo;
- extrair metricas declaradas por objetos Text com DataSource;
- gerar JSON compativel com snapshot_analyzer.py.

Limitacao assumida: este script e um MVP academico. Ele cobre o caso C1 e
exemplos simples do JaamSim, mas ainda nao e um parser completo do simulador.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT_TYPE_BY_JAAMSIM = {
    "EntityGenerator": "source",
    "Queue": "queue",
    "Server": "process",
    "EntityProcessor": "process",
    "Branch": "decision",
    "EntitySink": "sink",
}
PASS_THROUGH_TYPES = {"EntityConveyor"}
PROCESS_TYPES = {"Server", "EntityProcessor"}
RESOURCE_TYPES = {"ResourceUnit", "ResourcePool"}
DISTRIBUTION_TYPES = {
    "BetaDistribution",
    "DiscreteDistribution",
    "ErlangDistribution",
    "ExponentialDistribution",
    "GammaDistribution",
    "LogNormalDistribution",
    "NormalDistribution",
    "TriangularDistribution",
    "UniformDistribution",
    "WeibullDistribution",
}


@dataclass
class CfgModel:
    classes: dict[str, str] = field(default_factory=dict)
    inputs: dict[str, dict[str, str]] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    description: str = ""


def to_id(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return text or "item"


def unique_id(base: str, used: set[str]) -> str:
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def humanize(name: str) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    text = re.sub(r"[_-]+", " ", text)
    return " ".join(text.split()).strip() or name


def clean_braced_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def tokenise(value: str) -> list[str]:
    tokens = re.findall(r"'[^']*'|\"[^\"]*\"|[^ \t{}]+", value)
    return [clean_braced_value(token) for token in tokens]


def parse_cfg(path: Path) -> CfgModel:
    model = CfgModel()
    define_re = re.compile(r"^Define\s+(\S+)\s+\{(.*)\}\s*$")
    input_re = re.compile(r"^(\S+)\s+(\S+)\s+\{(.*)\}\s*$")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("# assumption:") or lower.startswith("# premissa:"):
            model.assumptions.append(line.split(":", 1)[1].strip())
            continue
        if line.startswith("#") or line == "RecordEdits":
            continue

        define_match = define_re.match(line)
        if define_match:
            jaamsim_class, body = define_match.groups()
            for name in tokenise(body):
                model.classes[name] = jaamsim_class
            continue

        input_match = input_re.match(line)
        if input_match:
            object_name, keyword, body = input_match.groups()
            model.inputs.setdefault(object_name, {})[keyword] = clean_braced_value(body.strip())
            if object_name == "Simulation" and keyword == "Description":
                model.description = clean_braced_value(body.strip())

    return model


def first_token(value: str | None) -> str | None:
    if not value:
        return None
    tokens = tokenise(value)
    return tokens[0] if tokens else None


def build_object_ids(model: CfgModel) -> dict[str, str]:
    used: set[str] = set()
    object_ids: dict[str, str] = {}
    for name, jaamsim_class in model.classes.items():
        if jaamsim_class not in SNAPSHOT_TYPE_BY_JAAMSIM:
            continue
        object_ids[name] = unique_id(to_id(name), used)
    return object_ids


def resolve_flow_target(model: CfgModel, target: str | None, object_ids: dict[str, str]) -> str | None:
    seen: set[str] = set()
    current = target
    while current and current not in seen:
        seen.add(current)
        if current in object_ids:
            return current
        if model.classes.get(current) in PASS_THROUGH_TYPES:
            current = first_token(model.inputs.get(current, {}).get("NextComponent"))
            continue
        return None
    return None


def add_connection(
    connections: list[dict[str, str]],
    seen: set[tuple[str, str, str]],
    source_id: str,
    target_id: str,
    connection_type: str = "entity_flow",
) -> None:
    key = (source_id, target_id, connection_type)
    if key in seen:
        return
    seen.add(key)
    connections.append({"from": source_id, "to": target_id, "type": connection_type})


def build_connections(model: CfgModel, object_ids: dict[str, str]) -> list[dict[str, str]]:
    connections: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for name, jaamsim_class in model.classes.items():
        if name not in object_ids:
            continue
        source_id = object_ids[name]
        inputs = model.inputs.get(name, {})

        if jaamsim_class in PROCESS_TYPES:
            queue_name = first_token(inputs.get("WaitQueue"))
            if queue_name in object_ids:
                add_connection(connections, seen, object_ids[queue_name], source_id)

        next_component = resolve_flow_target(model, first_token(inputs.get("NextComponent")), object_ids)
        if next_component:
            add_connection(connections, seen, source_id, object_ids[next_component])

        if jaamsim_class == "Branch":
            for target in tokenise(inputs.get("NextComponentList", "")):
                resolved = resolve_flow_target(model, target, object_ids)
                if resolved:
                    add_connection(connections, seen, source_id, object_ids[resolved], "conditional_flow")

    return connections


def build_components(model: CfgModel, object_ids: dict[str, str]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for name, object_id in object_ids.items():
        jaamsim_class = model.classes[name]
        components.append(
            {
                "id": object_id,
                "name": humanize(name),
                "type": SNAPSHOT_TYPE_BY_JAAMSIM[jaamsim_class],
                "jaamsim_class": jaamsim_class,
                "parameters": dict(model.inputs.get(name, {})),
                "description": f"Objeto JaamSim importado da classe {jaamsim_class}.",
            }
        )
    return components


def build_distributions(model: CfgModel) -> list[dict[str, Any]]:
    distributions: list[dict[str, Any]] = []
    for name, jaamsim_class in model.classes.items():
        if jaamsim_class not in DISTRIBUTION_TYPES and not jaamsim_class.endswith("Distribution"):
            continue
        distributions.append(
            {
                "id": to_id(name),
                "name": humanize(name),
                "type": jaamsim_class,
                "parameters": dict(model.inputs.get(name, {})),
            }
        )
    return distributions


def build_resources(model: CfgModel, object_ids: dict[str, str]) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    used: set[str] = set()
    for name, jaamsim_class in model.classes.items():
        if jaamsim_class not in RESOURCE_TYPES:
            continue
        resource_id = unique_id(to_id(name), used)
        resources.append({"id": resource_id, "name": humanize(name), "used_by": []})

    for name, jaamsim_class in model.classes.items():
        if jaamsim_class not in PROCESS_TYPES or name not in object_ids:
            continue
        process_id = object_ids[name]
        resources.append(
            {
                "id": f"capacidade_{process_id}",
                "name": f"Capacidade de {humanize(name)}",
                "used_by": [process_id],
            }
        )
    return resources


def metric_name(object_name: str, inputs: dict[str, str]) -> str:
    if "Format" in inputs:
        value = clean_braced_value(inputs["Format"])
        value = value.split("=", 1)[0]
        value = re.sub(r"%[,.\-\d]*[A-Za-z]", "", value)
        value = value.strip()
        if value:
            return value
    data_source = inputs.get("DataSource", "")
    output_match = re.search(r"\]\.([A-Za-z0-9_]+)", data_source)
    if output_match:
        return humanize(output_match.group(1))
    return humanize(object_name)


def build_metrics(model: CfgModel, object_ids: dict[str, str]) -> list[dict[str, str]]:
    metrics: list[dict[str, str]] = []
    used: set[str] = set()
    for name, inputs in model.inputs.items():
        data_source = inputs.get("DataSource")
        if not data_source:
            continue
        target_match = re.search(r"\[([^\]]+)\]", data_source)
        target_name = target_match.group(1) if target_match else ""
        target_id = object_ids.get(target_name, to_id(target_name)) if target_name else "model"
        metric_id = unique_id(f"metric_{to_id(name)}", used)
        metrics.append({"id": metric_id, "name": metric_name(name, inputs), "target": target_id})
    return metrics


def convert_cfg_to_snapshot(
    path: Path,
    *,
    model_id: str | None = None,
    case_id: str = "C1",
    variant: str = "reference",
    title: str | None = None,
    objective: str | None = None,
) -> dict[str, Any]:
    model = parse_cfg(path)
    object_ids = build_object_ids(model)
    return {
        "model_id": model_id or to_id(path.stem),
        "case_id": case_id,
        "variant": variant,
        "title": title or humanize(path.stem),
        "objective": objective
        or "Avaliar tempo de espera, clientes atendidos e utilizacao do servidor.",
        "components": build_components(model, object_ids),
        "connections": build_connections(model, object_ids),
        "resources": build_resources(model, object_ids),
        "metrics": build_metrics(model, object_ids),
        "simulation": {"source_format": "jaamsim_cfg", **model.inputs.get("Simulation", {})},
        "distributions": build_distributions(model),
        "assumptions": model.assumptions,
        "notes": (
            "Snapshot derivado de arquivo JaamSim .cfg por conversor MVP. "
            "Revisar manualmente antes de usar como evidencia final."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Converte JaamSim .cfg para snapshot JSON estruturado.")
    parser.add_argument("cfg", type=Path, help="Arquivo .cfg do JaamSim.")
    parser.add_argument("--output", type=Path, help="Arquivo JSON de saida.")
    parser.add_argument("--model-id", help="Identificador do modelo no snapshot.")
    parser.add_argument("--case-id", default="C1", help="Identificador do caso.")
    parser.add_argument("--variant", default="reference", help="Variante do caso.")
    parser.add_argument("--title", help="Titulo do snapshot.")
    parser.add_argument("--objective", help="Objetivo do snapshot.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = convert_cfg_to_snapshot(
        args.cfg,
        model_id=args.model_id,
        case_id=args.case_id,
        variant=args.variant,
        title=args.title,
        objective=args.objective,
    )
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"Snapshot salvo em: {args.output}")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
