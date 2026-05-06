# 车辆故障诊断 Agent Dev Spec

## 1. 目标

基于 TradingAgents-CN 的 agent 架构，设计一个独立后端项目：车辆故障诊断 Agent。系统通过 HTTP API 接收 VIN、故障现象、DTC/OBD 码、传感器数据、埋点事件、维修历史等输入，经过多 agent 协作后输出结构化诊断结论、证据链、维修建议、风险等级和后续检查计划。

这个项目作为根目录下的独立内容存在，后续实现不直接塞进 `tradingagents/`，而是放在独立包中，必要时只复用当前项目的 LLM provider、日志、配置和任务队列思路。

设计原则：

- 遵循 TradingAgents 的核心模式：`Graph` 编排、`State` 共享上下文、`Analyst` 调工具产报告、`Researcher/Planner` 形成诊断方案、`Safety/Judge` 输出最终结论。
- 后端优先：不设计前端页面，只提供 REST API、任务状态查询和可选 SSE/WebSocket 进度。
- VIN 优先：VIN 是车辆画像、传感器、埋点、历史维修、历史故障的主索引。
- 工具优先：模型不能凭空诊断，必须优先调用 VIN 数据库、OBD 码库、传感器规则、埋点事件、维修手册、历史案例等工具。
- 可解释：最终输出必须包含症状证据、数据证据、排除项、优先级、置信度和安全提示。

## 2. 独立项目目录

建议根目录结构：

```text
vehicle_fault_diagnosis_agent/
  README.md
  DEV_SPEC.md
  pyproject.toml
  vehicleagents/
    __init__.py
    default_config.py
    graph/
      vehicle_graph.py
      setup.py
      conditional_logic.py
      signal_processing.py
      reflection.py
    agents/
      __init__.py
      analysts/
        vin_context_analyst.py
        symptom_analyst.py
        diagnostic_code_analyst.py
        telemetry_analyst.py
        knowledge_analyst.py
      researchers/
        hypothesis_researcher.py
        counterfactual_researcher.py
      planner/
        diagnostic_planner.py
      advisor/
        repair_advisor.py
      safety/
        safety_analyst.py
        safety_judge.py
      utils/
        agent_states.py
        agent_utils.py
        memory.py
        vehicle_context.py
    tools/
      vin_tools.py
      dtc_tools.py
      telemetry_tools.py
      symptom_tools.py
      knowledge_tools.py
      cost_tools.py
    dataflows/
      interface.py
      providers/
        vin_database.py
        sensor_database.py
        event_database.py
        local_dtc.py
        local_manuals.py
        local_cases.py
  app/
    main.py
    routers/
      vehicle_diagnosis.py
    services/
      vehicle_diagnosis_service.py
    models/
      vehicle_diagnosis.py
    schemas/
      vehicle_diagnosis.py
  tests/
```

如果后续要和当前 FastAPI 后端共进程运行，可以把 `vehicle_fault_diagnosis_agent/app/routers/vehicle_diagnosis.py` 挂载到主应用；如果要独立部署，则直接运行该目录下自己的 `app/main.py`。

## 3. 架构映射

| TradingAgents 角色 | 车辆诊断角色 | 责任 |
| --- | --- | --- |
| Market Analyst | Symptom Analyst | 分析用户描述、故障现象、发生条件、严重程度 |
| Fundamentals Analyst | VIN Context Analyst | 基于 VIN 补全车辆画像、配置、里程、历史数据 |
| News/Social Analyst | Knowledge Analyst | 查询维修手册、TSB/召回、常见故障库、案例摘要 |
| ToolNode | VIN/Telemetry/DTC Tools | 查询 VIN 数据库、传感器、埋点、DTC 知识 |
| Bull/Bear Researcher | Hypothesis / Counterfactual Researcher | 提出可能根因与反证排除路径 |
| Research Manager | Diagnostic Planner | 汇总证据，排序根因，生成检查计划 |
| Trader | Repair Advisor | 形成维修建议、预计工时、备件建议、是否可继续行驶 |
| Risk Judge | Safety Judge | 评估安全风险、拖车建议、紧急程度、误诊风险 |

推荐图：

