# Vehicle Fault Diagnosis Agent

FastAPI + LangGraph backend for vehicle fault diagnosis. The project follows the same high-level pattern as TradingAgents-CN: shared state, analyst nodes, tool/data providers, researcher debate, planner, safety judge, and memory feedback.

## Production-Oriented Features

- FastAPI service with `/health` and OpenAPI docs.
- LangGraph multi-agent diagnosis workflow.
- Configurable analysts: `vin_context`, `symptom`, `dtc`, `telemetry`, `knowledge`.
- MongoDB persistence for tasks, results, outcomes, and memory cases.
- Selectable vehicle data provider mode: `auto`, `mongo`, or `mock`.
- Redis-backed async task queue with worker concurrency control.
- Redis-backed request rate limiting.
- Per-task execution timeout.
- JSON structured logs and `x-request-id` request tracing.
- Planner supports optional LLM evidence synthesis with deterministic rule fallback.
- OpenAI-compatible LLM client for OpenAI, DeepSeek, Qwen-compatible gateways, and similar `/chat/completions` APIs.
- Dataflow/tool adapters for VIN, DTC, sensors, events, and repair cases.

## Install

```bash
pip install -e .
```

You also need MongoDB and Redis running for the default service configuration.

## Configuration

中文启动与配置说明见 [STARTUP_CN.md](STARTUP_CN.md).

Copy the example environment file and fill in your local values:

```powershell
copy .env.example .env
```

The application automatically loads `.env` from the project root. Real environment variables still take precedence over `.env` values.

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Main Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `VEHICLE_DIAGNOSIS_APP_NAME` | `Vehicle Fault Diagnosis Agent` | FastAPI app name |
| `VEHICLE_DIAGNOSIS_ENV` | `local` | Runtime environment |
| `VEHICLE_DIAGNOSIS_MONGO_URI` | `mongodb://127.0.0.1:27017` | MongoDB URI |
| `VEHICLE_DIAGNOSIS_MONGO_DATABASE` | `vehicle_diagnosis` | MongoDB database |
| `VEHICLE_DIAGNOSIS_DATA_PROVIDER` | `auto` | `auto`, `mongo`, or `mock` |
| `VEHICLE_DIAGNOSIS_REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis URL |
| `VEHICLE_DIAGNOSIS_REDIS_QUEUE` | `vehicle_diagnosis:tasks` | Redis queue key |
| `VEHICLE_DIAGNOSIS_WORKER_CONCURRENCY` | `2` | Background worker count |
| `VEHICLE_DIAGNOSIS_QUEUE_MAX_SIZE` | `100` | Max Redis queue length |
| `VEHICLE_DIAGNOSIS_TASK_TIMEOUT_SECONDS` | `120` | Per-task timeout |
| `VEHICLE_DIAGNOSIS_RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window |
| `VEHICLE_DIAGNOSIS_RATE_LIMIT_MAX_REQUESTS` | `120` | Max requests per window |
| `VEHICLE_DIAGNOSIS_CORS_ORIGINS` | `*` | Comma-separated CORS origins |
| `VEHICLE_DIAGNOSIS_LOG_LEVEL` | `INFO` | Structured log level |
| `VEHICLE_DIAGNOSIS_LLM_CONFIG_PATH` | `./config/llm_config.json` | LLM config path |
| `VEHICLE_DIAGNOSIS_LLM_ENABLED` | `false` | Enable LLM runtime config |
| `VEHICLE_DIAGNOSIS_LLM_QUICK_MODEL` | `gpt-4o-mini` | Quick planner/reasoning model |
| `VEHICLE_DIAGNOSIS_LLM_DEEP_MODEL` | `gpt-4o` | Deep planner/reasoning model |
| `OPENAI_API_KEY` | empty | OpenAI API key if using OpenAI-compatible models |

## LLM Config

You can configure LLMs directly in `.env`, which is usually easiest:

```env
VEHICLE_DIAGNOSIS_LLM_ENABLED=true
VEHICLE_DIAGNOSIS_LLM_QUICK_PROVIDER=openai
VEHICLE_DIAGNOSIS_LLM_QUICK_MODEL=gpt-4o-mini
VEHICLE_DIAGNOSIS_LLM_QUICK_BASE_URL=https://api.openai.com/v1
VEHICLE_DIAGNOSIS_LLM_QUICK_API_KEY_ENV=OPENAI_API_KEY
VEHICLE_DIAGNOSIS_LLM_DEEP_PROVIDER=openai
VEHICLE_DIAGNOSIS_LLM_DEEP_MODEL=gpt-4o
VEHICLE_DIAGNOSIS_LLM_DEEP_API_KEY_ENV=OPENAI_API_KEY
OPENAI_API_KEY=your_key_here
```

Or keep model details in JSON:

```bash
copy config\llm_config.example.json config\llm_config.json
```

Environment variables override JSON values when both are present.

For MongoDB with authentication, put the full URI in `.env`:

```env
VEHICLE_DIAGNOSIS_MONGO_URI=mongodb://user:password@127.0.0.1:27017/vehicle_diagnosis?authSource=admin
VEHICLE_DIAGNOSIS_MONGO_DATABASE=vehicle_diagnosis
```

## API Example

Submit a diagnosis task:

```bash
curl -X POST http://127.0.0.1:8000/api/vehicle-diagnosis/tasks ^
  -H "Content-Type: application/json" ^
  -d "{\"vin\":\"LFV3A23C0J3000001\",\"symptoms\":[{\"name\":\"rough idle\",\"severity\":\"medium\"}],\"dtc_codes\":[\"P0301\",\"P0171\"],\"parameters\":{\"selected_analysts\":[\"vin_context\",\"symptom\",\"dtc\",\"telemetry\",\"knowledge\"],\"diagnosis_depth\":\"standard\"}}"
```

Query status:

```bash
curl http://127.0.0.1:8000/api/vehicle-diagnosis/tasks/{task_id}/status
```

Query result:

```bash
curl http://127.0.0.1:8000/api/vehicle-diagnosis/tasks/{task_id}/result
```

Submit confirmed repair outcome:

```bash
curl -X POST http://127.0.0.1:8000/api/vehicle-diagnosis/tasks/{task_id}/outcome ^
  -H "Content-Type: application/json" ^
  -d "{\"confirmed_root_cause\":\"cylinder 1 ignition coil failure\",\"repairs_performed\":[\"replace ignition coil\"],\"resolved\":true}"
```

Cancel a queued or running task:

```bash
curl -X POST http://127.0.0.1:8000/api/vehicle-diagnosis/tasks/{task_id}/cancel
```

Queued tasks are removed from the queue when possible. Running tasks are marked `cancel_requested`; because diagnosis execution runs in a worker thread, it is not force-killed mid-call, but the final status is reconciled to `cancelled`.

## Tests

Tests inject SQLite and an in-memory queue so they do not require MongoDB or Redis:

```bash
pytest -q
```

## Remaining Production Work

- Add authentication and user isolation.
- Replace mock vehicle data providers with real VIN/OBD/telemetry systems.
- Add concrete LLM client factory and token/cost accounting.
- Add Prometheus metrics and alerting.
- Add Docker Compose or Kubernetes manifests for deployment.
