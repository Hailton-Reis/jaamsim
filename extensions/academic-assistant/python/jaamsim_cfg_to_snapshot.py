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
    # Neutral operations documented by the exact JaamSim 2026-03 hierarchy.
    "Assign": "operation",
    "SetGraphics": "operation",
    "EntityDelay": "operation",
    "Release": "operation",
    "Seize": "operation",
    "Duplicate": "operation",
    "Statistics": "operation",
    "Pack": "operation",
    "Unpack": "operation",
    "AddTo": "operation",
    "RemoveFrom": "operation",
    "EntitySignal": "operation",
    "EntityLogger": "operation",
    "SubModel": "operation",
    "SubModelStart": "operation",
    "SubModelEnd": "operation",
}
PASS_THROUGH_TYPES = {"EntityConveyor"}
PROCESS_TYPES = {"Server", "EntityProcessor"}
DUPLICATE_TYPES = {"Duplicate"}
RESOURCE_TYPES = {"Resource", "ResourceUnit", "ResourcePool"}
RESOURCE_REFERENCE_KEYWORDS = {"ResourceList", "Resource"}
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
    warnings: list[dict[str, Any]] = field(default_factory=list)


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


def read_cfg_text(path: Path) -> tuple[str, str]:
    """Prefer UTF-8/BOM; identify legacy cp1252 fallback explicitly."""
    try:
        return path.read_text(encoding="utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        return path.read_text(encoding="cp1252"), "cp1252"


def logical_cfg_statements(path: Path) -> tuple[list[str], list[str], str]:
    """Accumulate JaamSim brace-delimited statements across physical lines."""
    statements: list[str] = []
    assumptions: list[str] = []
    pending: list[str] = []
    depth = 0
    content, source_encoding = read_cfg_text(path)

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("# assumption:") or lower.startswith("# premissa:"):
            assumptions.append(line.split(":", 1)[1].strip())
            continue
        if line.startswith("#") or line == "RecordEdits":
            continue

        pending.append(line)
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            statements.append(" ".join(pending))
            pending = []
            depth = 0

    if pending:
        # Preserve incomplete statements for explicit parser warnings.
        statements.append(" ".join(pending))
    return statements, assumptions, source_encoding


def parse_cfg(path: Path) -> CfgModel:
    model = CfgModel()
    define_re = re.compile(r"^Define\s+(\S+)\s+\{(.*)\}\s*$")
    input_re = re.compile(r"""^('[^']*'|"[^"]*"|\S+)\s+(\S+)\s+\{(.*)\}\s*$""")

    statements, assumptions, source_encoding = logical_cfg_statements(path)
    model.assumptions.extend(assumptions)
    if source_encoding != "utf-8-sig":
        model.warnings.append({
            "type": "SOURCE_ENCODING_FALLBACK",
            "encoding": source_encoding,
        })

    for line in statements:
        define_match = define_re.match(line)
        if define_match:
            jaamsim_class, body = define_match.groups()
            for name in tokenise(body):
                model.classes[name] = jaamsim_class
            continue

        input_match = input_re.match(line)
        if input_match:
            object_name, keyword, body = input_match.groups()
            object_name = clean_braced_value(object_name)
            # Quoted names must stay quoted until reference tokenisation.
            # Without this, 'Fila de Espera' would turn into only 'Fila'.
            reference_keywords = {
                "NextComponent", "WaitQueue", "NextComponentList",
                "TargetComponentList", "ResourceList", "Resource", "ResourcePool",
            }
            stored_body = body.strip() if keyword in reference_keywords else clean_braced_value(body.strip())
            model.inputs.setdefault(object_name, {})[keyword] = stored_body
            if object_name == "Simulation" and keyword == "Description":
                model.description = clean_braced_value(body.strip())
            continue

        model.warnings.append({"type": "UNPARSED_STATEMENT", "statement": line[:500]})

    return model

def first_token(value: str | None) -> str | None:
    if not value:
        return None
    tokens = tokenise(value)
    return tokens[0] if tokens else None


def custom_submodel_classes(model: CfgModel) -> set[str]:
    """Identify custom classes whose prototype was declared as SubModel."""
    class_values = set(model.classes.values())
    return {
        name
        for name, jaamsim_class in model.classes.items()
        if jaamsim_class == "SubModel" and name in class_values
    }


def snapshot_type_for(model: CfgModel, jaamsim_class: str) -> str | None:
    return SNAPSHOT_TYPE_BY_JAAMSIM.get(jaamsim_class) or (
        "operation" if jaamsim_class in custom_submodel_classes(model) else None
    )


def build_object_ids(model: CfgModel) -> dict[str, str]:
    used: set[str] = set()
    object_ids: dict[str, str] = {}
    for name, jaamsim_class in model.classes.items():
        if snapshot_type_for(model, jaamsim_class) is None:
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

        # Operations such as Seize also consume WaitQueue.
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

        if jaamsim_class in DUPLICATE_TYPES:
            for target in tokenise(inputs.get("TargetComponentList", "")):
                resolved = resolve_flow_target(model, target, object_ids)
                if resolved:
                    add_connection(connections, seen, source_id, object_ids[resolved], "duplicate_flow")

    return connections

def build_components(model: CfgModel, object_ids: dict[str, str]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    custom_submodels = custom_submodel_classes(model)
    for name, object_id in object_ids.items():
        jaamsim_class = model.classes[name]
        component = {
            "id": object_id,
            "name": humanize(name),
            "type": snapshot_type_for(model, jaamsim_class),
            "jaamsim_class": jaamsim_class,
            "parameters": dict(model.inputs.get(name, {})),
            "description": f"Objeto JaamSim importado da classe {jaamsim_class}.",
        }
        if jaamsim_class in custom_submodels:
            component["provenance"] = "CUSTOM_SUBMODEL_INSTANCE"
            component["semantic_scope"] = "SUBMODEL_SUMMARY_ONLY"
        elif jaamsim_class == "SubModel":
            component["provenance"] = "SUBMODEL_OBJECT"
            component["semantic_scope"] = "SUBMODEL_SUMMARY_ONLY"
        elif jaamsim_class in {"SubModelStart", "SubModelEnd"}:
            component["provenance"] = "SUBMODEL_BOUNDARY"
        components.append(component)
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
                "jaamsim_name": name,
                "type": jaamsim_class,
                "parameters": dict(model.inputs.get(name, {})),
            }
        )
    return distributions