```text
START
  -> VIN Context Analyst
  -> tools_vin_context -> VIN Context Analyst
  -> Msg Clear VIN Context
  -> Symptom Analyst
  -> tools_symptom -> Symptom Analyst
  -> Msg Clear Symptom
  -> Diagnostic Code Analyst
  -> tools_dtc -> Diagnostic Code Analyst
  -> Msg Clear Diagnostic Code
  -> Telemetry Analyst
  -> tools_telemetry -> Telemetry Analyst
  -> Msg Clear Telemetry
  -> Knowledge Analyst
  -> tools_knowledge -> Knowledge Analyst
  -> Msg Clear Knowledge
  -> Hypothesis Researcher
  -> Counterfactual Researcher
  -> Diagnostic Planner
  -> Repair Advisor
  -> Safety Analyst
  -> Safety Judge
  -> END
```

`selected_analysts` 可控制是否启用 `telemetry`、`knowledge` 等节点。没有 VIN 时仍可退化为症状 + DTC 诊断；有 VIN 时优先查询数据库。

## 4. VIN 数据库接入

你已有可通过 VIN 提供传感器、埋点信息的数据库，因此 VIN 数据应升级为一等数据源。

### 4.1 数据源抽象

在 `vehicleagents/dataflows/interface.py` 暴露统一接口：

```python
def get_vehicle_profile_by_vin(vin: str) -> dict: ...
def get_sensor_snapshot_by_vin(vin: str, time_range: dict | None = None) -> dict: ...
def get_sensor_timeseries_by_vin(vin: str, signals: list[str], time_range: dict) -> dict: ...
def get_event_logs_by_vin(vin: str, time_range: dict | None = None) -> list[dict]: ...
def get_dtc_history_by_vin(vin: str, time_range: dict | None = None) -> list[dict]: ...
def get_maintenance_history_by_vin(vin: str) -> list[dict]: ...
```

具体数据库适配放在：

- `providers/vin_database.py`: VIN 到车型、配置、生产批次、动力系统。
- `providers/sensor_database.py`: 传感器快照和时间序列。
- `providers/event_database.py`: 埋点事件、用户行为、车辆状态事件。

### 4.2 VIN Context Analyst

负责：

- 校验 VIN 格式和可用性。
- 调用 `get_vehicle_profile_by_vin`。
- 补全 `vehicle` 字段。
- 拉取最近 DTC 历史、维修历史、关键行驶里程。
- 判断数据缺口，如缺少车型年款、发动机型号、关键传感器。

输出 `vehicle_profile_report`。

### 4.3 Telemetry Analyst

负责：

- 调用 `get_sensor_snapshot_by_vin`、`get_sensor_timeseries_by_vin`、`get_event_logs_by_vin`。
- 根据故障现象和 DTC 自动选择信号集，例如：
  - 失火：`rpm`, `misfire_count`, `fuel_trim`, `o2_voltage`, `coil_status`
  - 电池/启动：`battery_voltage`, `alternator_voltage`, `start_attempts`
  - 过热：`coolant_temp`, `fan_status`, `vehicle_speed`, `load`
  - EV/混动：`soc`, `cell_voltage_delta`, `battery_temp`, `insulation_resistance`
- 输出异常传感器、异常时间窗口、埋点关联、数据质量。

输出 `telemetry_report`。

## 5. State 设计

参考 `tradingagents.agents.utils.agent_states.AgentState`，新增：

```python
class DiagnosticDebateState(TypedDict):
    hypothesis_history: str
    counterfactual_history: str
    history: str
    current_response: str
    planner_decision: str
    count: int

class SafetyReviewState(TypedDict):
    safety_history: str
    repair_history: str
    judge_decision: str
    latest_speaker: str
    count: int

class VehicleDiagnosisState(MessagesState):
    diagnosis_id: str
    case_date: str
    vin: str
    vehicle: dict
    symptoms: list[dict]
    dtc_codes: list[str]
    dtc_history: list[dict]
    sensor_snapshot: dict
    sensor_timeseries: dict
    event_logs: list[dict]
    freeze_frame: dict
    maintenance_history: list[dict]
    user_question: str

    vehicle_profile_report: str
    symptom_report: str
    dtc_report: str
    telemetry_report: str
    knowledge_report: str

    vin_context_tool_call_count: int
    symptom_tool_call_count: int
    dtc_tool_call_count: int
    telemetry_tool_call_count: int
    knowledge_tool_call_count: int

    diagnostic_debate_state: DiagnosticDebateState
    diagnostic_plan: str
    repair_advice: str
    safety_review_state: SafetyReviewState
    final_diagnosis: str
    structured_result: dict
```

