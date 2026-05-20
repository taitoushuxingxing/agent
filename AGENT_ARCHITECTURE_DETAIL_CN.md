# 车辆故障诊断 Agent 架构详细说明

本文档说明当前项目的实际架构、每个 Agent 的职责边界、输入输出格式、工具调用方式，以及 Summary Agent 如何统一完成最终辩论和交叉验证。

当前默认流程为 4 个前置 Agent + 1 个最终 Summary Agent：

1. 历史故障和维修记录 Agent：`vin_context`
2. 用户主观描述 Agent：`symptom`
3. DTC Agent：`dtc`
4. RAG 知识库 Agent：`knowledge`
5. 汇总/辩论 Agent：`Summary Agent`

`experience` 节点仍作为兼容可选项保留，用于查询 outcome 确认后的维修记忆；默认流程不启用。确认维修结果仍通过 outcome API 写入经验库，不由 Summary 自动写入。

## 1. 总体架构

```text
用户 / 前端 / 调用方
  -> FastAPI Router
  -> VehicleDiagnosisService
  -> VehicleDiagnosisGraph
  -> LangGraph Agent 流程
  -> structured_result
  -> 查询结果接口返回
```

主要代码位置：

| 模块 | 作用 |
| --- | --- |
| `app/routers/vehicle_diagnosis.py` | FastAPI 路由，负责创建任务、查询状态、查询结果、提交确认维修结果 |
| `app/services/vehicle_diagnosis_service.py` | 任务服务层，负责任务入库、队列、调用诊断图、保存结果、写入经验库 |
| `vehicleagents/graph/vehicle_graph.py` | 诊断图入口，创建初始 state 并调用 LangGraph |
| `vehicleagents/graph/setup.py` | 定义 LangGraph 节点和执行顺序 |
| `vehicleagents/agents/analysts/` | 各前置分析 Agent |
| `vehicleagents/agents/summary_agent.py` | 最终汇总/辩论 Agent |
| `vehicleagents/agents/utils/agent_utils.py` | Tool 节点、消息清理、报告写入等公共逻辑 |
| `vehicleagents/dataflows/providers/` | VIN、DTC、案例等数据查询 provider |

## 2. 默认运行流程

```text
START
  -> VIN Context Analyst
  -> tools_vin_context?
  -> Msg Clear VIN Context
  -> Symptom Analyst
  -> Msg Clear Symptom
  -> Diagnostic Code Analyst
  -> tools_dtc?
  -> Msg Clear Diagnostic Code
  -> Knowledge Analyst
  -> tools_knowledge?
  -> Msg Clear Knowledge
  -> Summary Agent
  -> END
```

默认启用的前置 Agent：

```text
vin_context, symptom, dtc, knowledge
```

可选 Agent 集合：

```text
vin_context, symptom, dtc, knowledge, experience
```

`vin_context` 和 `symptom` 在业务职责上相互独立，后续可以通过 LangGraph reducer 做并行优化。当前实现保持顺序执行，优先保证状态合并、工具结果和进度 trace 稳定。

## 3. 共享 State

LangGraph 中所有 Agent 共享 `VehicleDiagnosisState`。关键字段如下：

| 字段 | 说明 |
| --- | --- |
| `diagnosis_id` | 本次诊断 ID |
| `vin` | VIN |
| `vehicle` | 车辆档案 |
| `symptoms` | 用户提交的症状列表 |
| `user_question` | 用户原始主诉 |
| `dtc_codes` | 用户提交和历史合并后的 DTC 列表 |
| `dtc_history` | 根据 VIN 查询到的历史 DTC |
| `freeze_frame` | 冻结帧数据 |
| `maintenance_history` | 维修/保养记录 |
| `vehicle_profile_report` | 历史记录 Agent 报告 |
| `symptom_report` | 主观描述 Agent 报告 |
| `dtc_report` | DTC Agent 报告 |
| `knowledge_report` | RAG 知识库 Agent 报告 |
| `experience_report` | 可选经验 Agent 报告 |
| `analyst_conclusions` | 每个 Agent 的简短结论 |
| `analyst_tool_results` | 按 Agent 分组保存的工具调用结果 |
| `structured_result` | Summary 输出的结构化最终结果 |

## 4. Agent 职责边界

### 4.1 历史故障和维修记录 Agent

代码：

```text
vehicleagents/agents/analysts/vin_context_analyst.py
```

职责：

- 根据 VIN 查询车辆档案。
- 根据 VIN 查询历史 DTC。
- 根据 VIN 查询维修/保养记录。
- 输出历史事实，不推断最终根因。

