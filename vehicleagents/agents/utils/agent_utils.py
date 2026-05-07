"""Shared toolkit and utility nodes."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from uuid import uuid4
from typing import Annotated, Any

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langchain_core.tools import tool

from ...dataflows import interface
from ...default_config import DEFAULT_VEHICLE_CONFIG


def append_trace(state: dict[str, Any], node: str, status: str = "completed", detail: str = "") -> dict[str, Any]:
    trace = list(state.get("graph_trace") or [])
    entry = {"node": node, "status": status}
    if detail:
        entry["detail"] = detail
    trace.append(entry)
    return {"current_node": node, "graph_trace": trace}


def create_msg_delete(node_title: str | None = None):
    def delete_messages(state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages", [])
        removals = [RemoveMessage(id=m.id) for m in messages if hasattr(m, "id")]
        conclusions = state.get("analyst_conclusions") or {}
        if conclusions:
            content = "\n".join(f"[{analyst}：{conclusion}]" for analyst, conclusion in conclusions.items())
        else:
            content = "[分析师：暂无结论]"
        updates = append_trace(state, f"Msg Clear {node_title}" if node_title else "Msg Clear")
        updates["messages"] = removals + [HumanMessage(content=content)]
        return updates

    return delete_messages


def make_tool_call_message(tool_calls: list[dict[str, Any]], owner: str) -> AIMessage:
    normalized = []
    for call in tool_calls:
        normalized.append(
            {
                "name": call["name"],
                "args": call.get("args") or {},
                "id": call.get("id") or f"{owner}_{uuid4().hex}",
            }
        )
    return AIMessage(content=f"{owner} requests tool data.", tool_calls=normalized)


def invoke_llm_tool_decision(
    llm: Any,
    tools: list[Any],
    analyst_name: str,
    state: dict[str, Any],
    context: dict[str, Any],
) -> AIMessage | None:
    if llm is None:
        return None
    prompt = (
        f"You are {analyst_name} in a vehicle fault diagnosis graph. "
        "Decide whether one of your tools is needed before your final fixed conclusion. "
        "If a tool is needed, call the tool. If not, answer with JSON: "
        '{"need_tool": false, "conclusion": "有问题|无问题", "reason": "..."}.\n'
        f"State context:\n{json.dumps(context, ensure_ascii=False, default=str)}"
    )
    try:
        runner = llm.bind_tools(tools) if hasattr(llm, "bind_tools") else llm
        response = runner.invoke(prompt)
        if isinstance(response, AIMessage):
            return response
        tool_calls = _tool_calls_from_text(getattr(response, "content", response))
        if tool_calls:
            return make_tool_call_message(tool_calls, analyst_name)
    except Exception:
        return None
    return None


def conclusion_updates(
    state: dict[str, Any],
    node_name: str,
    report_key: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    conclusion = report.get("conclusion", "无问题")
    reason = report.get("reason", "")
    compact = f"{conclusion}" + (f" - {reason}" if reason else "")
    conclusions = dict(state.get("analyst_conclusions") or {})
    conclusions[node_name] = compact
    updates = append_trace(state, node_name, "concluded", compact)
    updates.update(
        {
            report_key: json.dumps(report, ensure_ascii=False, indent=2),
            "analyst_conclusions": conclusions,
            "pending_tool_owner": "",
        }
    )
    return updates


def _tool_calls_from_text(text: Any) -> list[dict[str, Any]]:
    if not isinstance(text, str):
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    calls = parsed.get("tool_calls") or parsed.get("tools") or []
    if isinstance(calls, dict):
        calls = [calls]
    return [call for call in calls if isinstance(call, dict) and call.get("name")]


def get_last_tool_calls(state: dict[str, Any]) -> list[dict[str, Any]]:
    messages = state.get("messages") or []
    if not messages:
        return []
    last = messages[-1]
    return list(getattr(last, "tool_calls", None) or [])


def create_vehicle_tool_node(
    analyst_key: str,
    node_name: str,
    tools: list[Any],
    max_tool_calls: int = 2,
    max_retries: int = 1,
    timeout_seconds: float = 10,
):
    tool_map = {item.name: item for item in tools}
    count_key = f"{analyst_key}_tool_call_count"

    def tool_node(state: dict[str, Any]) -> dict[str, Any]:
        calls = get_last_tool_calls(state)
        results_by_analyst = dict(state.get("analyst_tool_results") or {})
        analyst_results = list(results_by_analyst.get(analyst_key) or [])
        tool_errors = list(state.get("tool_errors") or [])
        messages: list[ToolMessage] = []
        state_updates: dict[str, Any] = {}

        remaining = max(max_tool_calls - state.get(count_key, 0), 0)
        executable_calls = calls[:remaining]
        skipped_calls = calls[remaining:]

        for call in skipped_calls:
            error = {
                "analyst": analyst_key,
                "tool": call.get("name", ""),
                "args": call.get("args") or {},
                "error": f"max_tool_calls exceeded for {analyst_key}",
            }
            tool_errors.append(error)
            analyst_results.append({**error, "ok": False})

        for call in executable_calls:
            name = call.get("name", "")
            args = call.get("args") or {}
            call_id = call.get("id") or f"{analyst_key}_{uuid4().hex}"
            try:
                if name not in tool_map:
                    raise ValueError(f"unknown tool: {name}")
                raw = _invoke_tool_with_retries(
                    tool_map[name],
                    args,
                    max_retries=max_retries,
                    timeout_seconds=timeout_seconds,
                )
                parsed = _loads_json(raw)
                record = {"tool": name, "args": args, "ok": True, "result": parsed}
                analyst_results.append(record)
                _merge_tool_result(state_updates, state, name, parsed)
                messages.append(ToolMessage(content=json.dumps(parsed, ensure_ascii=False), tool_call_id=call_id))
            except Exception as exc:
                error = {
                    "analyst": analyst_key,
                    "tool": name,
                    "args": args,
                    "error": str(exc),
                }
                tool_errors.append(error)
                analyst_results.append({"tool": name, "args": args, "ok": False, "error": str(exc)})
                messages.append(ToolMessage(content=json.dumps({"error": str(exc)}, ensure_ascii=False), tool_call_id=call_id))

        results_by_analyst[analyst_key] = analyst_results
        detail = f"{len(executable_calls)} tool call(s)"
        if skipped_calls:
            detail += f", {len(skipped_calls)} skipped"
        updates = append_trace(state, node_name, "completed", detail)
        updates.update(state_updates)
        updates.update(
            {
                "messages": messages,
                count_key: state.get(count_key, 0) + len(executable_calls),
                "analyst_tool_results": results_by_analyst,
                "tool_errors": tool_errors,
                "pending_tool_owner": analyst_key,
            }
        )
        return updates

    return tool_node


def _invoke_tool_with_retries(tool_item: Any, args: dict[str, Any], max_retries: int, timeout_seconds: float) -> Any:
    attempts = max(max_retries, 0) + 1
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            if timeout_seconds <= 0:
                return tool_item.invoke(args)
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(tool_item.invoke, args)
            try:
                return future.result(timeout=timeout_seconds)
            except TimeoutError as exc:
                future.cancel()
                last_error = TimeoutError(f"tool timed out after {timeout_seconds:g} seconds")
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return tool_item.invoke(args)


def _loads_json(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _merge_tool_result(state_updates: dict[str, Any], state: dict[str, Any], tool_name: str, result: Any) -> None:
    if tool_name == "get_vehicle_profile_by_vin" and isinstance(result, dict):
        vehicle = dict(state.get("vehicle") or {})
        vehicle.update(state_updates.get("vehicle") or {})
        vehicle.update(result)
        state_updates["vehicle"] = vehicle
    elif tool_name == "get_dtc_history_by_vin" and isinstance(result, list):
        state_updates["dtc_history"] = result
    elif tool_name == "get_maintenance_history_by_vin" and isinstance(result, list):
        state_updates["maintenance_history"] = result
    elif tool_name == "get_sensor_snapshot_by_vin" and isinstance(result, dict):
        state_updates["sensor_snapshot"] = result
    elif tool_name == "get_sensor_timeseries_by_vin" and isinstance(result, dict):
        state_updates["sensor_timeseries"] = result
    elif tool_name == "get_event_logs_by_vin" and isinstance(result, list):
        state_updates["event_logs"] = result


class VehicleToolkit:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = DEFAULT_VEHICLE_CONFIG.copy()
        if config:
            self._config.update(config)

    @staticmethod
    @tool
    def get_vehicle_profile_by_vin(vin: Annotated[str, "Vehicle identification number"]) -> str:
        """Fetch vehicle profile by VIN."""
        return json.dumps(interface.get_vehicle_profile_by_vin(vin), ensure_ascii=False)

    @staticmethod
    @tool
    def get_dtc_history_by_vin(vin: Annotated[str, "Vehicle identification number"]) -> str:
        """Fetch historical DTC records by VIN."""
        return json.dumps(interface.get_dtc_history_by_vin(vin), ensure_ascii=False)

    @staticmethod
    @tool
    def get_maintenance_history_by_vin(vin: Annotated[str, "Vehicle identification number"]) -> str:
        """Fetch maintenance records by VIN."""
        return json.dumps(interface.get_maintenance_history_by_vin(vin), ensure_ascii=False)

    @staticmethod
    @tool
    def get_sensor_snapshot_by_vin(vin: Annotated[str, "Vehicle identification number"]) -> str:
        """Fetch latest sensor snapshot by VIN."""
        return json.dumps(interface.get_sensor_snapshot_by_vin(vin), ensure_ascii=False)

    @staticmethod
    @tool
    def get_sensor_timeseries_by_vin(
        vin: Annotated[str, "Vehicle identification number"],
        signals: Annotated[list[str], "Signal names to fetch"],
    ) -> str:
        """Fetch sensor timeseries by VIN and signal list."""
        return json.dumps(interface.get_sensor_timeseries_by_vin(vin, signals), ensure_ascii=False)

    @staticmethod
    @tool
    def get_event_logs_by_vin(vin: Annotated[str, "Vehicle identification number"]) -> str:
        """Fetch vehicle event logs by VIN."""
        return json.dumps(interface.get_event_logs_by_vin(vin), ensure_ascii=False)

    @staticmethod
    @tool
    def lookup_dtc_code(code: Annotated[str, "DTC code, e.g. P0301"]) -> str:
        """Look up a DTC code in the local dictionary."""
        return json.dumps(interface.lookup_dtc_code(code), ensure_ascii=False)

    @staticmethod
    @tool
    def search_dtc_combinations(codes: Annotated[list[str], "DTC code list"]) -> str:
        """Search known diagnostic patterns for DTC combinations."""
        return json.dumps(interface.search_dtc_combinations(codes), ensure_ascii=False)

    @staticmethod
    @tool
    def retrieve_repair_cases(query: Annotated[dict[str, Any], "Case retrieval query"]) -> str:
        """Retrieve similar repair cases."""
        return json.dumps(interface.retrieve_repair_cases(query), ensure_ascii=False)

    @staticmethod
    @tool
    def analyze_telemetry_rules(
        sensor_snapshot: Annotated[dict[str, Any], "Sensor snapshot"],
        event_logs: Annotated[list[dict[str, Any]], "Event logs"],
    ) -> str:
        """Run deterministic telemetry checks for common fault signals."""
        findings: list[dict[str, Any]] = []
        signals = sensor_snapshot.get("signals", sensor_snapshot)

        def value(name: str) -> Any:
            item = signals.get(name)
            if isinstance(item, dict):
                return item.get("value")
            return item

        stft = value("stft_b1")
        ltft = value("ltft_b1")
        misfire_cyl_1 = value("misfire_count_cyl_1")
        battery_voltage = value("battery_voltage")

        if isinstance(stft, (int, float)) and stft > 15:
            findings.append({"signal": "stft_b1", "finding": "short term fuel trim is high", "severity": "medium"})
        if isinstance(ltft, (int, float)) and ltft > 10:
            findings.append({"signal": "ltft_b1", "finding": "long term fuel trim is high", "severity": "medium"})
        if isinstance(misfire_cyl_1, (int, float)) and misfire_cyl_1 > 0:
            findings.append({"signal": "misfire_count_cyl_1", "finding": "cylinder 1 misfire count is non-zero", "severity": "medium"})
        if isinstance(battery_voltage, (int, float)) and battery_voltage < 12.0:
            findings.append({"signal": "battery_voltage", "finding": "battery voltage is low", "severity": "medium"})
        for event in event_logs:
            if event.get("event_name") == "rough_idle_detected":
                findings.append({"event": "rough_idle_detected", "finding": "rough idle event correlates with symptom", "severity": event.get("severity", "medium")})
        return json.dumps({"findings": findings}, ensure_ascii=False)