关键字段：

- `vehicle`: `{vin, make, model, year, trim, engine, transmission, powertrain_type, mileage, region, production_batch}`
- `symptoms`: `[{name, description, severity, condition, frequency, first_seen_at}]`
- `event_logs`: `[{event_name, event_time, payload, source, severity}]`
- `sensor_timeseries`: `{signal_name: [{ts, value, unit, quality}]}`
- `structured_result`: API 直接返回的机器可读结论。

## 6. Tool 设计

工具统一放在 `VehicleToolkit`，沿用当前 `Toolkit` 的 `@tool` 模式。

| 工具 | 输入 | 输出 | 用途 |
| --- | --- | --- | --- |
| `get_vehicle_profile_by_vin` | `vin` | 车型、年款、配置、动力系统 | 补全车辆画像 |
| `get_dtc_history_by_vin` | `vin, time_range?` | 历史故障码、首次/末次出现时间 | 分析故障演化 |
| `get_sensor_snapshot_by_vin` | `vin, time_range?` | 关键传感器快照 | 快速定位异常 |
| `get_sensor_timeseries_by_vin` | `vin, signals, time_range` | 传感器时序 | 分析趋势和异常窗口 |
| `get_event_logs_by_vin` | `vin, time_range?` | 埋点事件列表 | 关联用户操作和车辆状态 |
| `lookup_dtc_code` | `code, make?, model?, year?` | DTC 含义、常见根因、严重度 | 解释故障码 |
| `search_dtc_combinations` | `codes[]` | 组合故障模式 | 分析多码关联 |
| `analyze_telemetry_rules` | `vehicle, sensor_snapshot, timeseries, event_logs` | 异常信号、阈值判断 | 规则化判断 |
| `search_service_bulletins` | `vehicle, symptoms, codes` | TSB/召回/已知问题 | 查知识库 |
| `retrieve_repair_cases` | `vehicle, symptoms, codes, telemetry_summary` | 相似案例、维修结果 | Memory/RAG |
| `estimate_repair_cost` | `parts, labor_hours, region` | 成本区间 | 维修建议 |
| `build_inspection_checklist` | `hypotheses` | 检查步骤 | 计划落地 |

工具调用限制：

- 每个 analyst 节点维护独立 `*_tool_call_count`。
- 默认 `max_tool_calls=2`。
- `vin_context` 和 `telemetry` 可配置为 `3`，因为需要分批查画像、传感器和埋点。
- 条件逻辑中若报告已生成且长度超过阈值，强制进入 `Msg Clear`。

## 7. Memory 设计

参考 `FinancialSituationMemory`，新增 `VehicleDiagnosisMemory`。

集合：

- `vehicle_fault_cases`: 历史故障案例。
- `vehicle_repair_outcomes`: 维修方案和最终结果。
- `vehicle_telemetry_patterns`: 传感器/埋点异常模式。
- `vehicle_safety_lessons`: 安全风险和误诊复盘。

记忆内容：

- situation: VIN 衍生画像 + 症状 + DTC + 关键传感器 + 埋点模式。
- recommendation: 根因、检查路径、维修动作、结果。
- metadata: make/model/year/engine/mileage/codes/signals/confirmed_root_cause/confidence。

查询时机：

- `Knowledge Analyst` 查询相似案例。
- `Telemetry Analyst` 查询相似传感器模式。
- `Diagnostic Planner` 查询历史成功检查路径。
- `Safety Judge` 查询高风险误诊案例。

写入时机：

- 初期通过 outcome API 回填维修结果后写入。
- 后续可在诊断任务完成后先写 pending memory，待用户确认维修结果后转为 confirmed。

## 8. Planner 与推理策略

`Diagnostic Planner` 是核心决策节点，不直接调用外部数据工具，负责整合前序报告和 memory。

