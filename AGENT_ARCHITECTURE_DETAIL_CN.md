# 车辆故障诊断 Agent 架构详细说明

本文档说明当前项目的实际架构、每个 Agent 的职责、输入输出格式、查询逻辑、经验库写入逻辑、数据库使用方式，以及 Summary Agent 的总结机制。

当前版本已经简化为用户指定的 6 个核心角色：

1. 车辆背景 Agent
2. 用户主观描述分析 Agent
3. DTC Agent
4. 知识库 Agent
5. 经验 Agent
6. 汇总 Summary Agent

未在需求中提到的复杂链路已经移除，例如传感器遥测分析、多轮正反辩论、维修建议 Agent、安全审查 Agent 等。

## 1. 总体架构

项目整体是一个 FastAPI + LangGraph 后端服务。

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
| `vehicleagents/graph/setup.py` | 定义 LangGraph 节点和顺序 |
| `vehicleagents/agents/analysts/` | 各分析 Agent |
| `vehicleagents/agents/summary_agent.py` | 最终汇总 Agent |
| `vehicleagents/agents/utils/memory.py` | 经验库抽象和 SQLite/Mongo 实现 |
| `vehicleagents/dataflows/providers/` | VIN、DTC、案例等数据查询 provider |

## 2. 运行流程

默认执行顺序如下：

```text
START
  -> VIN Context Analyst
  -> tools_vin_context?
  -> Msg Clear VIN Context
  -> Symptom Analyst
  -> tools_symptom?
  -> Msg Clear Symptom
  -> Diagnostic Code Analyst
  -> tools_dtc?
  -> Msg Clear Diagnostic Code
  -> Knowledge Analyst
  -> tools_knowledge?
  -> Msg Clear Knowledge
  -> Experience Analyst
  -> Msg Clear Experience
  -> Summary Agent
  -> END
```

默认启用的前置分析 Agent：

```text
vin_context, symptom, dtc, knowledge, experience
```

调用方也可以通过请求参数选择部分 Agent：

```json
{
  "parameters": {
    "selected_analysts": ["vin_context", "dtc", "experience"]
  }
}
```

但是 `Summary Agent` 是固定最终节点。也就是说，前面选哪些分析 Agent 可以配置，最后一定会汇总。

## 3. 共享 State

LangGraph 中所有 Agent 共享一个 `VehicleDiagnosisState`。关键字段如下：

| 字段 | 含义 |
| --- | --- |
| `diagnosis_id` | 本次诊断 ID |
| `case_date` | 案例创建时间 |
| `vin` | VIN |
| `vehicle` | 车辆档案 |
| `symptoms` | 用户提交的症状列表 |
| `dtc_codes` | 用户提交和历史合并后的 DTC 列表 |
| `dtc_history` | 根据 VIN 查询到的历史 DTC |
| `freeze_frame` | 冻结帧数据，当前保留字段，暂未深入使用 |
| `maintenance_history` | 根据 VIN 查询到的维修/保养记录 |
| `user_question` | 用户自然语言问题 |
| `vehicle_profile_report` | 车辆背景 Agent 报告 |
| `symptom_report` | 用户主观描述 Agent 报告 |
| `dtc_report` | DTC Agent 报告 |
| `knowledge_report` | 知识库 Agent 报告 |
| `experience_report` | 经验 Agent 报告 |
| `analyst_conclusions` | 每个 Agent 的简短结论，供后续节点快速阅读 |
| `analyst_tool_results` | 按 Agent 分组保存的工具调用结果 |
| `tool_errors` | 工具调用失败或超限错误 |
| `graph_trace` | LangGraph 执行轨迹 |
| `final_diagnosis` | 最终结果的 JSON 字符串 |
| `structured_result` | 最终结构化结果，API 查询结果主要返回这个 |

## 4. Agent 详细说明

### 4.1 车辆背景 Agent

代码位置：

```text
vehicleagents/agents/analysts/vin_context_analyst.py
```

图节点名称：

```text
VIN Context Analyst
```

职责：

- 根据 VIN 查询车辆档案。
- 根据 VIN 查询历史 DTC。
- 根据 VIN 查询维修/保养记录和里程。
- 判断车辆背景中是否存在历史故障线索。
- 标记数据缺口，例如缺少 VIN。

使用工具：

