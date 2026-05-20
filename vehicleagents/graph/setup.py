"""Set up the vehicle diagnosis workflow graph."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from vehicleagents.agents import (
    VehicleToolkit,
    create_diagnostic_code_analyst,
    create_knowledge_analyst,
    create_msg_delete,
    create_experience_analyst,
    create_summary_agent,
    create_symptom_analyst,
    create_vehicle_tool_node,
    create_vin_context_analyst,
)
from vehicleagents.agents.utils.agent_states import VehicleDiagnosisState
from vehicleagents.graph.conditional_logic import VehicleConditionalLogic

DEFAULT_ANALYSTS = ["vin_context", "symptom", "dtc", "knowledge"]


class VehicleGraphSetup:
    def __init__(
        self,
        quick_llm: Any = None,
        deep_llm: Any = None,
        toolkit: VehicleToolkit | None = None,
        conditional_logic: VehicleConditionalLogic | None = None,
        memory: Any = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.quick_llm = quick_llm
        self.deep_llm = deep_llm
        self.toolkit = toolkit or VehicleToolkit(config)
        self.conditional_logic = conditional_logic or VehicleConditionalLogic()
        self.memory = memory
        self.config = config or {}

    def setup_graph(self, selected_analysts: list[str] | None = None):
        selected = DEFAULT_ANALYSTS if selected_analysts is None else selected_analysts
        if not selected:
            raise ValueError("Vehicle diagnosis graph setup error: no analysts selected.")
        workflow = StateGraph(VehicleDiagnosisState)

        analyst_factories = {
            "vin_context": ("VIN Context", create_vin_context_analyst(self.quick_llm, self.toolkit)),
            "symptom": ("Symptom", create_symptom_analyst(self.quick_llm, self.toolkit)),
            "dtc": ("Diagnostic Code", create_diagnostic_code_analyst(self.quick_llm, self.toolkit)),
            "knowledge": ("Knowledge", create_knowledge_analyst(self.quick_llm, self.toolkit)),
            "experience": ("Experience", create_experience_analyst(self.memory)),
        }
        unknown = [key for key in selected if key not in analyst_factories]
        if unknown:
            supported = ", ".join(sorted(analyst_factories))
            raise ValueError(f"Unknown vehicle analysts: {', '.join(unknown)}. Supported analysts: {supported}.")

        for key in selected:
            node_title, node = analyst_factories[key]
            workflow.add_node(f"{node_title} Analyst", node)
            workflow.add_node(f"Msg Clear {node_title}", create_msg_delete(node_title))
            workflow.add_node(
                f"tools_{key}",
                create_vehicle_tool_node(
                    key,
                    f"tools_{key}",
                    self._tools_for_analyst(key),
                    max_tool_calls=self.conditional_logic.max_tool_calls_for(key),
                    max_retries=int(self.config.get("tool_max_retries", 1)),
                    timeout_seconds=float(self.config.get("tool_timeout_seconds", 10)),
                ),
            )

        workflow.add_node("Summary Agent", create_summary_agent(self.deep_llm))

        first_key = selected[0]
        first_title = analyst_factories[first_key][0]
        workflow.add_edge(START, f"{first_title} Analyst")

        for index, key in enumerate(selected):
            node_title = analyst_factories[key][0]
            clear_node = f"Msg Clear {node_title}"
            workflow.add_conditional_edges(
                f"{node_title} Analyst",
                self._conditional_for_analyst(key),
                {
                    f"tools_{key}": f"tools_{key}",
                    clear_node: clear_node,
                },
            )
            workflow.add_edge(f"tools_{key}", f"{node_title} Analyst")
            if index < len(selected) - 1:
                next_title = analyst_factories[selected[index + 1]][0]
                workflow.add_edge(clear_node, f"{next_title} Analyst")
            else:
                workflow.add_edge(clear_node, "Summary Agent")

        workflow.add_edge("Summary Agent", END)
        return workflow.compile()

    def _tools_for_analyst(self, key: str) -> list[Any]:
        return {
            "vin_context": [
                self.toolkit.get_vehicle_profile_by_vin,
                self.toolkit.get_dtc_history_by_vin,
                self.toolkit.get_maintenance_history_by_vin,
            ],
            "symptom": [],
            "dtc": [self.toolkit.lookup_dtc_code, self.toolkit.search_dtc_combinations],
            "knowledge": [self.toolkit.retrieve_repair_cases],
            "experience": [],
        }[key]

    def _conditional_for_analyst(self, key: str):
        return {
            "vin_context": self.conditional_logic.should_continue_vin_context,
            "symptom": self.conditional_logic.should_continue_symptom,
            "dtc": self.conditional_logic.should_continue_dtc,
            "knowledge": self.conditional_logic.should_continue_knowledge,
            "experience": self.conditional_logic.should_continue_experience,
        }[key]