输出必须包含：

- `ranked_hypotheses`: 按概率排序的根因列表。
- `evidence_for`: 支持证据，包括症状、DTC、传感器、埋点、历史案例。
- `evidence_against`: 反证或不确定点。
- `next_tests`: 推荐检查步骤，按低成本、低拆解优先。
- `stop_conditions`: 出现哪些现象应停止驾驶或拖车。
- `confidence`: `0.0-1.0`。

诊断优先级：

1. 先处理安全和继续行驶风险。
2. 优先解释 VIN 数据库中的真实 DTC、传感器异常和埋点事件。
3. 先考虑 DTC 与症状、传感器一致的根因。
4. 优先低成本、可验证、非侵入式检查。
5. 不把单一故障码直接等同于零件损坏。
6. 对缺失数据显式列出需要补充的信息。

## 9. API 设计

路由前缀：`/api/vehicle-diagnosis`

### 9.1 创建诊断任务

`POST /api/vehicle-diagnosis/tasks`

请求：

```json
{
  "vin": "LFV3A23C0J3000001",
  "vehicle": {
    "make": "optional",
    "model": "optional",
    "year": 2018,
    "mileage": 86000,
    "powertrain_type": "ice",
    "region": "CN"
  },
  "symptoms": [
    {
      "name": "发动机抖动",
      "description": "怠速明显抖动，加速无力",
      "condition": "冷车启动后更明显",
      "severity": "medium",
      "frequency": "often"
    }
  ],
  "dtc_codes": ["P0301", "P0171"],
  "sensor_snapshot": {},
  "freeze_frame": {},
  "time_range": {
    "start": "2026-05-05T00:00:00+08:00",
    "end": "2026-05-06T00:00:00+08:00"
  },
  "parameters": {
    "selected_analysts": ["vin_context", "symptom", "dtc", "telemetry", "knowledge"],
    "diagnosis_depth": "standard",
    "max_debate_rounds": 1
  }
}
```

说明：

- 如果请求里没有 `sensor_snapshot`，系统通过 VIN 和 `time_range` 自动查库。
- 如果请求里有 `sensor_snapshot`，以请求数据为优先，数据库数据作为补充。
- 如果请求里没有 `dtc_codes`，系统可通过 `get_dtc_history_by_vin` 自动补全最近故障码。

响应：

```json
{
  "success": true,
  "data": {
    "task_id": "uuid",
    "status": "submitted"
  }
}
```

### 9.2 查询状态

`GET /api/vehicle-diagnosis/tasks/{task_id}/status`

返回任务状态、当前节点、进度、耗时、错误信息。

### 9.3 查询结果

`GET /api/vehicle-diagnosis/tasks/{task_id}/result`

响应核心结构：

```json
{
  "success": true,
  "data": {
    "diagnosis_id": "uuid",
    "status": "completed",
    "vin": "LFV3A23C0J3000001",
    "vehicle": {},
    "summary": "最可能为一缸失火，需优先检查点火线圈、火花塞和进气泄漏。",
    "safety_level": "medium",
    "drivability": "limited",
    "confidence_score": 0.74,
    "ranked_hypotheses": [
      {
        "rank": 1,
        "fault": "一缸点火系统异常",
        "probability": 0.42,
        "evidence_for": ["P0301", "怠速抖动", "加速无力", "一缸失火计数异常"],
        "evidence_against": ["尚无一缸点火波形或火花塞状态"]
      }
    ],
    "inspection_plan": [],
    "repair_advice": {},
    "telemetry_findings": [],
    "reports": {
      "vehicle_profile_report": "",
      "symptom_report": "",
      "dtc_report": "",
      "telemetry_report": "",
      "knowledge_report": "",
      "diagnostic_plan": "",
      "safety_review": "",
      "final_diagnosis": ""
    }
  }
}
```

### 9.4 回填维修结果

`POST /api/vehicle-diagnosis/tasks/{task_id}/outcome`

用途：确认真实根因，写入 memory。

```json
{
  "confirmed_root_cause": "一缸点火线圈损坏",
  "repairs_performed": ["更换一缸点火线圈"],
  "resolved": true,
  "notes": "更换后怠速恢复正常，故障码清除后未复现。"
}
```