| 工具 | 作用 |
| --- | --- |
| `get_vehicle_profile_by_vin` | 查询车辆基础档案，如品牌、车型、年款、发动机、里程 |
| `get_dtc_history_by_vin` | 查询历史故障码 |
| `get_maintenance_history_by_vin` | 查询维修/保养历史 |

查询方式：

1. Agent 发现 state 中有 VIN，且还没有工具结果时，会请求工具。
2. 工具实际调用 `vehicleagents/dataflows/providers/vin_database.py`。
3. `vin_database.py` 会根据数据源模式查询：
   - `mongo`：强制查 MongoDB，失败直接报错。
   - `auto`：优先查 MongoDB，失败或查不到时走 mock。
   - `mock`：直接走内置 mock 数据。
4. MongoDB 涉及集合：
   - `vehicle_profiles`
   - `vin_dtc_history`
   - `vin_maintenance_history`

输出写入字段：

```text
vehicle_profile_report
vehicle
dtc_history
maintenance_history
```

输出格式：

```json
{
  "analyst": "VIN Context Analyst",
  "conclusion": "有问题 / 无问题",
  "reason": "存在历史故障码 / 未发现历史故障 / VIN 缺失",
  "vin": "LFV3A23C0J3000001",
  "vehicle": {
    "vin": "LFV3A23C0J3000001",
    "make": "Volkswagen",
    "model": "Sagitar",
    "model_year": 2020,
    "engine_code": "EA211-1.4T",
    "mileage_km": 86240
  },
  "dtc_history_count": 2,
  "maintenance_history_count": 1,
  "data_gaps": [],
  "tool_errors": []
}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `analyst` | 生成报告的 Agent 名称 |
| `conclusion` | 当前 Agent 对自己领域的简短判断 |
| `reason` | 形成该判断的原因 |
| `vin` | 当前诊断使用的 VIN |
| `vehicle` | 查询到的车辆档案 |
| `dtc_history_count` | 历史 DTC 数量 |
| `maintenance_history_count` | 维修/保养记录数量 |
| `data_gaps` | 缺失数据，例如 `vin_missing` |
| `tool_errors` | 本 Agent 工具调用中的错误 |

注意：当前部分旧中文文案在源码里有乱码现象，结构不受影响，后续可以单独修正文案。

### 4.2 用户主观描述分析 Agent

代码位置：

```text
vehicleagents/agents/analysts/symptom_analyst.py
```

图节点名称：

```text
Symptom Analyst
```

职责：

- 读取用户提交的症状。
- 识别症状数量。
- 计算最高严重程度。
- 提取主要主诉。
- 根据症状、DTC、车辆信息查询相似案例。

使用工具：

| 工具 | 作用 |
| --- | --- |
| `retrieve_repair_cases` | 根据症状、DTC、车辆信息查询相似案例 |

查询方式：

1. 如果请求中有 `symptoms`，Agent 会构造查询：

```json
{
  "symptoms": [],
  "dtc_codes": [],
  "vehicle": {}
}
```

2. 调用 `retrieve_repair_cases`。
3. 工具实际调用 `vehicleagents/dataflows/providers/local_cases.py`。
4. `local_cases.py` 当前主要按 DTC 查询：
   - 如果 MongoDB 可用且有 DTC，会查 `repair_cases` 集合：

```json
{
  "dtc_codes": {
    "$in": ["P0301", "P0171"]
  }
}
```

   - 按 `confidence` 降序。
   - 最多返回 5 条。
   - 如果没有 MongoDB 或无命中，并且包含 `P0301`，返回 mock 相似案例。

输出写入字段：

```text
symptom_report
```

输出格式：

```json
{
  "analyst": "Symptom Analyst",
  "conclusion": "有问题 / 无问题",
  "reason": "用户报告 1 个症状，最高严重程度 medium",
  "symptom_count": 1,
  "max_severity": "medium",
  "symptoms": [
    {
      "name": "rough idle",
      "description": "怠速抖动",
      "condition": "idle",
      "severity": "medium",
      "frequency": "intermittent"
    }
  ],
  "primary_complaint": "rough idle",
  "similar_cases": [
    [
      {
        "case_id": "mock_case_p0301_001",
        "summary": "Rough idle and P0301 resolved after swapping cylinder 1 ignition coil.",
        "confirmed_root_cause": "cylinder 1 ignition coil failure",
        "repair": ["replace ignition coil", "inspect spark plug"],
        "confidence": 0.62
      }
    ]
  ],
  "tool_errors": []
}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `symptom_count` | 用户提交的症状数量 |
| `max_severity` | 当前症状中的最高严重程度，按 `low < medium < high < critical` 判断 |
| `symptoms` | 原始症状列表 |
| `primary_complaint` | 主诉，优先取第一个症状名称 |
| `similar_cases` | 根据症状/DTC 查到的相似案例 |
| `tool_errors` | 工具调用错误 |

