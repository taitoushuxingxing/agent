"""Set up the vehicle diagnosis workflow graph."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from vehicleagents.agents import (
    VehicleToolkit,
    create_counterfactual_researcher,
    create_diagnostic_code_analyst,
    create_diagnostic_planner,
    create_hypothesis_researcher,
    create_knowledge_analyst,
    create_msg_delete,
    create_repair_advisor,
    create_safety_analyst,
    create_safety_judge,
    create_symptom_analyst,
    create_telemetry_analyst,
    create_vin_context_analyst,
)
from vehicleagents.agents.utils.agent_states import VehicleDiagnosisState
from vehicleagents.graph.conditional_logic import VehicleConditionalLogic

DEFAULT_ANALYSTS = ["vin_context", "symptom", "dtc", "telemetry", "knowledge"]


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
            "telemetry": ("Telemetry", create_telemetry_analyst(self.quick_llm, self.toolkit)),
            "knowledge": ("Knowledge", create_knowledge_analyst(self.quick_llm, self.toolkit)),
        }
        unknown = [key for key in selected if key not in analyst_factories]
        if unknown:
            supported = ", ".join(sorted(analyst_factories))
            raise ValueError(f"Unknown vehicle analysts: {', '.join(unknown)}. Supported analysts: {supported}.")

        for key in selected:
            node_title, node = analyst_factories[key]
            workflow.add_node(f"{node_title} Analyst", node)
            workflow.add_node(f"Msg Clear {node_title}", create_msg_delete())

        workflow.add_node("Hypothesis Researcher", create_hypothesis_researcher(self.quick_llm, self.memory))
        workflow.add_node("Counterfactual Researcher", create_counterfactual_researcher(self.quick_llm, self.memory))
        workflow.add_node("Diagnostic Planner", create_diagnostic_planner(self.deep_llm, self.memory))
        workflow.add_node("Repair Advisor", create_repair_advisor(self.quick_llm, self.memory))
        workflow.add_node("Safety Analyst", create_safety_analyst(self.quick_llm))
        workflow.add_node("Safety Judge", create_safety_judge(self.deep_llm, self.memory))

        first_key = selected[0]
        first_title = analyst_factories[first_key][0]
        workflow.add_edge(START, f"{first_title} Analyst")

        for index, key in enumerate(selected):
            node_title = analyst_factories[key][0]
            clear_node = f"Msg Clear {node_title}"
            workflow.add_edge(f"{node_title} Analyst", clear_node)
            if index < len(selected) - 1:
                next_title = analyst_factories[selected[index + 1]][0]
                workflow.add_edge(clear_node, f"{next_title} Analyst")
            else:
                workflow.add_edge(clear_node, "Hypothesis Researcher")

        workflow.add_conditional_edges(
            "Hypothesis Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Counterfactual Researcher": "Counterfactual Researcher",
                "Diagnostic Planner": "Diagnostic Planner",
            },
        )
        workflow.add_conditional_edges(
            "Counterfactual Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Hypothesis Researcher": "Hypothesis Researcher",
                "Diagnostic Planner": "Diagnostic Planner",
            },
        )
        workflow.add_edge("Diagnostic Planner", "Repair Advisor")
        workflow.add_edge("Repair Advisor", "Safety Analyst")
        workflow.add_conditional_edges(
            "Safety Analyst",
            self.conditional_logic.should_continue_safety,
            {
                "Repair Advisor": "Repair Advisor",
                "Safety Judge": "Safety Judge",
            },
        )
        workflow.add_edge("Safety Judge", END)
        return workflow.compile()