## 10. 数据持久化

业务集合建议：

- `vehicle_diagnosis_tasks`: 任务状态、输入摘要、执行进度。
- `vehicle_diagnosis_reports`: 完整报告、结构化结论、性能指标。
- `vehicle_repair_outcomes`: 用户回填的维修结果。
- `vehicle_knowledge_sources`: 本地知识库索引元数据。

外部 VIN 数据库建议通过 adapter 读取，不直接和诊断任务集合混在一起：

- `vin_vehicle_profiles`: VIN 画像。
- `vin_sensor_snapshots`: 传感器快照。
- `vin_sensor_timeseries`: 传感器时序。
- `vin_event_logs`: 埋点事件。
- `vin_dtc_history`: 历史故障码。

索引：

- `task_id` 唯一索引。
- `vin + created_at`。
- `user_id + created_at`。
- `vehicle.make + vehicle.model + vehicle.year`。
- `dtc_codes` 多键索引。
- `status + updated_at` 用于清理卡住任务。

## 11. 数据 Schema

本项目默认以 MongoDB 文档结构表达 schema，因为 VIN 画像、埋点和传感器扩展字段变化较快。若后续落 PostgreSQL/ClickHouse，可按同名字段映射。

### 11.1 VIN 车辆画像 `vin_vehicle_profiles`

```json
{
  "vin": "LFV3A23C0J3000001",
  "make": "Volkswagen",
  "brand": "大众",
  "model": "Sagitar",
  "model_year": 2018,
  "trim": "280TSI DSG",
  "platform": "MQB",
  "engine_code": "EA211",
  "engine": {
    "type": "ice",
    "displacement_l": 1.4,
    "fuel_type": "gasoline",
    "turbocharged": true
  },
  "transmission": {
    "type": "dct",
    "code": "DQ200",
    "gears": 7
  },
  "powertrain_type": "ice",
  "production": {
    "plant": "FAW-VW",
    "batch": "2018-W32",
    "date": "2018-08-12"
  },
  "region": "CN",
  "mileage_km": 86000,
  "first_registration_date": "2018-10-01",
  "warranty_status": "expired",
  "metadata": {
    "source": "internal_vin_db",
    "updated_at": "2026-05-06T19:00:00+08:00"
  }
}
```

必需字段：`vin`, `make`, `model`, `model_year`, `powertrain_type`。

推荐索引：

- `vin` 唯一索引。
- `make + model + model_year`。
- `engine_code`。
- `transmission.code`。

### 11.2 DTC 历史 `vin_dtc_history`

```json
{
  "vin": "LFV3A23C0J3000001",
  "code": "P0301",
  "status": "active",
  "ecu": "ECM",
  "description": "Cylinder 1 Misfire Detected",
  "severity": "medium",
  "first_seen_at": "2026-05-05T08:20:00+08:00",
  "last_seen_at": "2026-05-06T09:15:00+08:00",
  "occurrence_count": 7,
  "mileage_km": 86012,
  "freeze_frame_id": "ff_202605060915_001",
  "clear_count": 0,
  "raw": {}
}
```

推荐索引：

- `vin + last_seen_at`。
- `vin + code + status`。
- `code + last_seen_at`。

### 11.3 冻结帧 `vin_freeze_frames`

```json
{
  "freeze_frame_id": "ff_202605060915_001",
  "vin": "LFV3A23C0J3000001",
  "dtc_code": "P0301",
  "captured_at": "2026-05-06T09:15:00+08:00",
  "mileage_km": 86012,
  "signals": {
    "rpm": {"value": 760, "unit": "rpm"},
    "vehicle_speed": {"value": 0, "unit": "km/h"},
    "coolant_temp_c": {"value": 92, "unit": "C"},
    "stft_b1": {"value": 18.5, "unit": "%"},
    "ltft_b1": {"value": 12.1, "unit": "%"}
  },
  "raw": {}
}
```

### 11.4 传感器快照 `vin_sensor_snapshots`