工具：

| 工具 | 说明 |
| --- | --- |
| `get_vehicle_profile_by_vin` | 查询车辆档案 |
| `get_dtc_history_by_vin` | 查询历史故障码 |
| `get_maintenance_history_by_vin` | 查询维修/保养记录 |

输出重点：

```json
{
  "analyst": "VIN Context Analyst",
  "role": "historical_record_collector",
  "conclusion": "has_history_findings",
  "vehicle": {},
  "dtc_history": [],
  "maintenance_history": [],
  "handoff_note": "本报告只提供 VIN 车辆档案、历史故障和维修记录事实。"
}
```

### 4.2 用户主观描述 Agent

代码：

```text
vehicleagents/agents/analysts/symptom_analyst.py
```

职责：

- 将用户口语化描述做语义标准化。
- 提取标准症状、触发条件、频率、严重程度、疑似系统。
- 给出待验证的疑似故障点和排查方向。
- 生成可选的专业搜索词，用于后续外部搜索或 RAG 检索优化。

不做：

- 不查询维修案例库。
- 不查询 RAG。
- 不读取 DTC。
- 不给最终维修结论。

输出重点：

```json
{
  "analyst": "Symptom Analyst",
  "role": "subjective_hypothesis_provider",
  "semantic_standardization": {
    "standard_symptoms": ["冷车启动异常", "异常抖动"],
    "trigger_conditions": ["冷车启动"],
    "affected_systems": ["engine"],
    "severity": "medium",
    "frequency": "未明确"
  },
  "suspected_fault_points": [
    {
      "fault_point": "火花塞/点火线圈",
      "system": "engine_ignition",
      "priority": "high",
      "reason": "冷车抖动或怠速不稳常见于缺火相关问题"
    }
  ],
  "inspection_directions": [
    {
      "target": "火花塞/点火线圈",
      "suggested_dtc_focus": ["P0300-P0306", "P0171", "P0172"],
      "data_stream_focus": ["misfire_count", "short_term_fuel_trim", "long_term_fuel_trim"]
    }
  ],
  "search_strategy": {
    "should_search_web": false,
    "search_queries": [],
    "source_policy": "优先权威维修资料、召回/通病信息；过滤纯主观论坛吐槽"
  }
}
```

### 4.3 DTC Agent

代码：

```text
vehicleagents/agents/analysts/diagnostic_code_analyst.py
```

职责：

- 接收上游 `symptom_report` 中的 `inspection_directions`。
- 将疑似系统和排查方向用于 DTC 查询优先级排序。
- 查询并解释当前/历史 DTC。
- 查询 DTC 组合模式。
- 携带冻结帧和数据流事实。
- 只提交客观证据，不做最终交叉验证。

工具：

| 工具 | 说明 |
| --- | --- |
| `lookup_dtc_code` | 查询单个 DTC 的解释 |
| `search_dtc_combinations` | 查询多个 DTC 之间的组合模式 |

输出重点：

```json
{
  "analyst": "Diagnostic Code Analyst",
  "role": "objective_evidence_collector",
  "conclusion": "has_dtc_evidence",
  "upstream_focus": {
    "suspected_systems": ["engine_ignition"],
    "suggested_dtc_focus": ["P0300-P0306"]
  },
  "codes": ["P0301"],
  "lookups": [],
  "combinations": [],
  "freeze_frame": {},
  "handoff_note": "本报告只陈述 DTC/冻结帧/数据流事实，不执行最终交叉验证。"
}
```

### 4.4 RAG 知识库 Agent

代码：

```text
vehicleagents/agents/analysts/knowledge_analyst.py
```

职责：

- 接收主观假设、DTC 客观事实、车辆信息。
- 检索车辆手册、维修资料、技术公告、召回通病和历史案例。
- 输出维修知识参考。

不做：

- 不判断主观描述和 DTC 谁更可信。
- 不给最终根因。
- 不写经验库。

工具：

| 工具 | 说明 |
| --- | --- |
| `retrieve_repair_cases` | 当前本地案例检索；后续可替换为 MCP RAG |

输出重点：

```json
{
  "analyst": "Knowledge Analyst",
  "role": "rag_reference_retriever",
  "conclusion": "has_references",
  "query": {
    "semantic_standardization": {},
    "suspected_fault_points": [],
    "dtc_codes": ["P0301"],
    "retrieval_goal": "查找该车型在上述主观现象和 DTC/数据流条件下的维修手册步骤、技术公告、召回通病和已确认维修案例。"
  },
  "repair_references": [],
  "knowledge_sources": ["vehicle_manuals", "repair_cases"],
  "handoff_note": "本报告只提供维修知识参考，不执行最终判断。"
}
```

