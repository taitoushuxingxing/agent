# 车辆故障诊断 Agent 启动文档

本文档说明如何配置并启动 `vehicle_fault_diagnosis_agent` 服务。当前服务默认使用 MongoDB 保存任务、结果、反馈记忆和演示车辆数据，使用 Redis 作为任务队列和限流存储。

## 1. 环境要求

- Python 3.10+
- MongoDB
- Redis
- 可选：OpenAI/DeepSeek/Qwen 等 OpenAI-compatible LLM API Key

进入项目目录：

```powershell
cd E:\aiagentgithubproject\vehicle_fault_diagnosis_agent
```

安装依赖：

```powershell
python -m pip install -e .
```

## 2. 准备配置文件

复制示例配置：

```powershell
copy .env.example .env
```

编辑 `.env`。最少需要确认 MongoDB 和 Redis 配置。

### MongoDB 配置

如果 MongoDB 没有开启认证：

```env
VEHICLE_DIAGNOSIS_MONGO_URI=mongodb://127.0.0.1:27017
VEHICLE_DIAGNOSIS_MONGO_DATABASE=vehicle_diagnosis
```

如果 MongoDB 开启认证，填写带账号密码的 URI：

```env
VEHICLE_DIAGNOSIS_MONGO_URI=mongodb://user:password@127.0.0.1:27017/vehicle_diagnosis?authSource=admin
VEHICLE_DIAGNOSIS_MONGO_DATABASE=vehicle_diagnosis
```

数据源模式：

```env
VEHICLE_DIAGNOSIS_DATA_PROVIDER=auto
```

可选值：

- `auto`：优先读取 MongoDB，失败或查不到时回退到 mock 数据，适合开发和演示。
- `mongo`：强制读取 MongoDB，失败直接报错，适合生产环境。
- `mock`：完全使用内置 mock 数据，不访问 MongoDB，适合无数据库本地调试。

### Redis 配置

```env
VEHICLE_DIAGNOSIS_REDIS_URL=redis://127.0.0.1:6379/0
VEHICLE_DIAGNOSIS_REDIS_QUEUE=vehicle_diagnosis:tasks
```

队列和任务控制：

```env
VEHICLE_DIAGNOSIS_WORKER_CONCURRENCY=2
VEHICLE_DIAGNOSIS_QUEUE_MAX_SIZE=100
VEHICLE_DIAGNOSIS_TASK_TIMEOUT_SECONDS=120
```

限流配置：

```env
VEHICLE_DIAGNOSIS_RATE_LIMIT_WINDOW_SECONDS=60
VEHICLE_DIAGNOSIS_RATE_LIMIT_MAX_REQUESTS=120
```

### LLM 配置

如果暂时不接真实 LLM：

```env
VEHICLE_DIAGNOSIS_LLM_ENABLED=false
```

此时 Planner 会使用 deterministic rule fallback，服务仍可正常诊断。

如果使用 OpenAI-compatible API：

```env
VEHICLE_DIAGNOSIS_LLM_ENABLED=true

VEHICLE_DIAGNOSIS_LLM_QUICK_PROVIDER=openai
VEHICLE_DIAGNOSIS_LLM_QUICK_MODEL=gpt-4o-mini
VEHICLE_DIAGNOSIS_LLM_QUICK_BASE_URL=https://api.openai.com/v1
VEHICLE_DIAGNOSIS_LLM_QUICK_API_KEY_ENV=OPENAI_API_KEY
VEHICLE_DIAGNOSIS_LLM_QUICK_TEMPERATURE=0.2
VEHICLE_DIAGNOSIS_LLM_QUICK_MAX_TOKENS=4000
VEHICLE_DIAGNOSIS_LLM_QUICK_TIMEOUT_SECONDS=60

VEHICLE_DIAGNOSIS_LLM_DEEP_PROVIDER=openai
VEHICLE_DIAGNOSIS_LLM_DEEP_MODEL=gpt-4o
VEHICLE_DIAGNOSIS_LLM_DEEP_BASE_URL=https://api.openai.com/v1
VEHICLE_DIAGNOSIS_LLM_DEEP_API_KEY_ENV=OPENAI_API_KEY
VEHICLE_DIAGNOSIS_LLM_DEEP_TEMPERATURE=0.1
VEHICLE_DIAGNOSIS_LLM_DEEP_MAX_TOKENS=6000
VEHICLE_DIAGNOSIS_LLM_DEEP_TIMEOUT_SECONDS=90

OPENAI_API_KEY=你的_API_KEY
```

DeepSeek 或 Qwen 兼容网关也可以使用同一套字段，把 `BASE_URL`、`MODEL`、`API_KEY_ENV` 和实际 API Key 换掉即可。例如：

```env
VEHICLE_DIAGNOSIS_LLM_DEEP_PROVIDER=deepseek
VEHICLE_DIAGNOSIS_LLM_DEEP_MODEL=deepseek-chat
VEHICLE_DIAGNOSIS_LLM_DEEP_BASE_URL=https://api.deepseek.com/v1
VEHICLE_DIAGNOSIS_LLM_DEEP_API_KEY_ENV=DEEPSEEK_API_KEY
DEEPSEEK_API_KEY=你的_DEEPSEEK_KEY
```