```json
{
  "vin": "LFV3A23C0J3000001",
  "snapshot_id": "snap_202605060930_001",
  "captured_at": "2026-05-06T09:30:00+08:00",
  "mileage_km": 86013,
  "source": "telematics",
  "quality": "good",
  "signals": {
    "rpm": {"value": 760, "unit": "rpm", "quality": "good"},
    "battery_voltage": {"value": 12.4, "unit": "V", "quality": "good"},
    "coolant_temp_c": {"value": 92, "unit": "C", "quality": "good"},
    "stft_b1": {"value": 18.5, "unit": "%", "quality": "good"},
    "ltft_b1": {"value": 12.1, "unit": "%", "quality": "good"},
    "misfire_count_cyl_1": {"value": 43, "unit": "count", "quality": "good"}
  },
  "raw": {}
}
```

推荐索引：

- `vin + captured_at`。
- `snapshot_id` 唯一索引。

### 11.5 传感器时序 `vin_sensor_timeseries`

推荐以窄表事件点存储，适合 MongoDB、ClickHouse、TimescaleDB：

```json
{
  "vin": "LFV3A23C0J3000001",
  "ts": "2026-05-06T09:30:01+08:00",
  "signal": "rpm",
  "value": 760,
  "unit": "rpm",
  "quality": "good",
  "source": "telematics",
  "trip_id": "trip_20260506_001",
  "mileage_km": 86013
}
```

推荐索引：

- `vin + signal + ts`。
- `vin + trip_id + ts`。

信号命名规范：

- 使用小写 snake_case。
- 温度以 `_c` 结尾，如 `coolant_temp_c`。
- 电压以 `_voltage` 结尾。
- 百分比燃油修正使用 `stft_b1`, `ltft_b1`。
- 电动车电池使用 `hv_battery_soc`, `cell_voltage_delta_mv`, `battery_pack_temp_c`。

### 11.6 埋点事件 `vin_event_logs`

```json
{
  "vin": "LFV3A23C0J3000001",
  "event_id": "evt_202605060931_001",
  "event_name": "rough_idle_detected",
  "event_type": "vehicle_state",
  "event_time": "2026-05-06T09:31:00+08:00",
  "severity": "medium",
  "source": "vehicle_app",
  "trip_id": "trip_20260506_001",
  "mileage_km": 86013,
  "payload": {
    "duration_sec": 25,
    "rpm_variance": 180,
    "driver_reported": true
  },
  "tags": ["idle", "engine", "nvh"]
}
```

推荐索引：

- `vin + event_time`。
- `vin + event_name + event_time`。
- `event_type + event_time`。

事件分类：

- `driver_action`: 用户操作，如急加速、频繁启动、手动上报。
- `vehicle_state`: 车辆状态，如怠速抖动、过热、低电压。
- `system_alert`: 系统报警，如 MIL 点亮、ESP 报警。
- `maintenance`: 保养维修事件。
- `diagnostic`: 诊断仪或后台规则产生的诊断事件。

### 11.7 维修历史 `vin_maintenance_history`

```json
{
  "vin": "LFV3A23C0J3000001",
  "record_id": "maint_20260401_001",
  "service_date": "2026-04-01",
  "mileage_km": 84500,
  "service_type": "repair",
  "items": ["更换火花塞", "清洗节气门"],
  "parts": [
    {"name": "spark_plug", "brand": "NGK", "part_no": "xxx", "quantity": 4}
  ],
  "labor_hours": 1.2,
  "cost": {"amount": 680, "currency": "CNY"},
  "workshop": "internal_service_center",
  "notes": "怠速轻微抖动，清洗后改善。",
  "metadata": {}
}
```

### 11.8 诊断任务 `vehicle_diagnosis_tasks`

```json
{
  "task_id": "uuid",
  "user_id": "optional",
  "vin": "LFV3A23C0J3000001",
  "status": "running",
  "progress": 45,
  "current_step": "Telemetry Analyst",
  "request": {},
  "created_at": "2026-05-06T19:00:00+08:00",
  "updated_at": "2026-05-06T19:01:00+08:00",
  "started_at": "2026-05-06T19:00:02+08:00",
  "completed_at": null,
  "error_message": null
}
```

### 11.9 诊断报告 `vehicle_diagnosis_reports`