### 4.5 Summary Agent

代码：

```text
vehicleagents/agents/summary_agent.py
```

职责：

- 汇总前面所有 Agent 的报告。
- 在这里统一执行交叉验证和辩论。
- 处理主观描述、DTC 客观证据、RAG 知识之间的冲突。
- 输出最终诊断结论、置信度、故障排序和检查计划。

核心规则：

1. 客观优先：DTC、冻结帧、维修记录通常比用户体感更接近事实。
2. RAG 背书：最终维修建议应尽量得到手册、技术资料或历史案例支持。
3. 不过早过滤：DTC 和 RAG 上游节点只提交材料，避免中间节点提前丢失信息。
4. 低证据保守：只有主诉、没有 DTC/RAG 支撑时，结论标为疑似，建议进一步读取数据或路试。

LLM Prompt 核心：

```json
{
  "role": "summary_debate_agent",
  "instruction": "Use only the provided reports. Do the cross-validation/debate here, not in upstream agents. Compare subjective complaint hypotheses, objective VIN/DTC/freeze-frame facts, and RAG manual/case references. Prefer objective data and authoritative RAG when they conflict with subjective wording.",
  "case_file": {
    "vehicle_and_history": "...",
    "subjective_complaint_and_hypotheses": "...",
    "objective_dtc_data": "...",
    "rag_manual_and_cases": "...",
    "confirmed_experience_memory": "..."
  }
}
```

输出重点：

```json
{
  "summary": "Most likely fault: Cylinder 1 ignition system fault.",
  "final_conclusion": "Cylinder 1 ignition system fault",
  "confidence_score": 0.7,
  "confidence_level": "高",
  "ranked_hypotheses": [],
  "debate_notes": [
    "主观描述 Agent 提供语义标准化和待验证故障假设。",
    "DTC Agent 只提交客观 DTC/冻结帧/数据流事实，不提前裁决。",
    "RAG Agent 只提交维修手册和案例参考。",
    "Summary Agent 在本节点统一执行主观、客观和知识库证据的交叉验证。"
  ],
  "reasoning_process": "简要证据依据",
  "inspection_plan": []
}
```

## 5. 数据库和 Skill 设计

凡是需要查数据库的部分，都通过确定性 Skill/Tool 封装。LLM 不直接生成 SQL。

原则：

- LLM 只负责提取参数和选择工具。
- SQL、Mongo 查询、CAN/OBD 指令由代码中固定函数执行。
- Tool 内部做参数校验、超时、重试和错误记录。
- 工具结果写入 `analyst_tool_results`，供后续 Agent 和 Summary 使用。

当前工具：

| 工具 | 数据来源 |
| --- | --- |
| `get_vehicle_profile_by_vin` | `vin_database.py` |
| `get_dtc_history_by_vin` | `vin_database.py` |
| `get_maintenance_history_by_vin` | `vin_database.py` |
| `lookup_dtc_code` | `local_dtc.py` |
| `search_dtc_combinations` | `local_dtc.py` |
| `retrieve_repair_cases` | `local_cases.py` |

## 6. 经验库写入

诊断阶段的 Summary 结果是推断，不一定是真实根因。经验库只保存已经确认的维修结果。

写入流程：

```text
诊断任务 -> Summary 输出 -> 人工/业务系统确认 outcome -> 写入 vehicle_memory_cases -> 后续可选 Experience Agent 查询
```

API：

```text
POST /api/vehicle-diagnosis/tasks/{task_id}/outcome
```

## 7. API 示例

创建诊断任务：

```json
{
  "vin": "LFV3A23C0J3000001",
  "user_question": "冷车启动的时候发动机抖得厉害，热车就好了",
  "symptoms": [
    {
      "name": "rough idle",
      "severity": "medium"
    }
  ],
  "dtc_codes": ["P0301"],
  "parameters": {
    "selected_analysts": ["vin_context", "symptom", "dtc", "knowledge"],
    "diagnosis_depth": "standard"
  }
}
```

## 8. 当前总结

当前项目是一条清晰的多 Agent 诊断流水线：

```text
历史事实 -> 主观假设 -> 客观 DTC 取证 -> RAG 资料参考 -> Summary 统一裁决
```

每个前置 Agent 只提交自己领域的材料。最终的主客观交叉验证、冲突仲裁和诊断结论，都统一放在 `Summary Agent` 完成。