### 4.3 DTC Agent

代码位置：

```text
vehicleagents/agents/analysts/diagnostic_code_analyst.py
```

图节点名称：

```text
Diagnostic Code Analyst
```

职责：

- 合并用户提交 DTC 和 VIN 历史 DTC。
- 查询每个 DTC 的含义、常见原因、严重程度。
- 查询 DTC 组合模式。
- 输出故障码层面的分析报告。

使用工具：

| 工具 | 作用 |
| --- | --- |
| `lookup_dtc_code` | 查询单个 DTC 的解释 |
| `search_dtc_combinations` | 查询多个 DTC 之间的组合模式 |

查询方式：

1. 读取：
   - `state["dtc_codes"]`
   - `state["dtc_history"]`
2. 提取历史 DTC 中的 `code`。
3. 与用户提交 DTC 合并去重。
4. 默认对前两个 DTC 调用 `lookup_dtc_code`。
5. 如果故障码数量不足两个，会调用 `search_dtc_combinations`。
6. 工具实际调用 `vehicleagents/dataflows/providers/local_dtc.py`。
7. 当前 DTC 字典是本地字典，包含如 `P0301`, `P0171`, `P0420`, `P0128` 等。

输出写入字段：

```text
dtc_report
dtc_codes
```

输出格式：

```json
{
  "analyst": "Diagnostic Code Analyst",
  "conclusion": "有问题 / 无问题",
  "reason": "检测到 P0171, P0301",
  "codes": ["P0171", "P0301"],
  "lookups": [
    {
      "code": "P0301",
      "description": "Cylinder 1 Misfire Detected",
      "common_causes": [
        "cylinder 1 ignition coil",
        "spark plug",
        "injector",
        "compression issue"
      ],
      "severity": "medium"
    }
  ],
  "combinations": [
    {
      "pattern": "misfire_with_lean_condition",
      "interpretation": "Cylinder misfire together with lean condition can indicate intake leak, fuel delivery issue, or ignition fault aggravated by mixture imbalance.",
      "priority": "high"
    }
  ],
  "active_history": [],
  "tool_errors": []
}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `codes` | 用户提交和历史 DTC 合并后的故障码 |
| `lookups` | 单个 DTC 的解释结果 |
| `combinations` | 多 DTC 组合模式 |
| `active_history` | VIN 历史 DTC 明细 |
| `tool_errors` | DTC 工具调用错误 |

### 4.4 知识库 Agent

代码位置：

```text
vehicleagents/agents/analysts/knowledge_analyst.py
```

图节点名称：

```text
Knowledge Analyst
```

职责：

- 根据车辆、症状、DTC 查询知识库/案例库。
- 当前实现使用本地案例 provider。
- 后续可以替换为外部 RAG MCP。

使用工具：

| 工具 | 作用 |
| --- | --- |
| `retrieve_repair_cases` | 查询维修知识库或案例库 |

查询方式：

构造查询：

```json
{
  "vehicle": {},
  "symptoms": [],
  "dtc_codes": []
}
```

然后调用 `retrieve_repair_cases`。当前实际查询逻辑和用户主观描述 Agent 使用同一个工具：

1. MongoDB 可用时，按 `dtc_codes` 查询 `repair_cases` 集合。
2. 按 `confidence` 降序。
3. 最多返回 5 条。
4. 无 MongoDB 或无命中时，根据内置 mock 规则返回。

输出写入字段：

```text
knowledge_report
```

输出格式：

```json
{
  "analyst": "Knowledge Analyst",
  "conclusion": "有问题 / 无问题",
  "reason": "检索到 1 个相似案例",
  "similar_cases": [
    [
      {
        "case_id": "case_p0301_ignition_coil_001",
        "dtc_codes": ["P0301"],
        "symptoms": ["rough idle", "engine vibration"],
        "summary": "Rough idle and P0301 resolved after replacing cylinder 1 ignition coil.",
        "confirmed_root_cause": "cylinder 1 ignition coil failure",
        "repair": ["replace cylinder 1 ignition coil", "clear DTC", "road test"],
        "confidence": 0.78
      }
    ]
  ],
  "case_count": 1,
  "knowledge_sources": ["local_dtc", "local_cases"],
  "tool_errors": []
}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `similar_cases` | 知识库或案例库命中的相似案例 |
| `case_count` | 命中的案例数量 |
| `knowledge_sources` | 使用的知识来源标识 |
| `tool_errors` | 工具调用错误 |