def build_resources(model: CfgModel, object_ids: dict[str, str]) -> list[dict[str, Any]]:
    """Track declared JaamSim resources using explicit input references.

    Servers are processors, not implicit resources. A ResourceUnit in a used
    ResourcePool has potential consumers, but no runtime use is asserted.
    """
    resources: list[dict[str, Any]] = []
    resources_by_name: dict[str, dict[str, Any]] = {}
    used_ids: set[str] = set()

    for name, jaamsim_class in model.classes.items():
        if jaamsim_class not in RESOURCE_TYPES:
            continue
        resource = {
            "id": unique_id(to_id(name), used_ids),
            "name": humanize(name),
            "jaamsim_class": jaamsim_class,
            "used_by": [],
            "parameters": dict(model.inputs.get(name, {})),
            "provenance": "CFG_DECLARED_RESOURCE",
        }
        resources.append(resource)
        resources_by_name[name] = resource

    # Seize/Release use ResourceList, with Resource as its keyword alias.
    # Exact token matches prevent similarly named resources from colliding.
    for owner_name, inputs in model.inputs.items():
        if owner_name not in model.classes:
            continue
        owner_id = object_ids.get(owner_name, to_id(owner_name))
        for keyword, value in inputs.items():
            if keyword not in RESOURCE_REFERENCE_KEYWORDS:
                continue
            for target_name in tokenise(value):
                resource = resources_by_name.get(target_name)
                if resource is not None and owner_id not in resource["used_by"]:
                    resource["used_by"].append(owner_id)

    # ResourcePool membership is declared by ResourceUnit.ResourcePool.
    for name, resource in resources_by_name.items():
        if model.classes[name] != "ResourceUnit":
            continue
        pool_name = first_token(model.inputs.get(name, {}).get("ResourcePool"))
        if not pool_name or model.classes.get(pool_name) != "ResourcePool":
            continue
        pool = resources_by_name.get(pool_name)
        if pool is None:
            continue
        for consumer in pool["used_by"]:
            if consumer not in resource["used_by"]:
                resource["used_by"].append(consumer)

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


def build_metrics(model: CfgModel, object_ids: dict[str, str]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    used: set[str] = set()
    for name, inputs in model.inputs.items():
        data_source = inputs.get("DataSource")
        if not data_source:
            continue
        target_match = re.search(r"\[([^\]]+)\]", data_source)
        target_name = target_match.group(1) if target_match else ""
        target_id = object_ids.get(target_name, to_id(target_name)) if target_name else "model"
        metric_id = unique_id(f"metric_{to_id(name)}", used)
        metrics.append({
            "id": metric_id,
            "name": metric_name(name, inputs),
            "target": target_id,
            "data_source": data_source,
            "expression": data_source,
            "source_object": name,
            "source_class": model.classes.get(name),
            "requires_data_source": True,
            "provenance": "CFG_DATASOURCE",
        })
    return metrics


def build_parser_warnings(model: CfgModel, object_ids: dict[str, str]) -> list[dict[str, Any]]:
    warnings = list(model.warnings)
    for name, jaamsim_class in model.classes.items():
        inputs = model.inputs.get(name, {})
        for keyword in ("NextComponent", "NextComponentList", "TargetComponentList", "WaitQueue"):
            raw = inputs.get(keyword)
            if not raw:
                continue
            for target in tokenise(raw):
                if target in object_ids:
                    continue
                if model.classes.get(target) in PASS_THROUGH_TYPES:
                    if resolve_flow_target(model, target, object_ids):
                        continue
                warnings.append({
                    "type": "UNSUPPORTED_OR_UNRESOLVED_FLOW_TARGET",
                    "object": name,
                    "jaamsim_class": jaamsim_class,
                    "keyword": keyword,
                    "target": target,
                    "target_class": model.classes.get(target),
                })

    custom_submodels = custom_submodel_classes(model)
    for name, jaamsim_class in model.classes.items():
        if name not in object_ids:
            continue
        if jaamsim_class == "SubModel" or jaamsim_class in custom_submodels:
            warnings.append({
                "type": "SUBMODEL_SEMANTICS_PARTIAL",
                "object": name,
                "jaamsim_class": jaamsim_class,
                "semantic_scope": "SUBMODEL_SUMMARY_ONLY",
            })
    return warnings

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
        "parser_schema_version": "R001-v6-bridge",
        "parser_warnings": build_parser_warnings(model, object_ids),
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