```json
{
  "diagnosis_id": "uuid",
  "task_id": "uuid",
  "vin": "LFV3A23C0J3000001",
  "vehicle": {},
  "summary": "",
  "safety_level": "medium",
  "drivability": "limited",
  "confidence_score": 0.74,
  "ranked_hypotheses": [],
  "inspection_plan": [],
  "repair_advice": {},
  "telemetry_findings": [],
  "reports": {},
  "performance_metrics": {},
  "created_at": "2026-05-06T19:04:00+08:00"
}
```

## 12. 配置

新增 `vehicleagents/default_config.py`：

```python
DEFAULT_VEHICLE_CONFIG = {
    "project_dir": "vehicle_fault_diagnosis_agent",
    "llm_provider": "openai",
    "quick_think_llm": "gpt-4o-mini",
    "deep_think_llm": "gpt-4o",
    "backend_url": "https://api.openai.com/v1",
    "max_tool_calls": 2,
    "max_debate_rounds": 1,
    "max_safety_discuss_rounds": 1,
    "memory_enabled": True,
    "knowledge_base_dir": "data/vehicle_knowledge",
    "result_dir": "results/vehicle_diagnosis",
    "vin_database": {
        "provider": "mongo",
        "uri_env": "VEHICLE_VIN_DB_URI",
        "database": "vehicle_data"
    }
}
```

## 13. 安全与合规

必须在系统提示词和最终结果中体现：

- 诊断结论是辅助判断，不能替代持证技师实车检查。
- 涉及制动、转向、燃油泄漏、高压电池、严重过热、气囊、冒烟、异响加剧等风险时，优先建议停止驾驶并联系专业救援。
- 不输出绕过排放、安全或防盗系统的非法操作。
- 不建议用户执行超出用户能力的高危维修动作。
- 对不确定结论明确标注置信度和需要补充的数据。

## 14. 实施里程碑

第一阶段：独立后端骨架

- 新增 `vehicle_fault_diagnosis_agent` 项目目录。
- 新增 `vehicleagents` 包、state、conditional logic、graph setup。
- 新增独立 FastAPI app、router 和 service。
- 使用 mock VIN 数据库和 mock 工具跑通完整图。

第二阶段：VIN 数据库工具

- 接入 `get_vehicle_profile_by_vin`。
- 接入 `get_sensor_snapshot_by_vin` 和 `get_sensor_timeseries_by_vin`。
- 接入 `get_event_logs_by_vin` 和 `get_dtc_history_by_vin`。
- 完成 Telemetry Analyst。

第三阶段：知识库与 Memory

- 接入 DTC 本地字典。
- 接入相似案例 memory。
- 接入传感器阈值规则工具。
- 完成结构化结果解析。

第四阶段：异步任务与持久化

- 写入 `vehicle_diagnosis_tasks` 和 `vehicle_diagnosis_reports`。
- 支持状态查询、结果查询、失败恢复。
- 增加 outcome 回填与 memory 写入。

第五阶段：质量和测试

- 单元测试：VIN adapter、工具、state 初始化、conditional logic。
- 集成测试：完整诊断链路。
- 回归样例：P0300/P0301/P0171/P0420/P0128，以及有埋点/传感器异常的 VIN 案例。

## 15. 验收标准

- 可以通过 API 提交车辆故障诊断任务并返回 `task_id`。
- 只传 VIN 时，系统能自动拉取车辆画像、DTC 历史、传感器和埋点数据。
- 后台任务能完成 LangGraph 流程并返回结构化结果。
- 至少 5 类报告被生成并保存在结果中：VIN、症状、DTC、Telemetry、Knowledge。
- 工具调用不会无限循环，达到阈值会强制进入下一节点。
- 缺失 VIN 或 DTC 时仍能基于症状进行有限诊断。
- 高风险故障会输出明确的停止驾驶或拖车建议。
- 可通过 outcome API 把确认维修结果写入 memory。

## 16. 待确认问题

1. VIN 数据库类型最终由部署环境决定；MVP adapter 先按 MongoDB 文档模型实现。
2. 传感器时序量较大时，建议独立迁移到 ClickHouse 或 TimescaleDB。
3. 车辆领域 MVP 先覆盖燃油车通用 DTC；混动和电动车保留字段和规则入口。
4. API MVP 先不接登录体系，保留 `user_id` 可选字段。