### 4.5 经验 Agent

代码位置：

```text
vehicleagents/agents/analysts/experience_analyst.py
```

图节点名称：

```text
Experience Analyst
```

职责：

- 只负责读取经验库。
- 查询已经确认过的历史维修案例。
- 不负责写入经验库。

为什么只读：

诊断过程中的结果是“推断”，不是“确认事实”。如果 Agent 自动把推断结果写进经验库，误诊也会被沉淀，后续相似案例会被污染。因此当前设计是：

```text
Experience Agent 只读经验库
确认维修结果 outcome 接口才写经验库
```

查询方式：

1. 构造经验查询对象：

```json
{
  "vehicle": {},
  "symptoms": [],
  "dtc_codes": []
}
```

2. 将该对象序列化成 JSON 字符串。
3. 调用：

```python
memory.get_memories(current_situation, n_matches=3)
```

4. 当前 memory 检索方式是 token overlap：
   - 把当前 query 文本拆成 token。
   - 把历史案例的 `situation + recommendation` 拆成 token。
   - 计算 token 重合度。
   - 按相似度和时间排序。
   - 返回前 3 条。

输出写入字段：

```text
experience_report
```

输出格式：

```json
{
  "analyst": "Experience Analyst",
  "conclusion": "has_similar_cases",
  "reason": "found 1 confirmed similar case(s)",
  "query": {
    "vehicle": {
      "make": "Volkswagen",
      "model": "Sagitar"
    },
    "symptoms": [
      {
        "name": "rough idle",
        "severity": "medium"
      }
    ],
    "dtc_codes": ["P0301"]
  },
  "similar_cases": [
    {
      "situation": "{\"dtc_codes\":[\"P0301\"],\"symptoms\":[...],\"vehicle\":{},\"vin\":\"LFV3A23C0J3000001\"}",
      "recommendation": "{\"confirmed_root_cause\":\"cylinder 1 ignition coil failure\",\"repairs_performed\":[\"replace ignition coil\"],\"resolved\":true}",
      "metadata": {
        "task_id": "task-id",
        "stored_at": "2026-05-19T..."
      },
      "created_at": "2026-05-19T...",
      "score": 0.8
    }
  ]
}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `conclusion` | 是否命中相似经验，值通常是 `has_similar_cases` 或 `no_similar_cases` |
| `reason` | 命中数量说明 |
| `query` | 本次用于查经验库的结构化查询 |
| `similar_cases` | 命中的历史确认案例 |
| `score` | 当前简单 token overlap 相似度分数 |

## 5. Summary Agent 详细说明

代码位置：

```text
vehicleagents/agents/summary_agent.py
```

图节点名称：

```text
Summary Agent
```

职责：

- 汇总前面所有 Agent 的报告。
- 生成最终诊断摘要。
- 生成故障假设排序。
- 给出置信度。
- 给出下一步检查计划。
- 附带完整报告、工具错误、执行轨迹。

读取字段：

```text
vehicle_profile_report
symptom_report
dtc_report
knowledge_report
experience_report
```

输出字段：

```text
final_diagnosis
structured_result
```

### 5.1 Summary 是否必须使用 LLM？

不必须。

Summary Agent 支持两种模式：

```text
有 deep_llm -> 优先调用 LLM 汇总
没有 deep_llm 或 LLM 失败 -> 使用规则 fallback
```

也就是说，项目没有配置 LLM 时仍然可以跑通，只是总结能力比较简单。

### 5.2 LLM 汇总模式

如果配置了 `deep_llm`，Summary Agent 会构造 prompt：

```json
{
  "role": "summary_agent",
  "instruction": "Return strict JSON with keys summary, confidence_score, ranked_hypotheses, inspection_plan. Use only the provided analyst reports.",
  "reports": {
    "vehicle_profile_report": "...",
    "symptom_report": "...",
    "dtc_report": "...",
    "knowledge_report": "...",
    "experience_report": "..."
  }
}
```

要求 LLM 返回严格 JSON，至少包含：

```json
{
  "summary": "...",
  "confidence_score": 0.75,
  "ranked_hypotheses": [],
  "inspection_plan": []
}
```

如果 LLM 返回不是合法 JSON，或者缺少 `summary` / `ranked_hypotheses`，系统会丢弃 LLM 结果，转入规则 fallback。

### 5.3 规则 fallback 模式

当前规则逻辑：

| 条件 | 输出假设 |
| --- | --- |
| 包含 `P0301` | `Cylinder 1 ignition system fault` |
| 包含 `P0171` | `Lean mixture related fault` |
| 没有明确 DTC | `Undetermined fault` |

经验案例会影响概率：

```text
P0301 且经验库有 similar_cases -> probability = 0.58
P0301 且经验库无 similar_cases -> probability = 0.50
P0171 -> probability = 0.36
无明确 DTC -> probability = 0.20
```

最终 `confidence_score` 取所有假设中的最高 `probability`。

### 5.4 Summary 最终输出格式

```json
{
  "summary": "Most likely fault: Cylinder 1 ignition system fault.",
  "confidence_score": 0.58,
  "ranked_hypotheses": [
    {
      "rank": 1,
      "fault": "Cylinder 1 ignition system fault",
      "probability": 0.58,
      "evidence_for": ["P0301", "rough idle"],
      "evidence_against": [
        "ignition, injector, intake leak, and compression still need confirmation"
      ]
    },
    {
      "rank": 2,
      "fault": "Lean mixture related fault",
      "probability": 0.36,
      "evidence_for": ["P0171"],
      "evidence_against": [
        "fuel trim and intake leak data not confirmed"
      ]
    }
  ],
  "inspection_plan": [
    "Verify active and pending DTCs.",
    "Confirm the customer complaint under the reported working condition.",
    "Inspect the top-ranked fault area before replacing parts."
  ],
  "knowledge_sources": ["local_dtc", "local_cases"],
  "similar_experience_cases": [],
  "diagnosis_id": "diagnosis-id",
  "vin": "LFV3A23C0J3000001",
  "vehicle": {},
  "analyst_conclusions": {
    "VIN Context Analyst": "有问题 - 存在历史故障码",
    "Symptom Analyst": "有问题 - 用户报告 1 个症状",
    "Diagnostic Code Analyst": "有问题 - 检测到 P0301",
    "Knowledge Analyst": "有问题 - 检索到 1 个相似案例",
    "Experience Analyst": "has_similar_cases - found 1 confirmed similar case(s)"
  },
  "tool_errors": [],
  "diagnostic_trace": [
    {
      "node": "START",
      "status": "entered",
      "detail": "initial_state_created"
    },
    {
      "node": "Summary Agent",
      "status": "completed",
      "detail": "Most likely fault: Cylinder 1 ignition system fault."
    }
  ],
  "reports": {
    "vehicle_profile_report": "...",
    "symptom_report": "...",
    "dtc_report": "...",
    "knowledge_report": "...",
    "experience_report": "..."
  }
}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `summary` | 面向用户的最终一句话摘要 |
| `confidence_score` | 总体置信度，目前取最高假设概率 |
| `ranked_hypotheses` | 排序后的故障假设列表 |
| `ranked_hypotheses[].rank` | 排名 |
| `ranked_hypotheses[].fault` | 故障名称 |
| `ranked_hypotheses[].probability` | 当前规则或 LLM 给出的概率 |
| `ranked_hypotheses[].evidence_for` | 支持该故障的证据 |
| `ranked_hypotheses[].evidence_against` | 反证、缺失验证项或不确定点 |
| `inspection_plan` | 下一步检查建议 |
| `knowledge_sources` | 使用过的知识来源 |
| `similar_experience_cases` | 经验库命中的相似确认案例 |
| `diagnosis_id` | 诊断 ID |
| `vin` | VIN |
| `vehicle` | 车辆档案 |
| `analyst_conclusions` | 每个 Agent 的简短结论 |
| `tool_errors` | 所有工具错误 |
| `diagnostic_trace` | 图执行轨迹 |
| `reports` | 每个 Agent 的完整原始报告 |

