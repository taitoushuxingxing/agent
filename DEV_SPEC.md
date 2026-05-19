# Vehicle Fault Diagnosis Agent 简化设计

当前项目只保留用户指定的 agent 和工具边界：

1. `vin_context`：车辆背景 Agent，根据 VIN 查询车辆档案、历史 DTC、维修/保养记录和里程。
2. `symptom`：用户主观描述分析 Agent，基于预设 prompt/规则整理故障现象、工况、严重程度和主诉。
3. `dtc`：DTC Agent，查询故障码含义和故障码组合模式。
4. `knowledge`：知识库 Agent，查询知识库/案例库。后续可替换为外部 RAG MCP。
5. `experience`：经验 Agent，查询已确认的历史维修案例；确认结果写入由 API outcome 流程完成。
6. `Summary Agent`：汇总 Agent，融合前序报告并输出结构化诊断结论。

## LangGraph 流程

```text
START
  -> VIN Context Analyst -> tools_vin_context? -> Msg Clear VIN Context
  -> Symptom Analyst -> tools_symptom? -> Msg Clear Symptom
  -> Diagnostic Code Analyst -> tools_dtc? -> Msg Clear Diagnostic Code
  -> Knowledge Analyst -> tools_knowledge? -> Msg Clear Knowledge
  -> Experience Analyst -> Msg Clear Experience
  -> Summary Agent
  -> END
```

`selected_analysts` 可从以下集合选择：

```text
vin_context, symptom, dtc, knowledge, experience
```

默认顺序为：

```text
vin_context -> symptom -> dtc -> knowledge -> experience -> summary
```

## 工具

保留的工具：

- `get_vehicle_profile_by_vin`
- `get_dtc_history_by_vin`
- `get_maintenance_history_by_vin`
- `lookup_dtc_code`
- `search_dtc_combinations`
- `retrieve_repair_cases`

已删除用户未要求的旧复杂链路、传感器/事件工具，以及相关轮次配置项。

## 结果

最终结果由 `Summary Agent` 写入 `structured_result`，主要字段包括：

- `summary`
- `confidence_score`
- `ranked_hypotheses`
- `inspection_plan`
- `analyst_conclusions`
- `reports`
- `tool_errors`
- `diagnostic_trace`

确认维修结果仍通过 `/tasks/{task_id}/outcome` 写入经验库，用于后续 `Experience Analyst` 查询。
