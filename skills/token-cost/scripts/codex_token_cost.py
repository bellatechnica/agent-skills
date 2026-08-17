#!/usr/bin/env python3
"""Estimate API-equivalent cost from Codex rollout JSONL files."""

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


TOKEN_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


@dataclass(frozen=True)
class Rate:
    input: float
    cache_write: float
    cache_read: float
    output: float


@dataclass(frozen=True)
class LongContext:
    threshold: int
    input_multiplier: float
    output_multiplier: float


@dataclass(frozen=True)
class FastMultiplier:
    api: float
    credits: float


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


def parse_rates(specs: Iterable[str], label: str = "rate") -> dict[str, Rate]:
    result: dict[str, Rate] = {}
    for spec in specs:
        model, raw = parse_mapping(spec, label)
        try:
            values = [float(part) for part in raw.split(",")]
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid numeric rate: {spec!r}") from exc
        if len(values) != 4 or any(value < 0 for value in values):
            raise argparse.ArgumentTypeError(
                "rate must be MODEL=INPUT,CACHE_WRITE,CACHE_READ,OUTPUT"
            )
        result[model] = Rate(*values)
    return result


def parse_fast_multipliers(specs: Iterable[str]) -> dict[str, FastMultiplier]:
    result: dict[str, FastMultiplier] = {}
    for spec in specs:
        model, raw = parse_mapping(spec, "fast multiplier")
        try:
            values = [float(part) for part in raw.split(",")]
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"invalid numeric fast multiplier: {spec!r}"
            ) from exc
        if len(values) != 2 or any(value <= 0 for value in values):
            raise argparse.ArgumentTypeError(
                "fast multiplier must be MODEL=API_MULTIPLIER,CREDIT_MULTIPLIER"
            )
        result[model] = FastMultiplier(*values)
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
            with path.open(encoding="utf-8") as handle:
                yield path, handle
        except OSError as exc:
            print(f"warning: cannot read {path}: {exc}", file=sys.stderr)


def message_timestamp(root: Path, exact_message: str) -> datetime:
    matches: list[datetime] = []
    for _, handle in iter_jsonl(root):
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "response_item":
                continue
            payload = record.get("payload") or {}
            if payload.get("type") != "message" or payload.get("role") != "user":
                continue
            content = payload.get("content") or []
            texts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "input_text"
            ]
            if texts == [exact_message]:
                matches.append(parse_timestamp(record["timestamp"], None))
    if not matches:
        raise SystemExit(f"no exact user message timestamp found for {exact_message!r}")
    return max(matches)


def zero_usage() -> dict[str, int]:
    return {key: 0 for key in TOKEN_KEYS}


def project_identity(cwd: str | None) -> tuple[tuple, str]:
    """Return a stable grouping key and a display path for a working directory."""
    if not cwd:
        return ("unknown",), "unknown working directory"
    path = Path(cwd)
    try:
        status = path.stat()
    except OSError:
        return ("path", str(path)), str(path)
    return ("inode", status.st_dev, status.st_ino), str(path)


def normalize_service_tier(value: str | None) -> str | None:
    if value in ("default", "standard"):
        return "standard"
    if value in ("priority", "fast"):
        return "fast"
    return value


def turn_service_tiers(handle) -> dict[str, set[str]]:
    """Collect every explicit service-tier marker within each live turn."""
    tiers = defaultdict(set)
    turn_id = None
    for line in handle:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = record.get("payload") or {}
        if record.get("type") == "turn_context":
            turn_id = payload.get("turn_id") or turn_id
            tier = normalize_service_tier(payload.get("service_tier"))
            if turn_id and tier:
                tiers[turn_id].add(tier)
            continue
        if (
            record.get("type") == "event_msg"
            and payload.get("type") == "thread_settings_applied"
        ):
            settings = payload.get("thread_settings") or {}
            tier = normalize_service_tier(settings.get("service_tier"))
            if turn_id and tier:
                tiers[turn_id].add(tier)
    handle.seek(0)
    return tiers


