#!/usr/bin/env python3
"""Estimate API-equivalent cost from Claude Code project transcript JSONL files."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Rate:
    input: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float
    output: float


@dataclass(frozen=True)
class LongContext:
    threshold: int
    input_multiplier: float
    output_multiplier: float


def parse_timestamp(value: str, zone_name: str | None) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        if not zone_name:
            raise argparse.ArgumentTypeError(
                "naive timestamps require --timezone with an IANA name"
            )
        parsed = parsed.replace(tzinfo=ZoneInfo(zone_name))
    return parsed.astimezone(timezone.utc)


def parse_mapping(spec: str, label: str) -> tuple[str, str]:
    try:
        left, right = spec.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must contain '=': {spec!r}") from exc
    if not left or not right:
        raise argparse.ArgumentTypeError(f"invalid {label}: {spec!r}")
    return left, right


def parse_rates(specs: Iterable[str]) -> dict[str, Rate]:
    result: dict[str, Rate] = {}
    for spec in specs:
        model, raw = parse_mapping(spec, "rate")
        try:
            values = [float(part) for part in raw.split(",")]
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid numeric rate: {spec!r}") from exc
        if len(values) != 5 or any(value < 0 for value in values):
            raise argparse.ArgumentTypeError(
                "rate must be MODEL=INPUT,CACHE_WRITE_5M,CACHE_WRITE_1H,CACHE_READ,OUTPUT"
            )
        result[model] = Rate(*values)
    return result


def parse_long_context(specs: Iterable[str]) -> dict[str, LongContext]:
    result: dict[str, LongContext] = {}
    for spec in specs:
        model, raw = parse_mapping(spec, "long-context rule")
        parts = raw.split(",")
        if len(parts) != 3:
            raise argparse.ArgumentTypeError(
                "long-context must be MODEL=THRESHOLD,INPUT_MULTIPLIER,OUTPUT_MULTIPLIER"
            )
        try:
            threshold = int(parts[0])
            input_multiplier = float(parts[1])
            output_multiplier = float(parts[2])
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid long-context rule: {spec!r}") from exc
        if threshold < 0 or input_multiplier <= 0 or output_multiplier <= 0:
            raise argparse.ArgumentTypeError(f"invalid long-context rule: {spec!r}")
        result[model] = LongContext(threshold, input_multiplier, output_multiplier)
    return result


def iter_jsonl(root: Path):
    for path in sorted(root.rglob("*.jsonl")):
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                yield path, handle
        except OSError as exc:
            print(f"warning: cannot read {path}: {exc}", file=sys.stderr)


def is_turn_boundary(message: dict) -> bool:
    """A live human/subagent prompt, not a synthetic tool_result reply."""
    content = message.get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        block_types = {b.get("type") for b in content if isinstance(b, dict)}
        return not block_types or not block_types <= {"tool_result"}
    return True


def message_timestamp(root: Path, exact_message: str) -> datetime:
    matches: list[datetime] = []
    for _, handle in iter_jsonl(root):
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "user":
                continue
            message = record.get("message") or {}
            content = message.get("content")
            text = None
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                if len(texts) == 1:
                    text = texts[0]
            if text == exact_message and record.get("timestamp"):
                matches.append(parse_timestamp(record["timestamp"], None))
    if not matches:
        raise SystemExit(f"no exact user message timestamp found for {exact_message!r}")
    return max(matches)


def project_name(path: Path, root: Path) -> str:
    """The project a transcript belongs to: the first path segment under root."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    return parts[0] if len(parts) > 1 else "(root)"


