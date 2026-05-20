# Vehicle Fault Diagnosis Agent 简化设计

当前项目按聊天记录中的分工收敛为 4 个前置 Agent + 1 个最终 Summary Agent：

1. `vin_context`：历史故障和维修记录 Agent。根据 VIN 通过确定性 Skill 查询车辆档案、历史 DTC、维修/保养记录和里程。
2. `symptom`：用户主观描述 Agent。只做语义标准化，输出疑似故障点、排查方向和可选联网搜索词，不查询 RAG/案例库。
3. `dtc`：DTC Agent。根据上游排查方向定向读取/解释故障码、组合模式、冻结帧和数据流事实，只提交客观证据，不做最终交叉验证。
4. `knowledge`：RAG 知识库 Agent。接收主观假设和 DTC 客观数据，检索车辆手册、技术资料和历史案例，只提供资料参考。
5. `Summary Agent`：汇总/辩论 Agent。统一融合历史记录、主观假设、DTC 证据和 RAG 参考，完成最终交叉验证、冲突仲裁和诊断输出。

`experience` 仍作为可选兼容 Agent 保留，用于查询已通过 outcome 确认的维修记忆；默认流程不再启用。

## LangGraph 流程

```text
START
  -> VIN Context Analyst -> tools_vin_context? -> Msg Clear VIN Context
  -> Symptom Analyst -> Msg Clear Symptom
  -> Diagnostic Code Analyst -> tools_dtc? -> Msg Clear Diagnostic Code
  -> Knowledge Analyst -> tools_knowledge? -> Msg Clear Knowledge
  -> Summary Agent
  -> END
```

默认顺序：

```text
vin_context -> symptom -> dtc -> knowledge -> summary
```

支持选择：

```text
vin_context, symptom, dtc, knowledge, experience
```

## 工具边界

数据库和底层数据查询都通过 Skill/Tool 封装，LLM 不直接生成 SQL、CAN 指令或数据库查询语句。

- `get_vehicle_profile_by_vin`
- `get_dtc_history_by_vin`
- `get_maintenance_history_by_vin`
- `lookup_dtc_code`
- `search_dtc_combinations`
- `retrieve_repair_cases`

## 输出边界

- Symptom 输出 `semantic_standardization`、`suspected_fault_points`、`inspection_directions`。
- DTC 输出 `codes`、`lookups`、`combinations`、`freeze_frame` 等客观事实。
- Knowledge 输出 `repair_references` 和 `knowledge_sources`。
- Summary 输出 `summary`、`final_conclusion`、`confidence_score`、`confidence_level`、`ranked_hypotheses`、`debate_notes`、`reasoning_process`、`inspection_plan`。

确认维修结果仍通过 `/tasks/{task_id}/outcome` 写入经验库，避免把未确认的诊断推断污染经验数据。