def read_usage(root: Path, start: datetime, end: datetime):
    events: list[dict] = []
    diagnostics = defaultdict(int)
    for path, handle in iter_jsonl(root):
        tiers_by_turn = turn_service_tiers(handle)
        live = False
        model = None
        service_tier = None
        turn_id = None
        cwd = None
        previous = None
        for line_number, line in enumerate(handle, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                diagnostics["bad_json_lines"] += 1
                continue
            record_type = record.get("type")
            payload = record.get("payload") or {}
            if record_type == "turn_context":
                live = True
                model = payload.get("model") or model
                turn_id = payload.get("turn_id") or turn_id
                cwd = payload.get("cwd") or cwd
                previous_service_tier = service_tier
                service_tier = normalize_service_tier(payload.get("service_tier"))
                candidates = tiers_by_turn.get(turn_id, set())
                if service_tier is None and previous_service_tier is not None:
                    service_tier = previous_service_tier
                if service_tier is None and len(candidates) == 1:
                    [service_tier] = candidates
                    diagnostics["tier_backfills_from_unique_turn_marker"] += 1
                continue
            if (
                record_type == "event_msg"
                and payload.get("type") == "thread_settings_applied"
            ):
                settings = payload.get("thread_settings") or {}
                service_tier = (
                    normalize_service_tier(settings.get("service_tier"))
                    or service_tier
                )
                continue
            if not live or record_type != "event_msg" or payload.get("type") != "token_count":
                continue
            info = payload.get("info") or {}
            cumulative = info.get("total_token_usage")
            if not cumulative:
                continue
            current = {key: int(cumulative.get(key, 0) or 0) for key in TOKEN_KEYS}
            timestamp = parse_timestamp(record.get("timestamp", ""), None)
            if timestamp < start:
                previous = current
                continue
            if timestamp > end:
                break
            if previous is None:
                last = info.get("last_token_usage") or {}
                delta = {key: int(last.get(key, 0) or 0) for key in TOKEN_KEYS}
                diagnostics["first_event_fallbacks"] += 1
            else:
                delta = {key: current[key] - previous[key] for key in TOKEN_KEYS}
                if any(value < 0 for value in delta.values()):
                    last = info.get("last_token_usage") or {}
                    delta = {key: int(last.get(key, 0) or 0) for key in TOKEN_KEYS}
                    diagnostics["counter_reset_fallbacks"] += 1
            previous = current
            if not any(delta.values()):
                continue
            project_key, project_path = project_identity(cwd)
            events.append(
                {
                    "timestamp": timestamp,
                    "model": model or "unknown",
                    "service_tier": service_tier or "unknown",
                    "turn_id": turn_id or f"{path}:{line_number}",
                    "project_key": project_key,
                    "project_path": project_path,
                    **delta,
                }
            )
    return events, dict(diagnostics)


def calculate(
    events,
    rates,
    credit_rates,
    fast_multipliers,
    proxies,
    long_context,
):
    rows = defaultdict(
        lambda: {
            "turn_ids": set(),
            "observed_models": set(),
            **zero_usage(),
            "cost": defaultdict(float),
            "credit_cost": defaultdict(float),
            "api_priced": True,
            "credits_priced": True,
        }
    )
    long_requests = defaultdict(int)
    unpriced_api = set()
    unpriced_credits = set()
    for event in events:
        observed = event["model"]
        pricing_model = proxies.get(observed, observed)
        service_tier = event["service_tier"]
        row = rows[(pricing_model, service_tier)]
        row["turn_ids"].add(event["turn_id"])
        row["observed_models"].add(observed)
        for key in TOKEN_KEYS:
            row[key] += event[key]

        cache_read = event["cached_input_tokens"]
        cache_write = event["cache_write_input_tokens"]
        uncached = event["input_tokens"] - cache_read - cache_write
        if uncached < 0:
            raise SystemExit(
                f"negative uncached input for {observed} at {event['timestamp'].isoformat()}; "
                "inspect this log schema before pricing"
            )
        rule = long_context.get(pricing_model)
        input_multiplier = 1.0
        output_multiplier = 1.0
        if rule and event["input_tokens"] > rule.threshold:
            input_multiplier = rule.input_multiplier
            output_multiplier = rule.output_multiplier
            long_requests[pricing_model] += 1

        variant = f"{observed} / {service_tier}"
        fast_multiplier = fast_multipliers.get(pricing_model)
        rate = rates.get(pricing_model)
        if (
            rate is None
            or service_tier not in ("standard", "fast")
            or (service_tier == "fast" and fast_multiplier is None)
        ):
            row["api_priced"] = False
            unpriced_api.add(variant)
        else:
            tier_multiplier = (
                fast_multiplier.api if service_tier == "fast" else 1.0
            )
            row["cost"]["uncached input"] += (
                uncached * rate.input * input_multiplier * tier_multiplier / 1_000_000
            )
            row["cost"]["cache write"] += (
                cache_write
                * rate.cache_write
                * input_multiplier
                * tier_multiplier
                / 1_000_000
            )
            row["cost"]["cache read"] += (
                cache_read
                * rate.cache_read
                * input_multiplier
                * tier_multiplier
                / 1_000_000
            )
            row["cost"]["output"] += (
                event["output_tokens"]
                * rate.output
                * output_multiplier
                * tier_multiplier
                / 1_000_000
            )

        if credit_rates:
            credit_rate = credit_rates.get(pricing_model)
            if (
                credit_rate is None
                or service_tier not in ("standard", "fast")
                or (service_tier == "fast" and fast_multiplier is None)
            ):
                row["credits_priced"] = False
                unpriced_credits.add(variant)
            else:
                tier_multiplier = (
                    fast_multiplier.credits if service_tier == "fast" else 1.0
                )
                row["credit_cost"]["uncached input"] += (
                    uncached * credit_rate.input * tier_multiplier / 1_000_000
                )
                row["credit_cost"]["cache write"] += (
                    cache_write
                    * credit_rate.cache_write
                    * tier_multiplier
                    / 1_000_000
                )
                row["credit_cost"]["cache read"] += (
                    cache_read
                    * credit_rate.cache_read
                    * tier_multiplier
                    / 1_000_000
                )
                row["credit_cost"]["output"] += (
                    event["output_tokens"]
                    * credit_rate.output
                    * tier_multiplier
                    / 1_000_000
                )
        else:
            row["credits_priced"] = False

    normalized = {}
    for (model, service_tier), row in rows.items():
        cache_read = row["cached_input_tokens"]
        cache_write = row["cache_write_input_tokens"]
        label = f"{model} / {service_tier}"
        normalized[label] = {
            "turns": len(row.pop("turn_ids")),
            "observed_models": sorted(row.pop("observed_models")),
            "service_tier": service_tier,
            "input": row["input_tokens"] - cache_read - cache_write,
            "cache_write": cache_write,
            "cache_read": cache_read,
            "output": row["output_tokens"],
            "reasoning_output": row["reasoning_output_tokens"],
            "total_tokens": row["total_tokens"],
            "cost_components": dict(row["cost"]),
            "api_cost": (
                sum(row["cost"].values()) if row["api_priced"] else None
            ),
            "credit_components": dict(row["credit_cost"]),
            "usage_credits": (
                sum(row["credit_cost"].values())
                if row["credits_priced"]
                else None
            ),
            "pricing_model": model,
        }
    return (
        normalized,
        dict(long_requests),
        sorted(unpriced_api),
        sorted(unpriced_credits),
    )


def calculate_by_project(
    events,
    rates,
    credit_rates,
    fast_multipliers,
    proxies,
    long_context,
):
    """Partition replay-safe events by their active working directory."""
    grouped = defaultdict(list)
    for event in events:
        grouped[event["project_key"]].append(event)

    projects = {}
    for key, project_events in grouped.items():
        aliases = sorted({event["project_path"] for event in project_events})
        project = aliases[0]
        models, long_requests, unpriced_api, unpriced_credits = calculate(
            project_events,
            rates,
            credit_rates,
            fast_multipliers,
            proxies,
            long_context,
        )
        projects[project] = {
            "aliases": aliases,
            "turns": len({event["turn_id"] for event in project_events}),
            "models": models,
            "long_context_requests": long_requests,
            "unpriced_models": unpriced_api,
            "unpriced_api_models": unpriced_api,
            "unpriced_credit_models": unpriced_credits,
        }
    return projects


def token_text(value: int) -> str:
    if value == 0:
        return "—"
    if value >= 1_000_000:
        text = f"{value / 1_000_000:,.1f}".rstrip("0").rstrip(".")
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


def credit_text(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


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


def project_totals(project):
    totals = defaultdict(int)
    total_cost = 0.0
    total_credits = 0.0
    all_api_priced = True
    all_credits_priced = True
    for row in project["models"].values():
        for key in ("input", "cache_write", "cache_read", "output"):
            totals[key] += row[key]
        if row["api_cost"] is None:
            all_api_priced = False
        else:
            total_cost += row["api_cost"]
        if row["usage_credits"] is None:
            all_credits_priced = False
        else:
            total_credits += row["usage_credits"]
    return (
        totals,
        total_cost,
        total_credits,
        all_api_priced,
        all_credits_priced,
    )


def report_table(
    result,
    total_turns,
    start,
    end,
    display_zone,
    first,
    last,
    diagnostics,
    long_requests,
    unpriced_api,
    unpriced_credits,
    proxies,
    credits_enabled,
    by_project=None,
):
    model_rows = []
    totals = defaultdict(int)
    total_cost = 0.0
    total_credits = 0.0
    all_api_priced = True
    all_credits_priced = credits_enabled
    components = defaultdict(float)
    tier_order = {"standard": 0, "fast": 1, "unknown": 2}
    for label, row in sorted(
        result.items(),
        key=lambda item: (
            item[1]["pricing_model"],
            tier_order.get(item[1]["service_tier"], 3),
            item[0],
        ),
    ):
        model_rows.append([
            label,
            f"{row['turns']:,}",
            token_text(row["input"]),
            token_text(row["cache_write"]),
            token_text(row["cache_read"]),
            token_text(row["output"]),
            money_text(row["api_cost"]),
            credit_text(row["usage_credits"]),
        ])
        for key in ("input", "cache_write", "cache_read", "output"):
            totals[key] += row[key]
        if row["api_cost"] is None:
            all_api_priced = False
        else:
            total_cost += row["api_cost"]
        if row["usage_credits"] is None:
            all_credits_priced = False
        else:
            total_credits += row["usage_credits"]
        for component, cost in row["cost_components"].items():
            components[component] += cost
    model_rows.append([
        "total",
        f"{total_turns:,}",
        token_text(totals["input"]),
        token_text(totals["cache_write"]),
        token_text(totals["cache_read"]),
        token_text(totals["output"]),
        money_text(total_cost if all_api_priced else None),
        credit_text(total_credits if all_credits_priced else None),
    ])
    print(unicode_table(
        [
            "model / mode",
            "turns",
            "input",
            "cache write",
            "cache read",
            "output",
            "API $",
            "usage credits",
        ],
        model_rows,
    ))
    nonzero_components = [(name, cost) for name, cost in components.items() if cost > 0]
    if all_api_priced and len(nonzero_components) >= 2:
        print()
        ordered = [name for name in ("cache read", "cache write", "output", "uncached input") if components[name] > 0]
        component_rows = [[name, money_text(components[name]), share_text(components[name], total_cost)] for name in ordered]
        print(unicode_table(["component", "$", "share"], component_rows))

    if by_project:
        print()
        project_rows = []
        project_totals_all = defaultdict(int)
        project_cost = 0.0
        project_credits = 0.0
        projects_api_priced = True
        projects_credits_priced = True
        summaries = []
        for project, data in by_project.items():
            (
                totals_by_project,
                cost,
                credits,
                api_priced,
                credits_priced,
            ) = project_totals(data)
            summaries.append(
                (
                    project,
                    data,
                    totals_by_project,
                    cost,
                    credits,
                    api_priced,
                    credits_priced,
                )
            )
        for (
            project,
            data,
            totals_by_project,
            cost,
            credits,
            api_priced,
            credits_priced,
        ) in sorted(
            summaries, key=lambda item: (-item[3], item[0])
        ):
            project_rows.append([
                project,
                f"{data['turns']:,}",
                token_text(totals_by_project["input"]),
                token_text(totals_by_project["cache_write"]),
                token_text(totals_by_project["cache_read"]),
                token_text(totals_by_project["output"]),
                money_text(cost if api_priced else None),
                credit_text(credits if credits_priced else None),
            ])
            project_totals_all["turns"] += data["turns"]
            for key in ("input", "cache_write", "cache_read", "output"):
                project_totals_all[key] += totals_by_project[key]
            project_cost += cost
            project_credits += credits
            projects_api_priced = projects_api_priced and api_priced
            projects_credits_priced = projects_credits_priced and credits_priced
        project_rows.append([
            "total",
            f"{project_totals_all['turns']:,}",
            token_text(project_totals_all["input"]),
            token_text(project_totals_all["cache_write"]),
            token_text(project_totals_all["cache_read"]),
            token_text(project_totals_all["output"]),
            money_text(project_cost if projects_api_priced else None),
            credit_text(project_credits if projects_credits_priced else None),
        ])
        print(unicode_table(
            [
                "project folder",
                "turns",
                "input",
                "cache write",
                "cache read",
                "output",
                "API $",
                "usage credits",
            ],
            project_rows,
        ))

    local_start = start.astimezone(display_zone)
    local_end = end.astimezone(display_zone)
    print(f"\nWindow: {local_start.isoformat()} through {local_end.isoformat()}")
    if first and last:
        print(f"Counted activity: {first.astimezone(display_zone).isoformat()} through {last.astimezone(display_zone).isoformat()}")
    if proxies:
        print("Pricing proxies: " + ", ".join(f"{source} -> {target}" for source, target in sorted(proxies.items())))
    if unpriced_api:
        print("Unpriced API models/modes: " + ", ".join(unpriced_api))
    if unpriced_credits:
        print("Unpriced credit models/modes: " + ", ".join(unpriced_credits))
    if long_requests:
        print("Long-context requests: " + ", ".join(f"{model}={count}" for model, count in sorted(long_requests.items())))
    else:
        print("Long-context requests: none under the supplied rules")
    if diagnostics:
        print("Accounting diagnostics: " + ", ".join(f"{key}={value}" for key, value in sorted(diagnostics.items())))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-root", type=Path, default=Path.home() / ".codex" / "sessions")
    parser.add_argument("--since", required=True, help="ISO timestamp; naive values require --timezone")
    end_group = parser.add_mutually_exclusive_group()
    end_group.add_argument("--until", help="ISO timestamp; defaults to now")
    end_group.add_argument("--until-message", help="exact user-message text whose rollout timestamp is the end")
    parser.add_argument("--timezone", help="IANA timezone for naive timestamps and display")
    parser.add_argument("--rate", action="append", default=[], metavar="MODEL=I,W,R,O")
    parser.add_argument(
        "--credit-rate",
        action="append",
        default=[],
        metavar="MODEL=I,W,R,O",
        help="usage credits per million uncached input, cache write, cache read, and output tokens",
    )
    parser.add_argument(
        "--fast-multiplier",
        action="append",
        default=[],
        metavar="MODEL=API,CREDITS",
        help="Fast-mode multipliers for API cost and usage credits",
    )
    parser.add_argument("--proxy", action="append", default=[], metavar="OBSERVED=PRICING_MODEL")
    parser.add_argument("--long-context", action="append", default=[], metavar="MODEL=LIMIT,I_MULT,O_MULT")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--strict-pricing", action="store_true", help="fail if any observed model has no rate")
    parser.add_argument("--by-project", action="store_true", help="also group token usage by the working directory recorded for each turn")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        start = parse_timestamp(args.since, args.timezone)
        if args.until_message:
            end = message_timestamp(args.sessions_root, args.until_message)
        elif args.until:
            end = parse_timestamp(args.until, args.timezone)
        else:
            end = datetime.now(timezone.utc)
        rates = parse_rates(args.rate)
        credit_rates = parse_rates(args.credit_rate, "credit rate")
        fast_multipliers = parse_fast_multipliers(args.fast_multiplier)
        proxies = dict(parse_mapping(spec, "proxy") for spec in args.proxy)
        long_context = parse_long_context(args.long_context)
    except (argparse.ArgumentTypeError, ValueError) as exc:
        parser.error(str(exc))
    if end < start:
        parser.error("--until precedes --since")
    if not args.sessions_root.is_dir():
        parser.error(f"sessions root is not a directory: {args.sessions_root}")

    events, diagnostics = read_usage(args.sessions_root, start, end)
    result, long_requests, unpriced_api, unpriced_credits = calculate(
        events,
        rates,
        credit_rates,
        fast_multipliers,
        proxies,
        long_context,
    )
    if args.strict_pricing and unpriced_api:
        raise SystemExit("missing API rates for: " + ", ".join(unpriced_api))
    first = min((event["timestamp"] for event in events), default=None)
    last = max((event["timestamp"] for event in events), default=None)
    display_zone = ZoneInfo(args.timezone) if args.timezone else timezone.utc
    by_project = (
        calculate_by_project(
            events,
            rates,
            credit_rates,
            fast_multipliers,
            proxies,
            long_context,
        )
        if args.by_project
        else None
    )

    if args.format == "json":
        serializable = {
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "first_counted": first.isoformat() if first else None,
            "last_counted": last.isoformat() if last else None,
            "models": result,
            "long_context_requests": long_requests,
            "unpriced_api_models": unpriced_api,
            "unpriced_credit_models": unpriced_credits,
            "unpriced_models": unpriced_api,
            "pricing_proxies": proxies,
            "diagnostics": diagnostics,
        }
        if by_project is not None:
            serializable["projects"] = by_project
        print(json.dumps(serializable, indent=2, sort_keys=True))
    else:
        report_table(
            result,
            len({event["turn_id"] for event in events}),
            start,
            end,
            display_zone,
            first,
            last,
            diagnostics,
            long_requests,
            unpriced_api,
            unpriced_credits,
            proxies,
            bool(credit_rates),
            by_project=by_project,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