def read_usage(root: Path, start: datetime, end: datetime):
    events: list[dict] = []
    diagnostics = defaultdict(int)
    seen: set[tuple] = set()
    for path, handle in iter_jsonl(root):
        project = project_name(path, root)
        turn_seq = 0
        for line_number, line in enumerate(handle, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                diagnostics["bad_json_lines"] += 1
                continue
            record_type = record.get("type")
            message = record.get("message") or {}

            if record_type == "user":
                if is_turn_boundary(message):
                    turn_seq += 1
                continue

            if record_type != "assistant":
                continue
            usage = message.get("usage")
            if not usage:
                continue

            # Every content block (text, tool_use, ...) of one API response is
            # written as its own JSONL line and repeats the SAME usage object.
            # Dedup on (message id, requestId); resumed/forked sessions also
            # replay prior lines verbatim into new session files, so dedup is
            # global across all files, not just within one.
            dedupe_key = (message.get("id"), record.get("requestId"))
            if dedupe_key == (None, None):
                dedupe_key = (record.get("uuid"),)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            ts_raw = record.get("timestamp")
            if not ts_raw:
                diagnostics["missing_timestamp"] += 1
                continue
            timestamp = parse_timestamp(ts_raw, None)
            if timestamp < start or timestamp > end:
                continue

            cache_creation = usage.get("cache_creation") or {}
            write_1h = int(cache_creation.get("ephemeral_1h_input_tokens", 0) or 0)
            write_5m = int(cache_creation.get("ephemeral_5m_input_tokens", 0) or 0)
            if cache_creation:
                flat_write = int(usage.get("cache_creation_input_tokens", 0) or 0)
                if flat_write and (write_1h + write_5m) != flat_write:
                    diagnostics["ttl_split_mismatch"] += 1
            else:
                # Older/foreign records may lack the TTL breakdown; Anthropic's
                # default cache TTL is 5 minutes, so attribute the flat total there.
                write_5m = int(usage.get("cache_creation_input_tokens", 0) or 0)
                diagnostics["ttl_unspecified_assumed_5m"] += 1

            events.append(
                {
                    "timestamp": timestamp,
                    "model": message.get("model") or "unknown",
                    "project": project,
                    "turn_id": f"{path}#{turn_seq}",
                    "input_tokens": int(usage.get("input_tokens", 0) or 0),
                    "cache_write_5m": write_5m,
                    "cache_write_1h": write_1h,
                    "cache_read_tokens": int(usage.get("cache_read_input_tokens", 0) or 0),
                    "output_tokens": int(usage.get("output_tokens", 0) or 0),
                }
            )
    return events, dict(diagnostics)


def calculate(events, rates, proxies, long_context):
    rows = defaultdict(
        lambda: {
            "turn_ids": set(),
            "observed_models": set(),
            "input_tokens": 0,
            "cache_write_5m": 0,
            "cache_write_1h": 0,
            "cache_read_tokens": 0,
            "output_tokens": 0,
            "cost": defaultdict(float),
        }
    )
    long_requests = defaultdict(int)
    unpriced = set()
    for event in events:
        observed = event["model"]
        pricing_model = proxies.get(observed, observed)
        row = rows[pricing_model]
        row["turn_ids"].add(event["turn_id"])
        row["observed_models"].add(observed)
        for key in ("input_tokens", "cache_write_5m", "cache_write_1h", "cache_read_tokens", "output_tokens"):
            row[key] += event[key]

        rate = rates.get(pricing_model)
        if rate is None:
            unpriced.add(observed)
            continue

        total_context = (
            event["input_tokens"]
            + event["cache_write_5m"]
            + event["cache_write_1h"]
            + event["cache_read_tokens"]
        )
        rule = long_context.get(pricing_model)
        input_multiplier = 1.0
        output_multiplier = 1.0
        if rule and total_context > rule.threshold:
            input_multiplier = rule.input_multiplier
            output_multiplier = rule.output_multiplier
            long_requests[pricing_model] += 1

        row["cost"]["uncached input"] += event["input_tokens"] * rate.input * input_multiplier / 1_000_000
        row["cost"]["cache write (5m TTL)"] += event["cache_write_5m"] * rate.cache_write_5m * input_multiplier / 1_000_000
        row["cost"]["cache write (1h TTL)"] += event["cache_write_1h"] * rate.cache_write_1h * input_multiplier / 1_000_000
        row["cost"]["cache read"] += event["cache_read_tokens"] * rate.cache_read * input_multiplier / 1_000_000
        row["cost"]["output"] += event["output_tokens"] * rate.output * output_multiplier / 1_000_000

    normalized = {}
    for model, row in rows.items():
        normalized[model] = {
            "turns": len(row.pop("turn_ids")),
            "observed_models": sorted(row.pop("observed_models")),
            "input": row["input_tokens"],
            "cache_write_5m": row["cache_write_5m"],
            "cache_write_1h": row["cache_write_1h"],
            "cache_write": row["cache_write_5m"] + row["cache_write_1h"],
            "cache_read": row["cache_read_tokens"],
            "output": row["output_tokens"],
            "cost_components": dict(row["cost"]),
            "api_cost": sum(row["cost"].values()) if row["cost"] else None,
            "pricing_model": model,
        }
    return normalized, dict(long_requests), sorted(unpriced)


def calculate_by_project(events, rates, proxies, long_context):
    """Same aggregation as calculate(), partitioned by project first.

    Dedup already happened globally in read_usage() before events reach here,
    so a message that (rarely) appears to belong to two projects is already
    resolved to whichever file read_usage() saw first — this function does
    not re-partition duplicates, it only groups what read_usage() already
    decided.
    """
    by_project: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        by_project[event["project"]].append(event)

    result = {}
    for project, project_events in by_project.items():
        normalized, long_requests, unpriced = calculate(project_events, rates, proxies, long_context)
        result[project] = {
            "models": normalized,
            "long_context_requests": long_requests,
            "unpriced_models": unpriced,
        }
    return result


def token_text(value: int) -> str:
    if value == 0:
        return "—"
    if value >= 1_000_000:
        text = f"{value / 1_000_000:,.2f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if value >= 1_000:
        text = f"{value / 1_000:,.1f}".rstrip("0").rstrip(".")
        return f"{text}k"
    return f"{value:,}"


def money_text(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 1000:
        return f"${value:,.0f}"
    if value >= 100:
        return f"${value:,.1f}".rstrip("0").rstrip(".")
    if value >= 1:
        return f"${value:,.2f}".rstrip("0").rstrip(".")
    return f"${value:,.3f}".rstrip("0").rstrip(".")


def share_text(value: float, total: float) -> str:
    if total <= 0 or value <= 0:
        return "—"
    share = value * 100 / total
    if share < 0.05:
        return "~0%"
    if share < 1:
        return f"{share:.1f}%"
    return f"{share:.0f}%"


def unicode_table(headers, body, left_columns=frozenset({0})) -> str:
    values = [[str(cell) for cell in row] for row in [headers, *body]]
    widths = [max(len(row[i]) for row in values) for i in range(len(headers))]
    line = lambda left, middle, right: left + middle.join("─" * (width + 2) for width in widths) + right
    def render(row):
        cells = []
        for index, (value, width) in enumerate(zip(row, widths)):
            cells.append(f" {value.ljust(width) if index in left_columns else value.rjust(width)} ")
        return "│" + "│".join(cells) + "│"
    output = [line("┌", "┬", "┐"), render(values[0]), line("├", "┼", "┤")]
    for index, row in enumerate(values[1:]):
        output.append(render(row))
        if index != len(values[1:]) - 1:
            output.append(line("├", "┼", "┤"))
    output.append(line("└", "┴", "┘"))
    return "\n".join(output)


def model_table_rows(result, label_column="model"):
    """Build the [model/total] row list plus totals/cost-components used by
    both the top-level report and each project's nested breakdown."""
    rows = []
    totals = defaultdict(int)
    total_cost = 0.0
    all_priced = True
    components = defaultdict(float)
    for model in sorted(result):
        row = result[model]
        rows.append([
            model,
            f"{row['turns']:,}",
            token_text(row["input"]),
            token_text(row["cache_write"]),
            token_text(row["cache_read"]),
            token_text(row["output"]),
            money_text(row["api_cost"]),
        ])
        for key in ("turns", "input", "cache_write", "cache_read", "output"):
            totals[key] += row[key]
        if row["api_cost"] is None:
            all_priced = False
        else:
            total_cost += row["api_cost"]
        for component, cost in row["cost_components"].items():
            components[component] += cost
    rows.append([
        "total",
        f"{totals['turns']:,}",
        token_text(totals["input"]),
        token_text(totals["cache_write"]),
        token_text(totals["cache_read"]),
        token_text(totals["output"]),
        money_text(total_cost if all_priced else None),
    ])
    return rows, totals, total_cost, all_priced, components


def report_table(result, start, end, display_zone, first, last, diagnostics, long_requests, unpriced, proxies, by_project=None):
    model_rows, totals, total_cost, all_priced, components = model_table_rows(result)
    print(unicode_table(
        ["model", "turns", "input", "cache write", "cache read", "output", "API $"],
        model_rows,
    ))
    nonzero_components = [(name, cost) for name, cost in components.items() if cost > 0]
    if len(nonzero_components) >= 2:
        print()
        order = ["cache read", "cache write (1h TTL)", "cache write (5m TTL)", "output", "uncached input"]
        ordered = [name for name in order if components.get(name, 0) > 0]
        component_rows = [[name, money_text(components[name]), share_text(components[name], total_cost)] for name in ordered]
        print(unicode_table(["component", "$", "share"], component_rows))

    if by_project:
        print()
        project_summary_rows = []
        grand_turns = 0
        grand_cost = 0.0
        grand_all_priced = True
        for project in sorted(by_project, key=lambda p: -(sum(m["api_cost"] or 0 for m in by_project[p]["models"].values()))):
            models = by_project[project]["models"]
            turns = sum(m["turns"] for m in models.values())
            priced = all(m["api_cost"] is not None for m in models.values())
            cost = sum(m["api_cost"] or 0 for m in models.values())
            project_summary_rows.append([project, f"{turns:,}", money_text(cost if priced else None)])
            grand_turns += turns
            grand_cost += cost
            grand_all_priced = grand_all_priced and priced
        project_summary_rows.append(["total", f"{grand_turns:,}", money_text(grand_cost if grand_all_priced else None)])
        print(unicode_table(["project", "turns", "API $"], project_summary_rows))
        for project in sorted(by_project, key=lambda p: -(sum(m["api_cost"] or 0 for m in by_project[p]["models"].values()))):
            models = by_project[project]["models"]
            if not models:
                continue
            print(f"\n-- {project} --")
            rows, *_ = model_table_rows(models)
            print(unicode_table(["model", "turns", "input", "cache write", "cache read", "output", "API $"], rows))

    local_start = start.astimezone(display_zone)
    local_end = end.astimezone(display_zone)
    print(f"\nWindow: {local_start.isoformat()} through {local_end.isoformat()}")
    if first and last:
        print(f"Counted activity: {first.astimezone(display_zone).isoformat()} through {last.astimezone(display_zone).isoformat()}")
    if proxies:
        print("Pricing proxies: " + ", ".join(f"{source} -> {target}" for source, target in sorted(proxies.items())))
    if unpriced:
        print("Unpriced models: " + ", ".join(unpriced))
    if long_requests:
        print("Long-context requests: " + ", ".join(f"{model}={count}" for model, count in sorted(long_requests.items())))
    else:
        print("Long-context requests: none under the supplied rules")
    if diagnostics:
        print("Accounting diagnostics: " + ", ".join(f"{key}={value}" for key, value in sorted(diagnostics.items())))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-root", type=Path, default=Path.home() / ".claude" / "projects")
    parser.add_argument("--since", required=True, help="ISO timestamp; naive values require --timezone")
    end_group = parser.add_mutually_exclusive_group()
    end_group.add_argument("--until", help="ISO timestamp; defaults to now")
    end_group.add_argument("--until-message", help="exact user-message text whose transcript timestamp is the end")
    parser.add_argument("--timezone", help="IANA timezone for naive timestamps and display")
    parser.add_argument("--rate", action="append", default=[], metavar="MODEL=I,W5M,W1H,R,O")
    parser.add_argument("--proxy", action="append", default=[], metavar="OBSERVED=PRICING_MODEL")
    parser.add_argument("--long-context", action="append", default=[], metavar="MODEL=LIMIT,I_MULT,O_MULT")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--strict-pricing", action="store_true", help="fail if any observed model has no rate")
    parser.add_argument("--by-project", action="store_true", help="also break totals down by project directory (top-level dir under --logs-root)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        start = parse_timestamp(args.since, args.timezone)
        if args.until_message:
            end = message_timestamp(args.logs_root, args.until_message)
        elif args.until:
            end = parse_timestamp(args.until, args.timezone)
        else:
            end = datetime.now(timezone.utc)
        rates = parse_rates(args.rate)
        proxies = dict(parse_mapping(spec, "proxy") for spec in args.proxy)
        long_context = parse_long_context(args.long_context)
    except (argparse.ArgumentTypeError, ValueError) as exc:
        parser.error(str(exc))
    if end < start:
        parser.error("--until precedes --since")
    if not args.logs_root.is_dir():
        parser.error(f"logs root is not a directory: {args.logs_root}")

    events, diagnostics = read_usage(args.logs_root, start, end)
    result, long_requests, unpriced = calculate(events, rates, proxies, long_context)
    if args.strict_pricing and unpriced:
        raise SystemExit("missing rates for: " + ", ".join(unpriced))
    first = min((event["timestamp"] for event in events), default=None)
    last = max((event["timestamp"] for event in events), default=None)
    display_zone = ZoneInfo(args.timezone) if args.timezone else timezone.utc
    by_project = calculate_by_project(events, rates, proxies, long_context) if args.by_project else None

    if args.format == "json":
        serializable = {
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "first_counted": first.isoformat() if first else None,
            "last_counted": last.isoformat() if last else None,
            "models": result,
            "long_context_requests": long_requests,
            "unpriced_models": unpriced,
            "pricing_proxies": proxies,
            "diagnostics": diagnostics,
        }
        if by_project is not None:
            serializable["projects"] = by_project
        print(json.dumps(serializable, indent=2, sort_keys=True))
    else:
        report_table(result, start, end, display_zone, first, last, diagnostics, long_requests, unpriced, proxies, by_project=by_project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
