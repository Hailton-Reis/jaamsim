#!/usr/bin/env python3
# Copyright 2026 Hailton Santos Reis
# SPDX-License-Identifier: Apache-2.0

"""
Modulo auxiliar StatFit-like para o JaamSim Academic Assistant.

O objetivo é apoiar a escolha inicial de distribuições a partir de dados
numéricos importados, mantendo o escopo offline, auditável e leve. O módulo
não substitui ferramentas estatísticas completas nem validação por domínio.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from html import escape
import io
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import assistant_paths
import runtime_provenance


ROOT = assistant_paths.ASSISTANT_ROOT
DEFAULT_OUTPUT_DIR = assistant_paths.OUTPUT_DIR / "statfit"

MIN_RECOMMENDED_SAMPLE = 30
EPSILON = 1e-12
NUMERICAL_EPSILON = 1e-10
MAX_NUMERICAL_ITERATIONS = 200
NUMBER_TOKEN_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d+)?"
    r"(?=\s*(?:segundos|segundo|seg|secs|sec|minutos|minuto|min|horas|hora|hrs|hr|h|s)?\b|$)",
    flags=re.IGNORECASE,
)
NUMBER_PATTERN = r"[-+]?(?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d+)?"
RANGE_TOKEN_RE = re.compile(
    rf"^\s*({NUMBER_PATTERN})\s*(?:-|\u2013|\u2014|a|ate)\s*({NUMBER_PATTERN})"
    r"\s*(?:segundos|segundo|seg|secs|sec|minutos|minuto|min|horas|hora|hrs|hr|h|s)?\s*$",
    flags=re.IGNORECASE,
)

EXAMPLE_DATA = """tempo_atendimento
4.20
5.10
3.80
6.40
4.90
"""


@dataclass
class DataSeries:
    source: str
    column: str
    values: list[float]


@dataclass
class FitCandidate:
    distribution: str
    ks_statistic: float
    aic: float
    bic: float
    parameters: dict[str, float | list[float]]
    jaamsim_hint: str
    display_expression: str
    notes: list[str]
    ks_critical: float | None = None
    fit_decision: str = "inconclusiva"
    score: float | None = None


@dataclass
class FitReport:
    source: str
    column: str
    fit_kind: str
    support_mode: str
    sample_size: int
    data_quality_level: str
    minimum: float
    maximum: float
    mean: float
    median: float
    q1: float
    q3: float
    interquartile_range: float
    outlier_count: int
    standard_deviation: float
    coefficient_of_variation: float | None
    best_distribution: str
    candidates: list[FitCandidate]
    histogram: list[dict[str, float | int]]
    empirical_cdf: list[dict[str, float]]
    qq_points: list[dict[str, float]]
    pp_points: list[dict[str, float]]
    diagnostics_by_distribution: dict[str, dict[str, list[dict[str, float]]]]
    chart_files: dict[str, str]
    warnings: list[str]
    pedagogical_guidance: list[str]


def safe_jaamsim_name(raw_name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", raw_name)
    name = "".join(part[:1].upper() + part[1:] for part in parts) or "Distribuicao"
    if name[0].isdigit():
        name = f"Distribuicao{name}"
    if not name.endswith("Dist"):
        name = f"{name}Dist"
    return name


def parse_number(raw_value: str, *, line_number: int, column: str) -> float:
    parsed = try_parse_number(raw_value)
    if parsed is None:
        value = raw_value.strip()
        if not value:
            raise ValueError(f"Linha {line_number}: valor vazio na coluna '{column}'.")
        raise ValueError(
            f"Linha {line_number}: valor '{raw_value}' não é numérico na coluna '{column}'."
        )

    if not math.isfinite(parsed):
        raise ValueError(f"Linha {line_number}: valor '{raw_value}' não é finito.")

    return parsed


def normalize_number_text(raw_value: str) -> str:
    value = str(raw_value).strip().replace("\u00a0", " ").replace("\u202f", " ")
    value = value.strip("'\"")
    value = re.sub(r"(?i)\b(segundos|segundo|seg|secs|sec|minutos|minuto|min|horas|hora|hrs|hr|h|s)\b", "", value)
    value = value.strip().replace(" ", "")
    if not value:
        raise ValueError("valor vazio")

    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        if re.fullmatch(r"[-+]?\d{1,3}(,\d{3})+", value):
            value = value.replace(",", "")
        else:
            value = value.replace(",", ".")
    elif "." in value and re.fullmatch(r"[-+]?\d{1,3}(\.\d{3})+", value):
        value = value.replace(".", "")

    return value


def try_parse_number(raw_value: str) -> float | None:
    try:
        return float(normalize_number_text(raw_value))
    except (TypeError, ValueError):
        return None


def split_messy_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped:
        return []
    if "\t" in stripped:
        return [cell.strip() for cell in stripped.split("\t")]
    if ";" in stripped:
        return [cell.strip() for cell in stripped.split(";")]
    decimal_comma_with_unit = re.fullmatch(
        rf"{NUMBER_PATTERN}\s*(?:segundos|segundo|seg|secs|sec|minutos|minuto|min|horas|hora|hrs|hr|h|s)?",
        stripped,
        flags=re.IGNORECASE,
    )
    if "," in stripped and not re.fullmatch(r"[-+]?\d+,\d+", stripped) and not decimal_comma_with_unit:
        return [cell.strip() for cell in next(csv.reader([stripped]))]
    return [cell.strip() for cell in re.split(r"\s{2,}", stripped) if cell.strip()] or [stripped]


def normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def extract_numeric_tokens(cell: str) -> list[float]:
    matches = NUMBER_TOKEN_RE.findall(cell)
    has_inner_spaces = bool(re.search(r"\d\s+\d", cell))
    looks_like_one_spaced_number = bool(
        re.fullmatch(
            r"\s*[-+]?\d{1,3}(?:\s\d{3})+(?:[,.]\d+)?"
            r"\s*(?:segundos|segundo|seg|secs|sec|minutos|minuto|min|horas|hora|hrs|hr|h|s)?\s*",
            cell,
            flags=re.IGNORECASE,
        )
    )
    if len(matches) >= 2 and has_inner_spaces and not looks_like_one_spaced_number:
        values = []
        for match in matches:
            parsed = try_parse_number(match)
            if parsed is not None:
                values.append(parsed)
        return values

    parsed = try_parse_number(cell)
    if parsed is not None:
        return [parsed]
    interval = RANGE_TOKEN_RE.match(cell)
    if interval:
        start = try_parse_number(interval.group(1))
        end = try_parse_number(interval.group(2))
        if start is not None and end is not None:
            return [(start + end) / 2]
    try:
        normalized = normalize_number_text(cell)
        parsed = try_parse_number(normalized)
        if parsed is not None:
            return [parsed]
    except ValueError:
        pass
    values: list[float] = []
    for match in matches:
        parsed = try_parse_number(match)
        if parsed is not None:
            values.append(parsed)
    return values


def is_probable_index(values: list[float]) -> bool:
    if len(values) < 5:
        return False
    rounded = [int(value) for value in values if float(value).is_integer()]
    if len(rounded) != len(values):
        return False
    return rounded == list(range(rounded[0], rounded[0] + len(rounded)))


def read_flexible_text(text: str, source: str, column: str | None = None) -> DataSeries:
    rows = [split_messy_row(line) for line in text.splitlines()]
    rows = [row for row in rows if row]
    if not rows:
        raise ValueError("Entrada sem valores numericos.")

    selected_column = column.strip() if column else None
    if selected_column:
        wanted = normalize_label(selected_column)
        for header_index, row in enumerate(rows):
            labels = [normalize_label(cell) for cell in row]
            matches = [idx for idx, label in enumerate(labels) if wanted and (wanted in label or label in wanted)]
            for idx in matches:
                values = []
                for line_number, data_row in enumerate(rows[header_index + 1 :], start=header_index + 2):
                    if idx >= len(data_row):
                        continue
                    values.extend(extract_numeric_tokens(data_row[idx]))
                if values:
                    return DataSeries(source=source, column=selected_column, values=values)

    if len(rows) == 1:
        numeric = []
        for cell in rows[0]:
            numeric.extend(extract_numeric_tokens(cell))
        if numeric:
            return DataSeries(source=source, column=selected_column or "valor_colado", values=numeric)

    single_values: list[float] = []
    single_mode = True
    for row in rows:
        numeric = []
        for cell in row:
            numeric.extend(extract_numeric_tokens(cell))
        if len(numeric) != 1:
            single_mode = False
            break
        single_values.append(numeric[0])
    if single_mode and single_values:
        return DataSeries(source=source, column=selected_column or "valor_colado", values=single_values)

    columns: dict[int, list[float]] = {}
    for row in rows:
        for idx, cell in enumerate(row):
            parsed_values = extract_numeric_tokens(cell)
            if parsed_values:
                columns.setdefault(idx, []).extend(parsed_values)

    if not columns:
        raise ValueError("Não encontrei valores numéricos na entrada.")

    scored = []
    for idx, values in columns.items():
        if len(values) < 2:
            continue
        penalty = 1000 if is_probable_index(values) else 0
        spread = max(values) - min(values)
        score = len(values) * 100 - penalty + min(spread, 100)
        scored.append((score, idx, values))

    if not scored:
        raise ValueError("Não encontrei coluna numérica com pelo menos duas observações.")

    scored.sort(reverse=True)
    _score, idx, values = scored[0]
    return DataSeries(source=source, column=selected_column or f"coluna_detectada_{idx + 1}", values=values)


def _sniff_dialect(text: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except csv.Error:
        return csv.excel


def _parse_single_column_lines(text: str, source: str) -> DataSeries:
    values: list[float] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if any(delimiter in stripped for delimiter in [";", "\t"]):
            raise ValueError(
                "Arquivo possui separadores. Informe uma coluna com --column."
            )
        values.append(parse_number(stripped, line_number=index, column="valor"))

    return DataSeries(source=source, column="valor", values=values)


def read_dataset(input_file: Path, column: str | None = None, *, auto_clean: bool = False) -> DataSeries:
    text = input_file.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError("Arquivo de dados vazio.")

    if column is None:
        try:
            return _parse_single_column_lines(text, str(input_file))
        except ValueError as exc:
            if auto_clean:
                return read_flexible_text(text, str(input_file), column)

    try:
        dialect = _sniff_dialect(text)
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("CSV sem cabecalho. Use uma coluna nomeada ou um valor por linha.")

        fieldnames = [field.strip() for field in reader.fieldnames]
        reader.fieldnames = fieldnames
        selected_column = column.strip() if column else None
        if selected_column is None:
            if len(fieldnames) != 1:
                raise ValueError(
                    "CSV com múltiplas colunas exige --column com o nome da coluna numérica."
                )
            selected_column = fieldnames[0]

        if selected_column not in fieldnames:
            raise ValueError(
                f"Coluna '{selected_column}' não encontrada. Colunas disponíveis: {', '.join(fieldnames)}."
            )

        values = []
        for line_number, row in enumerate(reader, start=2):
            values.append(
                parse_number(
                    row.get(selected_column, ""),
                    line_number=line_number,
                    column=selected_column,
                )
            )

        return DataSeries(source=str(input_file), column=selected_column, values=values)
    except ValueError as exc:
        if auto_clean:
            return read_flexible_text(text, str(input_file), column)
        raise exc


def read_manual_values(values_text: str) -> DataSeries:
    return read_flexible_text(values_text, "manual", "valor_colado")


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def population_std(values: list[float], center: float) -> float:
    return math.sqrt(sum((value - center) ** 2 for value in values) / len(values))


def normal_cdf(x: float, mu: float, sigma: float) -> float:
    return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))


def lognormal_cdf(x: float, mu_log: float, sigma_log: float) -> float:
    if x <= 0:
        return 0.0
    return normal_cdf(math.log(x), mu_log, sigma_log)


def exponential_cdf(x: float, rate: float) -> float:
    if x < 0:
        return 0.0
    return 1.0 - math.exp(-rate * x)


def uniform_cdf(x: float, minimum: float, maximum: float) -> float:
    if x <= minimum:
        return 0.0
    if x >= maximum:
        return 1.0
    return (x - minimum) / (maximum - minimum)


def triangular_cdf(x: float, minimum: float, mode: float, maximum: float) -> float:
    if x <= minimum:
        return 0.0
    if x >= maximum:
        return 1.0
    if x <= mode:
        return ((x - minimum) ** 2) / ((maximum - minimum) * (mode - minimum))
    return 1.0 - ((maximum - x) ** 2) / ((maximum - minimum) * (maximum - mode))


def poisson_cdf(x: float, sample_mean: float) -> float:
    if x < 0 or sample_mean <= EPSILON:
        return 0.0
    k = int(math.floor(x))
    if k > 10000:
        return 1.0
    probability = math.exp(-sample_mean)
    total = probability
    for value in range(1, k + 1):
        probability *= sample_mean / value
        total += probability
    return max(0.0, min(1.0, total))


def discrete_uniform_cdf(x: float, minimum: int, maximum: int) -> float:
    if maximum < minimum:
        return 0.0
    if x < minimum:
        return 0.0
    if x >= maximum:
        return 1.0
    return (math.floor(x) - minimum + 1) / (maximum - minimum + 1)


def empirical_discrete_cdf(x: float, values: list[float], probabilities: list[float]) -> float:
    total = 0.0
    for value, probability in zip(values, probabilities):
        if value <= x:
            total += probability
    return max(0.0, min(1.0, total))


def triangular_pdf(x: float, minimum: float, mode: float, maximum: float) -> float:
    if x < minimum or x > maximum:
        return 0.0
    if abs(x - mode) <= EPSILON:
        return 2.0 / (maximum - minimum)
    if x < mode:
        return 2.0 * (x - minimum) / ((maximum - minimum) * (mode - minimum))
    return 2.0 * (maximum - x) / ((maximum - minimum) * (maximum - mode))


def regularized_gamma_p(shape: float, x: float) -> float:
    if shape <= 0.0:
        return math.nan
    if x <= 0.0:
        return 0.0
    if x < shape + 1.0:
        term = 1.0 / shape
        total = term
        ap = shape
        for _ in range(MAX_NUMERICAL_ITERATIONS):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * NUMERICAL_EPSILON:
                break
        return max(0.0, min(1.0, total * math.exp(-x + shape * math.log(x) - math.lgamma(shape))))

    b = x + 1.0 - shape
    c = 1.0 / EPSILON
    d = 1.0 / max(b, EPSILON)
    h = d
    for i in range(1, MAX_NUMERICAL_ITERATIONS + 1):
        an = -i * (i - shape)
        b += 2.0
        d = an * d + b
        if abs(d) < EPSILON:
            d = EPSILON
        c = b + an / c
        if abs(c) < EPSILON:
            c = EPSILON
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < NUMERICAL_EPSILON:
            break
    gamma_q = math.exp(-x + shape * math.log(x) - math.lgamma(shape)) * h
    return max(0.0, min(1.0, 1.0 - gamma_q))


def gamma_cdf(x: float, shape: float, scale: float) -> float:
    if x <= 0.0:
        return 0.0
    if shape <= 0.0 or scale <= 0.0:
        return math.nan
    return regularized_gamma_p(shape, x / scale)


def gamma_pdf(value: float, shape: float, scale: float) -> float:
    if value <= 0.0 or shape <= 0.0 or scale <= 0.0:
        return 0.0
    exponent = (shape - 1.0) * math.log(value) - value / scale - shape * math.log(scale) - math.lgamma(shape)
    return math.exp(max(-745.0, exponent))


def weibull_cdf(x: float, shape: float, scale: float, location: float = 0.0) -> float:
    if x <= location:
        return 0.0
    if shape <= 0.0 or scale <= 0.0:
        return math.nan
    return 1.0 - math.exp(-((x - location) / scale) ** shape)


def weibull_pdf(value: float, shape: float, scale: float, location: float = 0.0) -> float:
    if value <= location or shape <= 0.0 or scale <= 0.0:
        return 0.0
    normalized = (value - location) / scale
    exponent = -normalized**shape
    return (shape / scale) * normalized ** (shape - 1.0) * math.exp(max(-745.0, exponent))


def beta_continued_fraction(alpha: float, beta: float, x: float) -> float:
    qab = alpha + beta
    qap = alpha + 1.0
    qam = alpha - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < EPSILON:
        d = EPSILON
    d = 1.0 / d
    h = d
    for m in range(1, MAX_NUMERICAL_ITERATIONS + 1):
        m2 = 2 * m
        aa = m * (beta - m) * x / ((qam + m2) * (alpha + m2))
        d = 1.0 + aa * d
        if abs(d) < EPSILON:
            d = EPSILON
        c = 1.0 + aa / c
        if abs(c) < EPSILON:
            c = EPSILON
        d = 1.0 / d
        h *= d * c

        aa = -(alpha + m) * (qab + m) * x / ((alpha + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < EPSILON:
            d = EPSILON
        c = 1.0 + aa / c
        if abs(c) < EPSILON:
            c = EPSILON
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < NUMERICAL_EPSILON:
            break
    return h


def regularized_beta(x: float, alpha: float, beta: float) -> float:
    if alpha <= 0.0 or beta <= 0.0:
        return math.nan
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_bt = (
        math.lgamma(alpha + beta)
        - math.lgamma(alpha)
        - math.lgamma(beta)
        + alpha * math.log(x)
        + beta * math.log(1.0 - x)
    )
    bt = math.exp(max(-745.0, log_bt))
    if x < (alpha + 1.0) / (alpha + beta + 2.0):
        return max(0.0, min(1.0, bt * beta_continued_fraction(alpha, beta, x) / alpha))
    return max(
        0.0,
        min(1.0, 1.0 - bt * beta_continued_fraction(beta, alpha, 1.0 - x) / beta),
    )


def beta_cdf(x: float, alpha: float, beta: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return math.nan
    if x <= minimum:
        return 0.0
    if x >= maximum:
        return 1.0
    normalized = (x - minimum) / (maximum - minimum)
    return regularized_beta(normalized, alpha, beta)


def beta_pdf(value: float, alpha: float, beta: float, minimum: float, maximum: float) -> float:
    if value <= minimum or value >= maximum or maximum <= minimum:
        return 0.0
    normalized = (value - minimum) / (maximum - minimum)
    log_pdf = (
        (alpha - 1.0) * math.log(normalized)
        + (beta - 1.0) * math.log(1.0 - normalized)
        + math.lgamma(alpha + beta)
        - math.lgamma(alpha)
        - math.lgamma(beta)
        - math.log(max(maximum - minimum, EPSILON))
    )
    return math.exp(max(-745.0, log_pdf))


def numeric_quantile(cdf: Callable[[float], float], low: float, high: float, probability: float) -> float:
    p = min(max(probability, EPSILON), 1.0 - EPSILON)
    safe_low = low
    safe_high = max(high, low + 1.0)
    for _ in range(80):
        if cdf(safe_high) >= p:
            break
        safe_high *= 2.0
        if safe_high <= safe_low:
            safe_high = safe_low + 1.0
    for _ in range(80):
        midpoint = (safe_low + safe_high) / 2.0
        if cdf(midpoint) < p:
            safe_low = midpoint
        else:
            safe_high = midpoint
    return (safe_low + safe_high) / 2.0


def candidate_cdf(candidate: FitCandidate, x: float) -> float:
    params = candidate.parameters
    if candidate.distribution == "normal":
        return normal_cdf(x, params["mean"], params["standard_deviation"])
    if candidate.distribution == "lognormal":
        return lognormal_cdf(x, params["mean_log"], params["standard_deviation_log"])
    if candidate.distribution == "exponential":
        return exponential_cdf(x, params["rate"])
    if candidate.distribution == "uniform":
        return uniform_cdf(x, params["minimum"], params["maximum"])
    if candidate.distribution == "triangular":
        return triangular_cdf(x, params["minimum"], params["mode"], params["maximum"])
    if candidate.distribution == "gamma":
        return gamma_cdf(x, params["shape"], params["scale"])
    if candidate.distribution == "weibull":
        return weibull_cdf(x, params["shape"], params["scale"])
    if candidate.distribution == "erlang":
        return gamma_cdf(x, params["shape"], params["scale"])
    if candidate.distribution == "beta":
        return beta_cdf(x, params["alpha"], params["beta"], params["minimum"], params["maximum"])
    if candidate.distribution == "poisson":
        return poisson_cdf(x, params["mean"])
    if candidate.distribution == "discrete_uniform":
        return discrete_uniform_cdf(x, int(params["minimum"]), int(params["maximum"]))
    if candidate.distribution == "empirical_discrete":
        values = [float(value) for value in params["values"]]
        probabilities = [float(value) for value in params["probabilities"]]
        return empirical_discrete_cdf(x, values, probabilities)
    raise ValueError(f"Distribuicao sem CDF implementada: {candidate.distribution}")


def candidate_quantile(candidate: FitCandidate, probability: float) -> float:
    p = min(max(probability, EPSILON), 1.0 - EPSILON)
    params = candidate.parameters
    if candidate.distribution == "normal":
        return statistics.NormalDist(
            mu=params["mean"],
            sigma=params["standard_deviation"],
        ).inv_cdf(p)
    if candidate.distribution == "lognormal":
        normal_quantile = statistics.NormalDist(
            mu=params["mean_log"],
            sigma=params["standard_deviation_log"],
        ).inv_cdf(p)
        return math.exp(normal_quantile)
    if candidate.distribution == "exponential":
        return -math.log(1.0 - p) / params["rate"]
    if candidate.distribution == "uniform":
        return params["minimum"] + p * (params["maximum"] - params["minimum"])
    if candidate.distribution == "triangular":
        minimum = params["minimum"]
        mode = params["mode"]
        maximum = params["maximum"]
        split = (mode - minimum) / (maximum - minimum)
        if p < split:
            return minimum + math.sqrt(p * (maximum - minimum) * (mode - minimum))
        return maximum - math.sqrt((1.0 - p) * (maximum - minimum) * (maximum - mode))
    if candidate.distribution == "gamma":
        shape = params["shape"]
        scale = params["scale"]
        return numeric_quantile(lambda x: gamma_cdf(x, shape, scale), 0.0, max(params["mean"] * 3.0, scale), p)
    if candidate.distribution == "weibull":
        return params["scale"] * (-math.log(1.0 - p)) ** (1.0 / params["shape"])
    if candidate.distribution == "erlang":
        shape = params["shape"]
        scale = params["scale"]
        return numeric_quantile(lambda x: gamma_cdf(x, shape, scale), 0.0, max(params["mean"] * 3.0, scale), p)
    if candidate.distribution == "beta":
        return numeric_quantile(
            lambda x: beta_cdf(x, params["alpha"], params["beta"], params["minimum"], params["maximum"]),
            params["minimum"],
            params["maximum"],
            p,
        )
    if candidate.distribution == "poisson":
        sample_mean = params["mean"]
        cumulative = 0.0
        probability = math.exp(-sample_mean)
        value = 0
        while value < 10000:
            cumulative += probability
            if cumulative >= p:
                return float(value)
            value += 1
            probability *= sample_mean / value
        return float(value)
    if candidate.distribution == "discrete_uniform":
        minimum = int(params["minimum"])
        maximum = int(params["maximum"])
        count = maximum - minimum + 1
        index = min(count - 1, max(0, math.ceil(p * count) - 1))
        return float(minimum + index)
    if candidate.distribution == "empirical_discrete":
        values = [float(value) for value in params["values"]]
        probabilities = [float(value) for value in params["probabilities"]]
        cumulative = 0.0
        for value, probability in zip(values, probabilities):
            cumulative += probability
            if cumulative >= p:
                return value
        return values[-1]
    raise ValueError(f"Distribuicao sem quantil implementado: {candidate.distribution}")


def ks_statistic(values: list[float], cdf: Callable[[float], float]) -> float:
    ordered = sorted(values)
    sample_size = len(ordered)
    max_distance = 0.0
    for index, value in enumerate(ordered, start=1):
        theoretical = max(0.0, min(1.0, cdf(value)))
        empirical_left = (index - 1) / sample_size
        empirical_right = index / sample_size
        max_distance = max(
            max_distance,
            abs(theoretical - empirical_left),
            abs(empirical_right - theoretical),
        )
    return max_distance


def _round_parameters(parameters: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 6) for key, value in parameters.items()}


def expression_number(value: float) -> str:
    text = f"{value:.6g}".replace(".", ",")
    return text


def information_criteria(
    log_likelihood: float, parameter_count: int, sample_size: int
) -> tuple[float, float]:
    aic = 2 * parameter_count - 2 * log_likelihood
    bic = parameter_count * math.log(sample_size) - 2 * log_likelihood
    return round(aic, 6), round(bic, 6)


def format_cfg_number(value: float) -> str:
    return f"{value:.6g}"


def fit_normal(values: list[float]) -> FitCandidate | None:
    mu = mean(values)
    sigma = population_std(values, mu)
    if sigma <= EPSILON:
        return None

    log_likelihood = sum(
        -0.5 * math.log(2 * math.pi * sigma**2) - ((value - mu) ** 2) / (2 * sigma**2)
        for value in values
    )
    aic, bic = information_criteria(log_likelihood, 2, len(values))
    parameters = {"mean": mu, "standard_deviation": sigma}
    return FitCandidate(
        distribution="normal",
        ks_statistic=round(ks_statistic(values, lambda x: normal_cdf(x, mu, sigma)), 6),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=f"NormalDistribution(mean={mu:.6g}, standardDeviation={sigma:.6g})",
        display_expression=f"Normal(μ={expression_number(mu)}, σ={expression_number(sigma)})",
        notes=["Adequada quando a variavel pode variar em torno de uma media com simetria aproximada."],
    )


def fit_lognormal(values: list[float]) -> FitCandidate | None:
    if any(value <= 0 for value in values):
        return None

    log_values = [math.log(value) for value in values]
    mu_log = mean(log_values)
    sigma_log = population_std(log_values, mu_log)
    if sigma_log <= EPSILON:
        return None

    log_likelihood = sum(
        -math.log(value * sigma_log * math.sqrt(2 * math.pi))
        - ((math.log(value) - mu_log) ** 2) / (2 * sigma_log**2)
        for value in values
    )
    aic, bic = information_criteria(log_likelihood, 2, len(values))
    parameters = {"mean_log": mu_log, "standard_deviation_log": sigma_log}
    return FitCandidate(
        distribution="lognormal",
        ks_statistic=round(
            ks_statistic(values, lambda x: lognormal_cdf(x, mu_log, sigma_log)),
            6,
        ),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=f"LogNormalDistribution(meanLog={mu_log:.6g}, standardDeviationLog={sigma_log:.6g})",
        display_expression=f"Lognormal(μlog={expression_number(mu_log)}, σlog={expression_number(sigma_log)})",
        notes=["Indicada para tempos ou tamanhos positivos com assimetria a direita."],
    )


def fit_exponential(values: list[float]) -> FitCandidate | None:
    if any(value < 0 for value in values):
        return None

    sample_mean = mean(values)
    if sample_mean <= EPSILON:
        return None

    rate = 1.0 / sample_mean
    log_likelihood = len(values) * math.log(rate) - rate * sum(values)
    aic, bic = information_criteria(log_likelihood, 1, len(values))
    parameters = {"mean": sample_mean, "rate": rate}
    return FitCandidate(
        distribution="exponential",
        ks_statistic=round(ks_statistic(values, lambda x: exponential_cdf(x, rate)), 6),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=f"ExponentialDistribution(mean={sample_mean:.6g})",
        display_expression=f"Exponencial(média={expression_number(sample_mean)})",
        notes=["Candidata para tempos entre eventos independentes e sem memoria."],
    )


def fit_uniform(values: list[float]) -> FitCandidate | None:
    minimum = min(values)
    maximum = max(values)
    if maximum - minimum <= EPSILON:
        return None

    log_likelihood = -len(values) * math.log(maximum - minimum)
    aic, bic = information_criteria(log_likelihood, 2, len(values))
    parameters = {"minimum": minimum, "maximum": maximum}
    return FitCandidate(
        distribution="uniform",
        ks_statistic=round(ks_statistic(values, lambda x: uniform_cdf(x, minimum, maximum)), 6),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=f"UniformDistribution(min={minimum:.6g}, max={maximum:.6g})",
        display_expression=f"Uniforme(min={expression_number(minimum)}, max={expression_number(maximum)})",
        notes=["Uso defensavel quando qualquer valor no intervalo e plausivel de forma parecida."],
    )


def fit_triangular(values: list[float]) -> FitCandidate | None:
    minimum = min(values)
    maximum = max(values)
    if maximum - minimum <= EPSILON:
        return None

    mode = statistics.median(values)
    if mode <= minimum + EPSILON or mode >= maximum - EPSILON:
        mode = mean(values)
    if mode <= minimum + EPSILON or mode >= maximum - EPSILON:
        mode = (minimum + maximum) / 2

    log_likelihood = sum(
        math.log(max(triangular_pdf(value, minimum, mode, maximum), EPSILON))
        for value in values
    )
    aic, bic = information_criteria(log_likelihood, 3, len(values))
    parameters = {"minimum": minimum, "mode": mode, "maximum": maximum}
    return FitCandidate(
        distribution="triangular",
        ks_statistic=round(
            ks_statistic(values, lambda x: triangular_cdf(x, minimum, mode, maximum)),
            6,
        ),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=(
            f"TriangularDistribution(min={minimum:.6g}, mode={mode:.6g}, max={maximum:.6g})"
        ),
        display_expression=(
            f"Triangular(min={expression_number(minimum)}, moda={expression_number(mode)}, "
            f"max={expression_number(maximum)})"
        ),
        notes=[
            "Candidata util quando ha minimo, valor mais provavel e maximo defensaveis pelo dominio.",
            "Nesta versao, o modo e estimado de forma heuristica; revisar com o processo real.",
        ],
    )


def fit_gamma(values: list[float]) -> FitCandidate | None:
    if any(value <= 0 for value in values):
        return None

    sample_mean = mean(values)
    variance = population_std(values, sample_mean) ** 2
    if sample_mean <= EPSILON or variance <= EPSILON:
        return None

    shape = sample_mean**2 / variance
    scale = variance / sample_mean
    if shape <= 0.0 or scale <= 0.0:
        return None

    log_likelihood = sum(
        math.log(max(gamma_pdf(value, shape, scale), EPSILON))
        for value in values
    )
    aic, bic = information_criteria(log_likelihood, 2, len(values))
    parameters = {"mean": sample_mean, "shape": shape, "scale": scale}
    return FitCandidate(
        distribution="gamma",
        ks_statistic=round(ks_statistic(values, lambda x: gamma_cdf(x, shape, scale)), 6),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=f"GammaDistribution(mean={sample_mean:.6g}, shape={shape:.6g})",
        display_expression=f"Gamma(shape={expression_number(shape)}, scale={expression_number(scale)})",
        notes=[
            "Candidata para tempos positivos assimetricos, com flexibilidade maior que a exponencial.",
            "JaamSim usa Mean e Shape; o scale e mostrado para leitura estatistica.",
        ],
    )


def estimate_weibull_shape(values: list[float]) -> float | None:
    logs = [math.log(value) for value in values if value > 0]
    if len(logs) != len(values):
        return None
    average_log = mean(logs)

    def score(shape: float) -> float:
        powered = [value**shape for value in values]
        denominator = sum(powered)
        if denominator <= EPSILON:
            return math.nan
        weighted_log = sum(power * math.log(value) for power, value in zip(powered, values)) / denominator
        return 1.0 / shape + average_log - weighted_log

    low = 0.1
    high = 20.0
    low_score = score(low)
    high_score = score(high)
    if math.isfinite(low_score) and math.isfinite(high_score) and low_score * high_score <= 0.0:
        for _ in range(80):
            midpoint = (low + high) / 2.0
            mid_score = score(midpoint)
            if not math.isfinite(mid_score):
                break
            if abs(mid_score) < NUMERICAL_EPSILON:
                return midpoint
            if low_score * mid_score <= 0.0:
                high = midpoint
                high_score = mid_score
            else:
                low = midpoint
                low_score = mid_score
        return (low + high) / 2.0

    sample_mean = mean(values)
    sample_std = population_std(values, sample_mean)
    coefficient = sample_std / sample_mean if sample_mean > EPSILON else 0.0
    if coefficient <= EPSILON:
        return None
    return max(0.1, min(20.0, coefficient ** -1.086))


def fit_weibull(values: list[float]) -> FitCandidate | None:
    if any(value <= 0 for value in values):
        return None

    shape = estimate_weibull_shape(values)
    if shape is None or shape <= 0.0:
        return None

    scale = (sum(value**shape for value in values) / len(values)) ** (1.0 / shape)
    if scale <= EPSILON:
        return None

    log_likelihood = sum(
        math.log(max(weibull_pdf(value, shape, scale), EPSILON))
        for value in values
    )
    aic, bic = information_criteria(log_likelihood, 2, len(values))
    parameters = {
        "mean": scale * math.gamma(1.0 + 1.0 / shape),
        "shape": shape,
        "scale": scale,
        "location": 0.0,
    }
    return FitCandidate(
        distribution="weibull",
        ks_statistic=round(ks_statistic(values, lambda x: weibull_cdf(x, shape, scale)), 6),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=f"WeibullDistribution(shape={shape:.6g}, scale={scale:.6g})",
        display_expression=f"Weibull(shape={expression_number(shape)}, scale={expression_number(scale)})",
        notes=[
            "Candidata para duracoes positivas com risco/taxa de falha variavel ao longo do tempo.",
            "JaamSim usa Shape, Location e Scale.",
        ],
    )


def fit_erlang(values: list[float]) -> FitCandidate | None:
    if any(value <= 0 for value in values):
        return None

    sample_mean = mean(values)
    variance = population_std(values, sample_mean) ** 2
    if sample_mean <= EPSILON or variance <= EPSILON:
        return None

    shape = max(1, int(round(sample_mean**2 / variance)))
    if shape > 50:
        shape = 50
    scale = sample_mean / shape
    log_likelihood = sum(
        math.log(max(gamma_pdf(value, float(shape), scale), EPSILON))
        for value in values
    )
    aic, bic = information_criteria(log_likelihood, 1, len(values))
    parameters = {"mean": sample_mean, "shape": float(shape), "scale": scale}
    return FitCandidate(
        distribution="erlang",
        ks_statistic=round(ks_statistic(values, lambda x: gamma_cdf(x, float(shape), scale)), 6),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=f"ErlangDistribution(mean={sample_mean:.6g}, shape={shape})",
        display_expression=f"Erlang(k={shape}, scale={expression_number(scale)})",
        notes=[
            "Caso especial da Gamma com shape inteiro; util para soma de etapas exponenciais semelhantes.",
            "No JaamSim, Shape inteiro maior que 10 costuma ser melhor representado por Gamma.",
        ],
    )


def fit_beta(values: list[float]) -> FitCandidate | None:
    minimum_observed = min(values)
    maximum_observed = max(values)
    span = maximum_observed - minimum_observed
    if span <= EPSILON:
        return None

    padding = max(span * 0.001, EPSILON)
    minimum = minimum_observed - padding
    maximum = maximum_observed + padding
    scale = maximum - minimum
    normalized = [(value - minimum) / scale for value in values]
    sample_mean = mean(normalized)
    variance = population_std(normalized, sample_mean) ** 2
    bound = sample_mean * (1.0 - sample_mean)
    if variance <= EPSILON or variance >= bound:
        return None

    common = bound / variance - 1.0
    alpha = sample_mean * common
    beta = (1.0 - sample_mean) * common
    if alpha <= 0.0 or beta <= 0.0:
        return None

    log_likelihood = sum(
        math.log(max(beta_pdf(value, alpha, beta, minimum, maximum), EPSILON))
        for value in values
    )
    aic, bic = information_criteria(log_likelihood, 4, len(values))
    parameters = {
        "alpha": alpha,
        "beta": beta,
        "minimum": minimum,
        "maximum": maximum,
        "scale": scale,
        "location": minimum,
    }
    return FitCandidate(
        distribution="beta",
        ks_statistic=round(
            ks_statistic(values, lambda x: beta_cdf(x, alpha, beta, minimum, maximum)),
            6,
        ),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=f"BetaDistribution(alpha={alpha:.6g}, beta={beta:.6g}, location={minimum:.6g}, scale={scale:.6g})",
        display_expression=(
            f"Beta(alpha={expression_number(alpha)}, beta={expression_number(beta)}, "
            f"min={expression_number(minimum)}, max={expression_number(maximum)})"
        ),
        notes=[
            "Candidata para dados continuos naturalmente limitados entre minimo e maximo.",
            "Os limites foram levemente expandidos para evitar probabilidade zero nos extremos observados.",
        ],
    )


def is_integer_series(values: list[float]) -> bool:
    return all(float(value).is_integer() for value in values)


def fit_poisson(values: list[float]) -> FitCandidate | None:
    if not is_integer_series(values) or any(value < 0 for value in values):
        return None

    sample_mean = mean(values)
    if sample_mean <= EPSILON:
        return None

    log_likelihood = sum(
        value * math.log(sample_mean) - sample_mean - math.lgamma(value + 1.0)
        for value in values
    )
    aic, bic = information_criteria(log_likelihood, 1, len(values))
    parameters = {"mean": sample_mean}
    return FitCandidate(
        distribution="poisson",
        ks_statistic=round(ks_statistic(values, lambda x: poisson_cdf(x, sample_mean)), 6),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=f"PoissonDistribution(mean={sample_mean:.6g})",
        display_expression=f"Poisson(λ={expression_number(sample_mean)})",
        notes=[
            "Candidata para contagens de eventos independentes em uma janela fixa.",
            "Não use para tempo entre chegadas; para isso, avalie exponencial ou agenda de chegadas.",
        ],
    )


def fit_discrete_uniform(values: list[float]) -> FitCandidate | None:
    if not is_integer_series(values):
        return None
    minimum = int(min(values))
    maximum = int(max(values))
    if maximum <= minimum:
        return None

    probability = 1.0 / (maximum - minimum + 1)
    log_likelihood = len(values) * math.log(probability)
    aic, bic = information_criteria(log_likelihood, 2, len(values))
    parameters = {"minimum": float(minimum), "maximum": float(maximum)}
    return FitCandidate(
        distribution="discrete_uniform",
        ks_statistic=round(ks_statistic(values, lambda x: discrete_uniform_cdf(x, minimum, maximum)), 6),
        aic=aic,
        bic=bic,
        parameters=_round_parameters(parameters),
        jaamsim_hint=f"DiscreteUniformDistribution(min={minimum}, max={maximum})",
        display_expression=f"Uniforme discreta(min={minimum}, max={maximum})",
        notes=["Candidata quando cada valor inteiro no intervalo parece igualmente plausivel."],
    )


def fit_empirical_discrete(values: list[float]) -> FitCandidate | None:
    if not is_integer_series(values):
        return None
    counts = Counter(int(value) for value in values)
    if len(counts) < 2:
        return None

    ordered_values = sorted(counts)
    sample_size = len(values)
    probabilities = [counts[value] / sample_size for value in ordered_values]
    log_likelihood = sum(count * math.log(max(count / sample_size, EPSILON)) for count in counts.values())
    parameter_count = max(1, len(ordered_values) - 1)
    aic, bic = information_criteria(log_likelihood, parameter_count, sample_size)
    parameters: dict[str, float | list[float]] = {
        "values": [float(value) for value in ordered_values],
        "probabilities": [round(probability, 6) for probability in probabilities],
    }
    return FitCandidate(
        distribution="empirical_discrete",
        ks_statistic=round(
            ks_statistic(
                values,
                lambda x: empirical_discrete_cdf(
                    x,
                    [float(value) for value in ordered_values],
                    probabilities,
                ),
            ),
            6,
        ),
        aic=aic,
        bic=bic,
        parameters=parameters,
        jaamsim_hint="DiscreteDistribution(valueList=observed_values, probabilityList=observed_frequencies)",
        display_expression=f"Empírica discreta({len(ordered_values)} valores)",
        notes=[
            "Representa diretamente as frequencias observadas.",
            "Pode sobreajustar amostras pequenas; use apenas quando fizer sentido operacional.",
        ],
    )


def fit_distributions(
    values: list[float],
    *,
    fit_kind: str = "continuous",
    support_mode: str = "auto",
) -> list[FitCandidate]:
    if len(values) < 2:
        raise ValueError("Informe pelo menos 2 valores numericos.")

    continuous_candidates = [
        candidate
        for candidate in [
            fit_normal(values),
            fit_lognormal(values),
            fit_exponential(values),
            fit_uniform(values),
            fit_triangular(values),
            fit_gamma(values),
            fit_weibull(values),
            fit_erlang(values),
            fit_beta(values),
        ]
        if candidate is not None
    ]
    discrete_candidates = [
        candidate
        for candidate in [
            fit_poisson(values),
            fit_discrete_uniform(values),
            fit_empirical_discrete(values),
        ]
        if candidate is not None
    ]
    candidates = discrete_candidates if fit_kind == "discrete" and discrete_candidates else continuous_candidates
    if not candidates:
        raise ValueError("Não foi possível ajustar distribuições com os dados informados.")
    filtered = filter_candidates_by_options(candidates, fit_kind=fit_kind, support_mode=support_mode)
    ranked = sorted(filtered, key=lambda item: (item.ks_statistic, item.aic, item.bic))
    annotate_candidate_decisions(ranked, sample_size=len(values))
    return ranked


def annotate_candidate_decisions(candidates: list[FitCandidate], *, sample_size: int) -> None:
    if not candidates:
        return
    ks_critical = 1.36 / math.sqrt(sample_size) if sample_size >= 2 else None
    best_aic = min(candidate.aic for candidate in candidates)
    for candidate in candidates:
        candidate.ks_critical = round(ks_critical, 6) if ks_critical is not None else None
        if ks_critical is None:
            candidate.fit_decision = "inconclusiva"
            candidate.score = None
            continue
        if candidate.distribution == "empirical_discrete":
            candidate.fit_decision = "inconclusiva"
        elif candidate.ks_statistic <= ks_critical:
            candidate.fit_decision = "nao_rejeitada"
        else:
            candidate.fit_decision = "rejeitada"
        ks_component = max(0.0, 1.0 - (candidate.ks_statistic / ks_critical))
        aic_component = 1.0 / (1.0 + max(0.0, candidate.aic - best_aic))
        candidate.score = round(100.0 * (0.75 * ks_component + 0.25 * aic_component), 3)


def filter_candidates_by_options(
    candidates: list[FitCandidate],
    *,
    fit_kind: str,
    support_mode: str,
) -> list[FitCandidate]:
    filtered = candidates
    discrete_names = {"poisson", "discrete_uniform", "empirical_discrete"}
    if support_mode == "positive":
        allowed = (
            {"poisson", "empirical_discrete"}
            if fit_kind == "discrete"
            else {"lognormal", "exponential", "gamma", "weibull", "erlang"}
        )
        filtered = [candidate for candidate in filtered if candidate.distribution in allowed]
    elif support_mode == "bounded":
        allowed = (
            {"discrete_uniform", "empirical_discrete"}
            if fit_kind == "discrete"
            else {"uniform", "triangular", "beta"}
        )
        filtered = [candidate for candidate in filtered if candidate.distribution in allowed]
    elif support_mode == "unbounded":
        allowed = {"poisson", "empirical_discrete"} if fit_kind == "discrete" else {"normal"}
        filtered = [candidate for candidate in filtered if candidate.distribution in allowed]

    if fit_kind == "discrete":
        filtered = [candidate for candidate in filtered if candidate.distribution in discrete_names] or filtered or candidates

    return filtered or candidates


def build_warnings(
    values: list[float],
    candidates: list[FitCandidate],
    *,
    fit_kind: str = "continuous",
    support_mode: str = "auto",
) -> list[str]:
    warnings = [
        "Validar a distribuição escolhida com conhecimento do processo real antes de usar no JaamSim."
    ]
    if fit_kind == "discrete":
        warnings.append(
            "Modo discreto solicitado. Poisson, uniforme discreta e empirica discreta foram avaliadas quando os dados eram inteiros."
        )
        if not is_integer_series(values):
            warnings.append("Dados discretos solicitados, mas há valores não inteiros; o ajuste discreto foi limitado.")
    if support_mode == "positive" and any(value <= 0 for value in values):
        warnings.append("Suporte positivo solicitado, mas ha valores <= 0. Revise os dados ou altere o suporte.")
    if support_mode == "bounded":
        warnings.append("Suporte limitado solicitado; uniform, triangular e beta foram priorizadas por compatibilidade conceitual.")
    if support_mode == "unbounded":
        warnings.append("Suporte não limitado solicitado; normal foi priorizada por compatibilidade conceitual.")
    if len(values) < MIN_RECOMMENDED_SAMPLE:
        warnings.append(
            f"Amostra pequena (n={len(values)}). Use o resultado como triagem, não como prova final."
        )
    if any(value < 0 for value in values):
        warnings.append("Dados negativos bloquearam distribuições que exigem valores não negativos.")
    if any(value <= 0 for value in values):
        warnings.append("Dados zero/negativos bloquearam ajuste lognormal.")
    if len(set(values)) < 3:
        warnings.append("Poucos valores distintos reduzem a confiabilidade do ajuste.")
    outlier_count = count_iqr_outliers(values)
    if outlier_count:
        warnings.append(
            f"Possíveis outliers pelo critério IQR: {outlier_count} valor(es). Revisar medição antes de decidir a distribuição."
        )
    if candidates and candidates[0].ks_statistic > 0.2:
        warnings.append(
            "Melhor KS acima de 0.2 indica aderencia fraca ou amostra pouco representativa."
        )
    return warnings


def count_iqr_outliers(values: list[float]) -> int:
    if len(values) < 4:
        return 0
    q1 = empirical_quantile(values, 0.25)
    q3 = empirical_quantile(values, 0.75)
    iqr = q3 - q1
    if iqr <= EPSILON:
        return 0
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return sum(1 for value in values if value < lower or value > upper)


def classify_fit_quality(values: list[float], candidates: list[FitCandidate]) -> str:
    if len(values) < 5 or len(set(values)) < 3:
        return "fraca"
    best_ks = candidates[0].ks_statistic if candidates else 1.0
    if len(values) < MIN_RECOMMENDED_SAMPLE:
        return "triagem_com_cautela"
    if count_iqr_outliers(values) > 0:
        return "triagem_com_cautela"
    if best_ks > 0.2:
        return "triagem_com_cautela"
    return "triagem_consistente"


def empirical_quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Não há valores para calcular quantil.")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def coefficient_of_variation(values: list[float], sample_mean: float, std: float) -> float | None:
    if abs(sample_mean) <= EPSILON:
        return None
    return std / abs(sample_mean)


def build_histogram(values: list[float], *, max_bins: int = 10) -> list[dict[str, float | int]]:
    minimum = min(values)
    maximum = max(values)
    if maximum - minimum <= EPSILON:
        return [{"lower": round(minimum, 6), "upper": round(maximum, 6), "count": len(values)}]

    bin_count = max(3, min(max_bins, math.ceil(math.sqrt(len(values)))))
    width = (maximum - minimum) / bin_count
    counts = [0 for _ in range(bin_count)]
    for value in values:
        index = int((value - minimum) / width)
        if index >= bin_count:
            index = bin_count - 1
        counts[index] += 1

    histogram = []
    for index, count in enumerate(counts):
        lower = minimum + index * width
        upper = maximum if index == bin_count - 1 else lower + width
        histogram.append({"lower": round(lower, 6), "upper": round(upper, 6), "count": count})
    return histogram


def build_empirical_cdf(values: list[float]) -> list[dict[str, float]]:
    ordered = sorted(values)
    total = len(ordered)
    return [
        {"x": round(value, 6), "probability": round(index / total, 6)}
        for index, value in enumerate(ordered, start=1)
    ]


def build_qq_points(values: list[float], candidate: FitCandidate) -> list[dict[str, float]]:
    ordered = sorted(values)
    sample_size = len(ordered)
    return [
        {
            "theoretical": round(candidate_quantile(candidate, (index - 0.5) / sample_size), 6),
            "observed": round(value, 6),
        }
        for index, value in enumerate(ordered, start=1)
    ]


def build_pp_points(values: list[float], candidate: FitCandidate) -> list[dict[str, float]]:
    ordered = sorted(values)
    sample_size = len(ordered)
    return [
        {
            "theoretical": round(max(0.0, min(1.0, candidate_cdf(candidate, value))), 6),
            "empirical": round((index - 0.5) / sample_size, 6),
        }
        for index, value in enumerate(ordered, start=1)
    ]


def build_candidate_diagnostics(
    values: list[float],
    candidates: list[FitCandidate],
) -> dict[str, dict[str, list[dict[str, float]]]]:
    diagnostics: dict[str, dict[str, list[dict[str, float]]]] = {}
    for candidate in candidates:
        diagnostics[candidate.distribution] = {
            "qq_points": build_qq_points(values, candidate),
            "pp_points": build_pp_points(values, candidate),
        }
    return diagnostics


def infer_variable_context(column: str) -> str:
    name = column.lower()
    if any(word in name for word in ["chegada", "arrival", "interarrival", "entre_chegadas"]):
        return "chegada"
    if any(word in name for word in ["atendimento", "servico", "serviço", "process", "triagem", "consulta"]):
        return "atendimento"
    if any(word in name for word in ["contagem", "quantidade", "count", "numero", "número", "demanda"]):
        return "contagem"
    if any(word in name for word in ["retrabalho", "rework", "defeito", "falha"]):
        return "retrabalho"
    if any(word in name for word in ["prioridade", "priority", "classe"]):
        return "prioridade"
    return "generico"


def build_pedagogical_guidance(series: DataSeries, candidates: list[FitCandidate]) -> list[str]:
    context = infer_variable_context(series.column)
    best = candidates[0].distribution if candidates else "inconclusiva"
    guidance = [
        "Use o melhor KS/AIC/BIC como hipotese inicial; ele nao substitui plausibilidade do processo nem validacao por cenarios.",
        f"Contexto inferido da coluna: {context}. Melhor candidata local: {best}.",
    ]
    if context == "chegada":
        guidance.append("Para chegadas aleatorias, processo de Poisson e tempos entre chegadas exponenciais costumam ser hipoteses iniciais defensaveis.")
        guidance.append("Para agenda ou horario planejado, prefira distribuicao deterministica/agenda em vez de forcar ajuste continuo.")
    elif context == "atendimento":
        guidance.append("Para atendimento/servico, triangular e uniforme sao uteis quando so ha minimo, maximo e valor provavel; lognormal/gamma ajudam quando ha assimetria positiva.")
        guidance.append("Se o tempo de servico depende de tipo de cliente, separe amostras por classe antes de ajustar.")
    elif context == "contagem":
        guidance.append("Para contagens/demanda, revise modelos discretos ou Poisson; ajuste continuo pode ser apenas aproximacao.")
    elif context == "retrabalho":
        guidance.append("Para retrabalho/falha, muitas vezes o dado correto e uma probabilidade ou Bernoulli, nao uma distribuicao de tempo.")
    elif context == "prioridade":
        guidance.append("Para prioridade/classe, trate como regra de roteamento ou distribuicao discreta de categorias.")
    else:
        guidance.append("Se a variavel nao estiver clara, documente unidade, fonte e papel no modelo antes de copiar a distribuicao para o JaamSim.")

    if len(series.values) < 30:
        guidance.append("Amostra pequena: use apenas como triagem e registre a limitacao no estudo.")
    return guidance


def analyze_series(
    series: DataSeries,
    *,
    fit_kind: str = "continuous",
    support_mode: str = "auto",
) -> FitReport:
    candidates = fit_distributions(series.values, fit_kind=fit_kind, support_mode=support_mode)
    best = candidates[0]
    sample_mean = mean(series.values)
    std = population_std(series.values, sample_mean)
    cv = coefficient_of_variation(series.values, sample_mean, std)
    q1 = empirical_quantile(series.values, 0.25)
    q3 = empirical_quantile(series.values, 0.75)
    return FitReport(
        source=series.source,
        column=series.column,
        fit_kind=fit_kind,
        support_mode=support_mode,
        sample_size=len(series.values),
        data_quality_level=classify_fit_quality(series.values, candidates),
        minimum=round(min(series.values), 6),
        maximum=round(max(series.values), 6),
        mean=round(sample_mean, 6),
        median=round(empirical_quantile(series.values, 0.5), 6),
        q1=round(q1, 6),
        q3=round(q3, 6),
        interquartile_range=round(q3 - q1, 6),
        outlier_count=count_iqr_outliers(series.values),
        standard_deviation=round(std, 6),
        coefficient_of_variation=round(cv, 6) if cv is not None else None,
        best_distribution=best.distribution,
        candidates=candidates,
        histogram=build_histogram(series.values),
        empirical_cdf=build_empirical_cdf(series.values),
        qq_points=build_qq_points(series.values, best),
        pp_points=build_pp_points(series.values, best),
        diagnostics_by_distribution=build_candidate_diagnostics(series.values, candidates),
        chart_files={},
        warnings=build_warnings(series.values, candidates, fit_kind=fit_kind, support_mode=support_mode),
        pedagogical_guidance=build_pedagogical_guidance(series, candidates),
    )


def distribution_cfg_class(candidate: FitCandidate) -> str:
    return {
        "normal": "NormalDistribution",
        "lognormal": "LogNormalDistribution",
        "exponential": "ExponentialDistribution",
        "uniform": "UniformDistribution",
        "triangular": "TriangularDistribution",
        "gamma": "GammaDistribution",
        "weibull": "WeibullDistribution",
        "erlang": "ErlangDistribution",
        "beta": "BetaDistribution",
        "poisson": "PoissonDistribution",
        "discrete_uniform": "DiscreteUniformDistribution",
        "empirical_discrete": "DiscreteDistribution",
    }.get(candidate.distribution, f"{candidate.distribution}Distribution")


def distribution_cfg_inputs(candidate: FitCandidate, unit: str) -> tuple[list[tuple[str, str]], list[str]]:
    params = candidate.parameters
    notes: list[str] = []
    if candidate.distribution == "normal":
        return [
            ("Mean", f"{format_cfg_number(params['mean'])} {unit}"),
            ("StandardDeviation", f"{format_cfg_number(params['standard_deviation'])} {unit}"),
        ], notes
    if candidate.distribution == "exponential":
        return [("Mean", f"{format_cfg_number(params['mean'])} {unit}")], notes
    if candidate.distribution == "uniform":
        notes.append("Confirmar no JaamSim se os nomes MinValue/MaxValue estão aderentes à versão usada.")
        return [
            ("MinValue", f"{format_cfg_number(params['minimum'])} {unit}"),
            ("MaxValue", f"{format_cfg_number(params['maximum'])} {unit}"),
        ], notes
    if candidate.distribution == "lognormal":
        notes.append("Confirmar no JaamSim se os nomes MeanLog/StandardDeviationLog estão aderentes à versão usada.")
        return [
            ("MeanLog", format_cfg_number(params["mean_log"])),
            ("StandardDeviationLog", format_cfg_number(params["standard_deviation_log"])),
        ], notes
    if candidate.distribution == "triangular":
        notes.append("Confirmar no JaamSim se os nomes MinValue/Mode/MaxValue estão aderentes à versão usada.")
        return [
            ("MinValue", f"{format_cfg_number(params['minimum'])} {unit}"),
            ("Mode", f"{format_cfg_number(params['mode'])} {unit}"),
            ("MaxValue", f"{format_cfg_number(params['maximum'])} {unit}"),
        ], notes
    if candidate.distribution == "gamma":
        notes.append("GammaDistribution no JaamSim usa Mean e Shape; scale aparece apenas como leitura estatistica.")
        return [
            ("Mean", f"{format_cfg_number(params['mean'])} {unit}"),
            ("Shape", format_cfg_number(params["shape"])),
        ], notes
    if candidate.distribution == "weibull":
        notes.append("WeibullDistribution no JaamSim usa Location, Scale e Shape.")
        return [
            ("Location", f"{format_cfg_number(params.get('location', 0.0))} {unit}"),
            ("Scale", f"{format_cfg_number(params['scale'])} {unit}"),
            ("Shape", format_cfg_number(params["shape"])),
        ], notes
    if candidate.distribution == "erlang":
        notes.append("ErlangDistribution no JaamSim usa Mean e Shape inteiro.")
        return [
            ("Mean", f"{format_cfg_number(params['mean'])} {unit}"),
            ("Shape", format_cfg_number(params["shape"])),
        ], notes
    if candidate.distribution == "beta":
        notes.append("BetaDistribution no JaamSim usa Location, Scale, AlphaParam e BetaParam.")
        return [
            ("Location", f"{format_cfg_number(params['location'])} {unit}"),
            ("Scale", f"{format_cfg_number(params['scale'])} {unit}"),
            ("AlphaParam", format_cfg_number(params["alpha"])),
            ("BetaParam", format_cfg_number(params["beta"])),
        ], notes
    if candidate.distribution == "poisson":
        notes.append("PoissonDistribution usa UnitType dimensionaless no JaamSim; use para contagens, não para tempos.")
        return [("Mean", format_cfg_number(float(params["mean"])))], notes
    if candidate.distribution == "discrete_uniform":
        notes.append("DiscreteUniformDistribution usa UnitType dimensionaless no JaamSim; use para contagens inteiras.")
        return [
            ("MinValue", format_cfg_number(float(params["minimum"]))),
            ("MaxValue", format_cfg_number(float(params["maximum"]))),
        ], notes
    if candidate.distribution == "empirical_discrete":
        values = " ".join(format_cfg_number(float(value)) for value in params["values"])
        probabilities = " ".join(format_cfg_number(float(value)) for value in params["probabilities"])
        notes.append("DiscreteDistribution usa ValueList/ProbabilityList; revisar se as frequências observadas representam a operação real.")
        return [
            ("ValueList", values),
            ("ProbabilityList", probabilities),
        ], notes
    notes.append("Distribuicao sem mapeamento especifico para snippet JaamSim.")
    return [], notes


def render_jaamsim_cfg_snippet(
    report: FitReport,
    *,
    object_name: str | None = None,
    unit_type: str = "TimeUnit",
    unit: str = "s",
    random_seed: int = 11,
) -> str:
    best = report.candidates[0]
    safe_name = safe_jaamsim_name(object_name or report.column)
    cfg_class = distribution_cfg_class(best)
    inputs, mapping_notes = distribution_cfg_inputs(best, unit)
    is_discrete_distribution = best.distribution in {"poisson", "discrete_uniform", "empirical_discrete"}
    effective_unit_type = "DimensionlessUnit" if is_discrete_distribution else unit_type
    lines = [
        "# Snippet StatFit auxiliar para JaamSim",
        "# Gerado offline por algoritmo; revise antes de usar.",
        "# Não altera topologia nem substitui validação estatística/formal.",
        f"# Fonte: {report.source}",
        f"# Coluna: {report.column}",
        f"# Melhor candidata: {best.distribution} | KS={best.ks_statistic} | AIC={best.aic} | BIC={best.bic}",
        "",
        f"Define {cfg_class} {{ {safe_name} }}",
        "",
        f"{safe_name} UnitType {{ {effective_unit_type} }}",
        f"{safe_name} RandomSeed {{ {random_seed} }}",
    ]
    lines.extend(f"{safe_name} {input_name} {{ {input_value} }}" for input_name, input_value in inputs)
    lines.extend(["", "# Uso sugerido:", f"# - Vincule manualmente `{safe_name}` ao objeto apropriado no JaamSim."])
    if is_discrete_distribution:
        lines.extend(
            [
                "# - Esta candidata representa contagens/quantidades. Não use diretamente em InterArrivalTime sem converter a lógica do processo.",
                "# - Exemplos de uso: quantidade comprada, tamanho de lote, número de itens por cliente ou decisão dimensionless equivalente.",
            ]
        )
    else:
        lines.append("# - Exemplo observado em modelos locais: GeneratorClientes InterArrivalTime { IATDistribution }")
    lines.append("# - Substitua o nome da distribuição no objeto alvo somente depois de validar a unidade e o processo real.")
    if mapping_notes:
        lines.append("")
        lines.append("# Observacoes de mapeamento:")
        lines.extend(f"# - {note}" for note in mapping_notes)
    if report.warnings:
        lines.append("")
        lines.append("# Avisos metodologicos:")
        lines.extend(f"# - {warning}" for warning in report.warnings)
    return "\n".join(lines).rstrip() + "\n"


def render_histogram_lines(histogram: list[dict[str, float | int]]) -> list[str]:
    max_count = max((int(item["count"]) for item in histogram), default=0)
    if max_count <= 0:
        return ["Sem valores para histograma."]
    lines = []
    for item in histogram:
        count = int(item["count"])
        bar_size = max(1, round((count / max_count) * 24)) if count else 0
        bar = "#" * bar_size
        lines.append(
            f"{format_cfg_number(float(item['lower']))} - {format_cfg_number(float(item['upper']))}: "
            f"{bar} ({count})"
        )
    return lines


def render_markdown(
    report: FitReport,
    *,
    jaamsim_object_name: str | None = None,
    unit_type: str = "TimeUnit",
    unit: str = "s",
    random_seed: int = 11,
) -> str:
    lines = [
        f"# Relatório StatFit Auxiliar - {report.column}",
        "",
        "> Módulo opcional offline para triagem de distribuições. Não substitui StatFit comercial, teste estatístico formal ou validação por especialista.",
        "",
        "## Entrada",
        "",
        f"- Fonte: `{report.source}`",
        f"- Coluna analisada: `{report.column}`",
        f"- Tipo de ajuste: `{report.fit_kind}`",
        f"- Suporte assumido: `{report.support_mode}`",
        f"- Tamanho da amostra: `{report.sample_size}`",
        f"- Classificação local da qualidade: `{report.data_quality_level}`",
        f"- Mínimo: `{report.minimum}`",
        f"- Máximo: `{report.maximum}`",
        f"- Media: `{report.mean}`",
        f"- Mediana: `{report.median}`",
        f"- Q1/Q3: `{report.q1}` / `{report.q3}`",
        f"- Intervalo interquartil (IQR): `{report.interquartile_range}`",
        f"- Possíveis outliers por IQR: `{report.outlier_count}`",
        f"- Desvio padrao populacional: `{report.standard_deviation}`",
        f"- Coeficiente de variação: `{report.coefficient_of_variation if report.coefficient_of_variation is not None else 'n/a'}`",
        "",
        "## Histograma textual",
        "",
        "```text",
        *render_histogram_lines(report.histogram),
        "```",
        "",
        "## Ranking de distribuições",
        "",
        "| Posição | Distribuição | KS | KS crítico | Decisão | Aceitação (%) | Expressão | AIC | BIC | Parâmetros | Pista JaamSim |",
        "|---|---|---:|---:|---|---:|---|---:|---:|---|---|",
    ]

    for position, candidate in enumerate(report.candidates, start=1):
        parameters = ", ".join(
            f"{key}={value}" for key, value in candidate.parameters.items()
        )
        lines.append(
            f"| {position} | {candidate.distribution} | {candidate.ks_statistic} | {candidate.ks_critical if candidate.ks_critical is not None else 'n/a'} | {candidate.fit_decision} | {candidate.score if candidate.score is not None else 'n/a'} | {candidate.display_expression} | {candidate.aic} | {candidate.bic} | {parameters} | `{candidate.jaamsim_hint}` |"
        )

    best = report.candidates[0]
    if report.chart_files:
        lines.extend(
            [
                "",
                "## Gráficos gerados",
                "",
            ]
        )
        for label, path in report.chart_files.items():
            lines.append(f"- {label}: `{path}`")
        lines.extend(
            [
                "",
                "> Q-Q e P-P são diagnósticos visuais da melhor candidata. Pontos próximos da diagonal sugerem melhor aderência; desvios sistemáticos pedem revisão da distribuição ou dos dados.",
            ]
        )

    lines.extend(
        [
            "",
            "## Melhor candidata",
            "",
            f"- Distribuição: `{best.distribution}`",
            f"- Critério principal: menor estatística KS (`{best.ks_statistic}`).",
            "- Decisão humana: obrigatória antes de levar a distribuição para o modelo.",
            "",
            "## Orientacao pedagogica offline",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report.pedagogical_guidance)
    lines.extend(
        [
            "",
            "## Avisos e limites",
            "",
        ]
    )
    lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend(
        [
            "",
            "## Formato aceito",
            "",
            "CSV com cabeçalho e coluna numérica nomeada:",
            "",
            "```csv",
            EXAMPLE_DATA.strip(),
            "```",
            "",
            "Comando exemplo:",
            "",
            "```bash",
            "python extensions/academic-assistant/python/statfit_auxiliar.py dados.csv --column tempo_atendimento",
            "```",
            "",
            "Para entrada colada ou CSV/TXT irregular, use `--auto-clean` e revise a coluna detectada.",
            "",
            "## Snippet JaamSim sugerido",
            "",
            "Este bloco é uma recomendação para revisão manual. Ele não altera o modelo automaticamente.",
            "",
            "```cfg",
            render_jaamsim_cfg_snippet(
                report,
                object_name=jaamsim_object_name,
                unit_type=unit_type,
                unit=unit,
                random_seed=random_seed,
            ).strip(),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def safe_stem(source: str, column: str) -> str:
    base = "manual" if source == "manual" else Path(source).stem
    raw = f"{base}_{column}".lower()
    return re.sub(r"[^a-z0-9_-]+", "_", raw).strip("_") or "dataset"


def _scale_svg(value: float, source_min: float, source_max: float, target_min: float, target_max: float) -> float:
    if abs(source_max - source_min) <= EPSILON:
        return (target_min + target_max) / 2
    ratio = (value - source_min) / (source_max - source_min)
    return target_min + ratio * (target_max - target_min)


def render_histogram_svg(report: FitReport) -> str:
    width = 720
    height = 420
    left = 72
    right = 32
    top = 56
    bottom = 72
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_count = max((int(item["count"]) for item in report.histogram), default=1)
    bar_gap = 8
    bar_width = max(8, (plot_width - bar_gap * (len(report.histogram) - 1)) / max(1, len(report.histogram)))

    elements = [
        f'<text x="{left}" y="28" class="title">Histograma - {escape(report.column)}</text>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" class="axis"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" class="axis"/>',
        f'<text x="{left}" y="{height - 24}" class="label">Valores observados</text>',
        f'<text x="18" y="{top + 12}" class="label">freq.</text>',
    ]

    for index, item in enumerate(report.histogram):
        count = int(item["count"])
        x = left + index * (bar_width + bar_gap)
        bar_height = 0 if max_count <= 0 else (count / max_count) * plot_height
        y = top + plot_height - bar_height
        label = f"{format_cfg_number(float(item['lower']))}-{format_cfg_number(float(item['upper']))}"
        elements.extend(
            [
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" rx="2" class="bar"/>',
                f'<text x="{x + bar_width / 2:.2f}" y="{y - 6:.2f}" class="count">{count}</text>',
                f'<text x="{x + bar_width / 2:.2f}" y="{top + plot_height + 18}" class="tick" transform="rotate(30 {x + bar_width / 2:.2f},{top + plot_height + 18})">{escape(label)}</text>',
            ]
        )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<style>",
            "text{font-family:Arial,Helvetica,sans-serif;fill:#1f2933}.title{font-size:20px;font-weight:700}.label{font-size:12px}.tick{font-size:10px;text-anchor:start}.count{font-size:11px;text-anchor:middle}.axis{stroke:#5b6770;stroke-width:1.2}.bar{fill:#4f83cc;stroke:#315f99;stroke-width:1}",
            "</style>",
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
            *elements,
            "</svg>",
        ]
    )


def render_ecdf_svg(report: FitReport) -> str:
    width = 720
    height = 420
    left = 72
    right = 32
    top = 56
    bottom = 72
    plot_width = width - left - right
    plot_height = height - top - bottom
    x_min = report.minimum
    x_max = report.maximum

    points = []
    for item in report.empirical_cdf:
        x = _scale_svg(float(item["x"]), x_min, x_max, left, left + plot_width)
        y = _scale_svg(float(item["probability"]), 0.0, 1.0, top + plot_height, top)
        points.append((x, y))

    point_text = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    elements = [
        f'<text x="{left}" y="28" class="title">CDF empirica - {escape(report.column)}</text>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" class="axis"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" class="axis"/>',
        f'<text x="{left}" y="{height - 24}" class="label">Valores observados</text>',
        f'<text x="18" y="{top + 12}" class="label">prob.</text>',
        f'<text x="{left - 10}" y="{top + plot_height + 4}" class="tick" text-anchor="end">0.0</text>',
        f'<text x="{left - 10}" y="{top + 4}" class="tick" text-anchor="end">1.0</text>',
        f'<text x="{left}" y="{top + plot_height + 20}" class="tick">{format_cfg_number(x_min)}</text>',
        f'<text x="{left + plot_width}" y="{top + plot_height + 20}" class="tick" text-anchor="end">{format_cfg_number(x_max)}</text>',
    ]
    if point_text:
        elements.append(f'<polyline points="{point_text}" class="line"/>')
    for x, y in points:
        elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.4" class="dot"/>')

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<style>",
            "text{font-family:Arial,Helvetica,sans-serif;fill:#1f2933}.title{font-size:20px;font-weight:700}.label{font-size:12px}.tick{font-size:10px}.axis{stroke:#5b6770;stroke-width:1.2}.line{fill:none;stroke:#138a72;stroke-width:2}.dot{fill:#138a72}",
            "</style>",
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
            *elements,
            "</svg>",
        ]
    )


def render_diagnostic_scatter_svg(
    report: FitReport,
    points: list[dict[str, float]],
    *,
    title: str,
    x_key: str,
    y_key: str,
    x_label: str,
    y_label: str,
) -> str:
    width = 720
    height = 420
    left = 72
    right = 32
    top = 56
    bottom = 72
    plot_width = width - left - right
    plot_height = height - top - bottom
    xs = [float(item[x_key]) for item in points]
    ys = [float(item[y_key]) for item in points]
    axis_min = min(xs + ys, default=0.0)
    axis_max = max(xs + ys, default=1.0)
    if abs(axis_max - axis_min) <= EPSILON:
        axis_min -= 1.0
        axis_max += 1.0

    elements = [
        f'<text x="{left}" y="28" class="title">{escape(title)} - {escape(report.best_distribution)}</text>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" class="axis"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" class="axis"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top}" class="reference"/>',
        f'<text x="{left}" y="{height - 24}" class="label">{escape(x_label)}</text>',
        f'<text x="18" y="{top + 12}" class="label">{escape(y_label)}</text>',
        f'<text x="{left}" y="{top + plot_height + 20}" class="tick">{format_cfg_number(axis_min)}</text>',
        f'<text x="{left + plot_width}" y="{top + plot_height + 20}" class="tick" text-anchor="end">{format_cfg_number(axis_max)}</text>',
    ]

    for item in points:
        x_value = float(item[x_key])
        y_value = float(item[y_key])
        x = _scale_svg(x_value, axis_min, axis_max, left, left + plot_width)
        y = _scale_svg(y_value, axis_min, axis_max, top + plot_height, top)
        elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" class="dot"/>')

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<style>",
            "text{font-family:Arial,Helvetica,sans-serif;fill:#1f2933}.title{font-size:20px;font-weight:700}.label{font-size:12px}.tick{font-size:10px}.axis{stroke:#5b6770;stroke-width:1.2}.reference{stroke:#c44949;stroke-width:1.5;stroke-dasharray:6 5}.dot{fill:#4f83cc;stroke:#315f99;stroke-width:.8}",
            "</style>",
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
            *elements,
            "</svg>",
        ]
    )


def write_chart_outputs(report: FitReport, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_stem(report.source, report.column)
    histogram_path = output_dir / f"{stem}_histograma.svg"
    ecdf_path = output_dir / f"{stem}_cdf_empirica.svg"
    qq_path = output_dir / f"{stem}_qq_plot.svg"
    pp_path = output_dir / f"{stem}_pp_plot.svg"
    histogram_path.write_text(render_histogram_svg(report), encoding="utf-8")
    ecdf_path.write_text(render_ecdf_svg(report), encoding="utf-8")
    qq_path.write_text(
        render_diagnostic_scatter_svg(
            report,
            report.qq_points,
            title="Gráfico Q-Q",
            x_key="theoretical",
            y_key="observed",
            x_label="Quantis teoricos",
            y_label="Quantis observados",
        ),
        encoding="utf-8",
    )
    pp_path.write_text(
        render_diagnostic_scatter_svg(
            report,
            report.pp_points,
            title="Gráfico P-P",
            x_key="theoretical",
            y_key="empirical",
            x_label="Probabilidade teorica",
            y_label="Probabilidade empirica",
        ),
        encoding="utf-8",
    )
    return {
        "histogram_svg": histogram_path,
        "ecdf_svg": ecdf_path,
        "qq_svg": qq_path,
        "pp_svg": pp_path,
    }


def write_outputs(
    report: FitReport,
    output_dir: Path,
    *,
    jaamsim_object_name: str | None = None,
    unit_type: str = "TimeUnit",
    unit: str = "s",
    random_seed: int = 11,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_stem(report.source, report.column)
    json_path = output_dir / f"{stem}_statfit_report.json"
    md_path = output_dir / f"{stem}_statfit_report.md"
    chart_paths = write_chart_outputs(report, output_dir)
    report.chart_files = {key: str(path) for key, path in chart_paths.items()}
    payload = asdict(report)
    payload["python_runtime"] = runtime_provenance.capture_runtime(Path(__file__))
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown(
            report,
            jaamsim_object_name=jaamsim_object_name,
            unit_type=unit_type,
            unit=unit,
            random_seed=random_seed,
        ),
        encoding="utf-8",
    )
    return json_path, md_path


def write_jaamsim_snippet(
    report: FitReport,
    output_dir: Path,
    *,
    jaamsim_object_name: str | None = None,
    unit_type: str = "TimeUnit",
    unit: str = "s",
    random_seed: int = 11,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_stem(report.source, report.column)
    snippet_path = output_dir / f"{stem}_jaamsim_distribution.cfg"
    snippet_path.write_text(
        render_jaamsim_cfg_snippet(
            report,
            object_name=jaamsim_object_name,
            unit_type=unit_type,
            unit=unit,
            random_seed=random_seed,
        ),
        encoding="utf-8",
    )
    return snippet_path


def render_example() -> str:
    return (
        "Formato recomendado (CSV com cabeçalho e uma coluna numérica):\n\n"
        f"{EXAMPLE_DATA}\n"
        "Comando:\n"
        "python extensions/academic-assistant/python/statfit_auxiliar.py dados.csv --column tempo_atendimento\n\n"
        "Colagem rapida do Excel:\n"
        "python extensions/academic-assistant/python/statfit_auxiliar.py --values \"4.2\\n5.1\\n4.8\"\n\n"
        "CSV/TXT irregular:\n"
        "python extensions/academic-assistant/python/statfit_auxiliar.py dados_sujos.csv --auto-clean\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Módulo auxiliar offline para ajuste inicial de distribuições."
    )
    parser.add_argument("input_file", nargs="?", type=Path, help="CSV/TXT com dados numericos.")
    parser.add_argument("--column", help="Nome da coluna numérica quando a entrada for CSV.")
    parser.add_argument(
        "--values",
        help="Valores colados/manuais. Aceita linhas, tabs, ponto e virgula, virgula e texto copiado do Excel.",
    )
    parser.add_argument(
        "--auto-clean",
        action="store_true",
        help="Tenta organizar dados colados/CSV sujo e detectar uma coluna numérica automaticamente.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretório de saída para JSON/Markdown.",
    )
    parser.add_argument(
        "--jaamsim-object-name",
        help="Nome do objeto de distribuição no snippet JaamSim. Padrão: derivado da coluna.",
    )
    parser.add_argument(
        "--unit-type",
        default="TimeUnit",
        help="UnitType usado no snippet JaamSim. Padrão: TimeUnit.",
    )
    parser.add_argument(
        "--unit",
        default="s",
        help="Unidade numérica usada nos parâmetros do snippet, quando aplicável. Padrão: s.",
    )
    parser.add_argument(
        "--fit-kind",
        choices=["continuous", "discrete"],
        default="continuous",
        help="Tipo conceitual dos dados: continuous ou discrete.",
    )
    parser.add_argument(
        "--support",
        choices=["auto", "positive", "bounded", "unbounded"],
        default="auto",
        help="Suporte conceitual da distribuição: auto, positive, bounded ou unbounded.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=11,
        help="RandomSeed usado no snippet JaamSim. Padrão: 11.",
    )
    parser.add_argument(
        "--no-jaamsim-snippet",
        action="store_true",
        help="Não gera o arquivo .cfg de recomendação JaamSim.",
    )
    parser.add_argument(
        "--print-example",
        action="store_true",
        help="Mostra exemplo estrito de arquivo aceito.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.print_example:
        print(render_example())
        return 0

    if args.values:
        series = read_manual_values(args.values)
    elif args.input_file:
        series = read_dataset(args.input_file, args.column, auto_clean=args.auto_clean)
    else:
        parser.error("Informe um arquivo de dados, --values ou --print-example.")

    report = analyze_series(series, fit_kind=args.fit_kind, support_mode=args.support)
    json_path, md_path = write_outputs(
        report,
        args.output_dir,
        jaamsim_object_name=args.jaamsim_object_name,
        unit_type=args.unit_type,
        unit=args.unit,
        random_seed=args.random_seed,
    )
    snippet_path = None
    if not args.no_jaamsim_snippet:
        snippet_path = write_jaamsim_snippet(
            report,
            args.output_dir,
            jaamsim_object_name=args.jaamsim_object_name,
            unit_type=args.unit_type,
            unit=args.unit,
            random_seed=args.random_seed,
        )

    print(f"Melhor distribuição: {report.best_distribution}")
    print(f"Tipo ajuste: {report.fit_kind}")
    print(f"Suporte: {report.support_mode}")
    print(f"Classificação qualidade: {report.data_quality_level}")
    print(f"IQR: {report.interquartile_range}")
    print(f"Outliers IQR: {report.outlier_count}")
    print(f"Relatório Markdown: {md_path}")
    print(f"Relatório JSON: {json_path}")
    histogram_chart = report.chart_files.get("histogram_svg")
    ecdf_chart = report.chart_files.get("ecdf_svg")
    qq_chart = report.chart_files.get("qq_svg")
    pp_chart = report.chart_files.get("pp_svg")
    if histogram_chart:
        print(f"Gráfico histograma: {histogram_chart}")
    if ecdf_chart:
        print(f"Gráfico CDF empírica: {ecdf_chart}")
    if qq_chart:
        print(f"Gráfico Q-Q: {qq_chart}")
    if pp_chart:
        print(f"Gráfico P-P: {pp_chart}")
    if snippet_path:
        print(f"Snippet JaamSim: {snippet_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