## 3. 检查 MongoDB 和 Redis

检查端口是否连通：

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 27017 -InformationLevel Quiet
Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -InformationLevel Quiet
```

都返回 `True` 说明端口可访问。

如果 MongoDB 开启认证，但 `.env` 中 URI 没有填写账号密码，写入 seed 数据或启动服务时会出现 `requires authentication`。此时需要改成带认证的 MongoDB URI。

## 4. 写入演示数据

确认 `.env` 中 MongoDB 配置正确后，执行：

```powershell
python scripts\seed_mongo_demo_data.py
```

脚本会写入一个演示 VIN：

```text
LFV3A23C0J3000001
```

写入集合包括：

- `vehicle_profiles`
- `vin_dtc_history`
- `vin_maintenance_history`
- `repair_cases`

如果只是想不依赖 MongoDB 演示，可以把 `.env` 改成：

```env
VEHICLE_DIAGNOSIS_DATA_PROVIDER=mock
```

然后跳过 seed 步骤。

## 5. 启动服务

启动 FastAPI：

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

开发时可使用热重载：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
curl http://127.0.0.1:8000/health
```

返回示例：

```json
{"status":"ok","environment":"local"}
```

打开 API 文档：

```text
http://127.0.0.1:8000/docs
```

## 6. 提交诊断任务

PowerShell 示例：

```powershell
$body = @{
  vin = "LFV3A23C0J3000001"
  symptoms = @(
    @{
      name = "rough idle"
      severity = "medium"
    }
  )
  dtc_codes = @("P0301", "P0171")
  parameters = @{
    selected_analysts = @("vin_context", "symptom", "dtc", "knowledge", "experience")
    diagnosis_depth = "standard"
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/vehicle-diagnosis/tasks" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

返回中会包含 `task_id`，例如：

```json
{
  "success": true,
  "data": {
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "status": "queued"
  },
  "message": "diagnosis task queued"
}
```

## 7. 查询状态和结果

查询任务状态：

```powershell
$taskId = "替换为你的task_id"
Invoke-RestMethod "http://127.0.0.1:8000/api/vehicle-diagnosis/tasks/$taskId/status"
```

常见状态：

- `submitted`
- `queued`
- `running`
- `completed`
- `failed`
- `cancel_requested`
- `cancelled`

查询诊断结果：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/vehicle-diagnosis/tasks/$taskId/result"
```

## 8. 取消任务

取消任务：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/vehicle-diagnosis/tasks/$taskId/cancel" `
  -Method Post
```

说明：

- 如果任务还在队列中，会尽量从 Redis 队列移除并标记为 `cancelled`。
- 如果任务已经在运行，会先标记为 `cancel_requested`。
- 当前诊断运行在线程中，不强制杀线程；运行结束后会把最终状态纠正为 `cancelled`。

## 9. 回填维修结果

当真实维修完成后，可以把确认根因写回 memory：

```powershell
$outcome = @{
  confirmed_root_cause = "cylinder 1 ignition coil failure"
  repairs_performed = @("replace cylinder 1 ignition coil", "clear DTC", "road test")
  resolved = $true
  notes = "Idle returned to normal after coil replacement."
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/vehicle-diagnosis/tasks/$taskId/outcome" `
  -Method Post `
  -ContentType "application/json" `
  -Body $outcome
```

该结果会写入 memory backend。默认生产配置下 memory 存在 MongoDB 的 `vehicle_memory_cases` 集合中。

## 10. 测试

运行测试：

```powershell
pytest -q
```

测试使用 SQLite repository 和内存队列注入，不需要真实 MongoDB、Redis 或 LLM。

## 11. 常见问题

### MongoDB 提示 requires authentication

说明 MongoDB 开启了认证。请在 `.env` 中配置带账号密码的 URI：

```env
VEHICLE_DIAGNOSIS_MONGO_URI=mongodb://user:password@127.0.0.1:27017/vehicle_diagnosis?authSource=admin
```

### 想完全跳过 MongoDB

设置：

```env
VEHICLE_DIAGNOSIS_DATA_PROVIDER=mock
```

但注意：服务任务持久化默认仍然使用 MongoDB repository。该设置只控制车辆数据 provider。若要服务本身也不依赖 MongoDB，需要在代码中注入 SQLite repository，当前主要用于测试。

### Redis 连接失败

确认 Redis 正在运行，并且 `.env` 中配置正确：

```env
VEHICLE_DIAGNOSIS_REDIS_URL=redis://127.0.0.1:6379/0
```

### LLM API Key 没配置

如果 `VEHICLE_DIAGNOSIS_LLM_ENABLED=true`，必须配置对应的 API Key 环境变量。比如：

```env
VEHICLE_DIAGNOSIS_LLM_DEEP_API_KEY_ENV=OPENAI_API_KEY
OPENAI_API_KEY=你的_API_KEY
```

如果暂时不用 LLM：

```env
VEHICLE_DIAGNOSIS_LLM_ENABLED=false
```

Planner 会自动使用规则 fallback。