## 6. 经验库写入流程

当前没有“经验写入 Agent”作为 LangGraph 节点。

写入发生在服务层：

```text
POST /api/vehicle-diagnosis/tasks/{task_id}/outcome
```

路由：

```text
app/routers/vehicle_diagnosis.py
```

服务方法：

```text
app/services/vehicle_diagnosis_service.py -> record_outcome()
```

### 6.1 为什么不让 Summary Agent 自动写？

Summary Agent 的结果是诊断推断，不一定是真实根因。经验库应该只保存已经确认的维修结果，否则会把误诊写进去，后续检索会被污染。

因此当前规则是：

```text
诊断阶段：只读经验
维修确认后：通过 outcome 接口写经验
```

### 6.2 outcome 请求格式

```json
{
  "confirmed_root_cause": "cylinder 1 ignition coil failure",
  "repairs_performed": ["replace ignition coil"],
  "resolved": true,
  "notes": "更换后怠速恢复正常"
}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `confirmed_root_cause` | 人工或维修流程确认后的真实根因 |
| `repairs_performed` | 实际执行的维修动作 |
| `resolved` | 故障是否解决 |
| `notes` | 补充说明，当前 outcome 会保存到任务记录，但 memory recommendation 暂未写入 notes |

### 6.3 写入 memory 的数据结构

`record_outcome()` 会从原任务 request 中构造 `situation`，从 outcome 中构造 `recommendation`。

`situation`：

```json
{
  "vin": "LFV3A23C0J3000001",
  "vehicle": {
    "make": "Volkswagen",
    "model": "Sagitar",
    "model_year": 2020
  },
  "symptoms": [
    {
      "name": "rough idle",
      "severity": "medium"
    }
  ],
  "dtc_codes": ["P0301", "P0171"]
}
```

`recommendation`：

```json
{
  "confirmed_root_cause": "cylinder 1 ignition coil failure",
  "repairs_performed": ["replace ignition coil"],
  "resolved": true
}
```

然后调用：

```python
self.memory.add_case(
    situation=json.dumps(situation, ensure_ascii=False, sort_keys=True),
    recommendation=json.dumps(recommendation, ensure_ascii=False, sort_keys=True),
    metadata={
        "task_id": task_id,
        "stored_at": "..."
    },
)
```

注意：当前 `situation` 和 `recommendation` 在 memory 中是 JSON 字符串，不是 MongoDB 嵌套对象。

### 6.4 MongoDB 写入格式

默认服务环境使用 MongoDB。

配置：

```text
VEHICLE_DIAGNOSIS_MONGO_URI=mongodb://127.0.0.1:27017
VEHICLE_DIAGNOSIS_MONGO_DATABASE=vehicle_diagnosis
```

经验库集合：

```text
vehicle_memory_cases
```

写入文档格式：

```json
{
  "memory_id": "uuid",
  "situation": "{\"dtc_codes\":[\"P0301\"],\"symptoms\":[...],\"vehicle\":{},\"vin\":\"LFV3A23C0J3000001\"}",
  "recommendation": "{\"confirmed_root_cause\":\"cylinder 1 ignition coil failure\",\"repairs_performed\":[\"replace ignition coil\"],\"resolved\":true}",
  "metadata": {
    "task_id": "task-id",
    "stored_at": "2026-05-19T..."
  },
  "created_at": "2026-05-19T..."
}
```

MongoDB 当前索引：

```text
created_at
```

### 6.5 SQLite 写入格式

测试或手动注入 SQLite repository 时，会使用 SQLite。

表名：

```text
vehicle_memory_cases
```

字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `memory_id` | TEXT PRIMARY KEY | 经验 ID |
| `situation` | TEXT | JSON 字符串，描述当时车辆、症状、DTC |
| `recommendation` | TEXT | JSON 字符串，描述确认根因和维修结果 |
| `metadata_json` | TEXT | JSON 字符串，保存任务 ID、写入时间等 |
| `created_at` | TEXT | 创建时间 |

SQLite 当前索引：

```text
created_at
```

## 7. 用数据库就行吗？

可以。当前阶段用数据库完全够用，尤其是 MongoDB。

原因：

- 经验案例天然是文档型数据。
- 每条案例包含车辆、症状、DTC、确认根因、维修动作、是否解决。
- MongoDB 很适合保存这种结构。
- 当前项目已经默认使用 MongoDB 保存任务、结果、outcome 和 memory cases。

但长期建议做两步优化。

### 7.1 第一阶段：继续使用当前数据库方案

当前方案能跑通闭环：

```text
诊断任务 -> Summary 输出 -> 人工确认 outcome -> 写入 vehicle_memory_cases -> 后续 Experience Agent 查询
```

适合 MVP 和演示。

### 7.2 第二阶段：把 memory 改成结构化对象

当前 `situation` / `recommendation` 是 JSON 字符串，不方便直接建索引查询。

建议后续改成：

```json
{
  "memory_id": "uuid",
  "vin": "LFV3A23C0J3000001",
  "vehicle": {
    "make": "Volkswagen",
    "model": "Sagitar",
    "model_year": 2020,
    "mileage_km": 86240
  },
  "symptoms": [
    {
      "name": "rough idle",
      "severity": "medium",
      "condition": "idle"
    }
  ],
  "dtc_codes": ["P0301", "P0171"],
  "confirmed_root_cause": "cylinder 1 ignition coil failure",
  "repairs_performed": ["replace ignition coil"],
  "resolved": true,
  "source_task_id": "task-id",
  "created_at": "2026-05-19T..."
}
```

然后可以建立索引：

```text
vin
dtc_codes
symptoms.name
confirmed_root_cause
created_at
```

这样查询会比 token overlap 更稳定。

### 7.3 第三阶段：增加向量检索

当经验案例数量上来后，可以增加 embedding/vector 检索：

```text
MongoDB 字段过滤 + 向量相似度召回
```

例如：

1. 先按品牌、车型、DTC 粗过滤。
2. 再用症状描述、维修结果、工况做向量相似度排序。
3. 最后返回 Top N 给 Experience Agent。

## 8. 查询 Agent 之间的区别

虽然 Symptom Agent、Knowledge Agent、Experience Agent 都会“查案例”，但它们定位不同。

| Agent | 查什么 | 数据来源 | 是否是确认经验 |
| --- | --- | --- | --- |
| Symptom Agent | 根据用户主诉查类似维修案例 | `repair_cases` / mock | 不一定 |
| Knowledge Agent | 根据车辆、症状、DTC 查知识库/案例库 | `repair_cases` / 后续 RAG MCP | 不一定 |
| Experience Agent | 查已经通过 outcome 确认的历史案例 | `vehicle_memory_cases` | 是 |

建议后续把三者进一步拆清：

- Symptom Agent 专注症状结构化，不一定查案例。
- Knowledge Agent 接 RAG MCP，查维修手册、技术公告、知识库。
- Experience Agent 查确认维修闭环案例。

## 9. 当前接口闭环

### 9.1 创建诊断任务

```http
POST /api/vehicle-diagnosis/tasks
```

请求示例：

```json
{
  "vin": "LFV3A23C0J3000001",
  "symptoms": [
    {
      "name": "rough idle",
      "severity": "medium",
      "condition": "idle"
    }
  ],
  "dtc_codes": ["P0301", "P0171"],
  "parameters": {
    "selected_analysts": ["vin_context", "symptom", "dtc", "knowledge", "experience"],
    "diagnosis_depth": "standard"
  }
}
```

### 9.2 查询任务状态

```http
GET /api/vehicle-diagnosis/tasks/{task_id}/status
```

### 9.3 查询诊断结果

```http
GET /api/vehicle-diagnosis/tasks/{task_id}/result
```

返回的是 `structured_result`。

### 9.4 提交确认维修结果并写入经验库

```http
POST /api/vehicle-diagnosis/tasks/{task_id}/outcome
```

请求示例：

```json
{
  "confirmed_root_cause": "cylinder 1 ignition coil failure",
  "repairs_performed": ["replace ignition coil"],
  "resolved": true,
  "notes": "更换后怠速恢复正常，清码后未复现。"
}
```

写入成功返回：

```json
{
  "task_id": "task-id",
  "outcome": {
    "confirmed_root_cause": "cylinder 1 ignition coil failure",
    "repairs_performed": ["replace ignition coil"],
    "resolved": true,
    "notes": "更换后怠速恢复正常，清码后未复现。"
  },
  "stored": true
}
```

## 10. 一句话总结

当前项目是一个顺序式多 Agent 诊断流水线：

```text
车辆背景、主观症状、DTC、知识库、经验库分别收集证据；
Summary Agent 负责融合证据并输出结构化诊断；
经验库只保存人工确认后的维修结果；
MongoDB 作为当前默认持久化数据库完全可用，后续建议升级为结构化字段 + 向量检索。
```
