from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "vehicle_fault_diagnosis_agent_architecture.png"

W, H = 3400, 2450
BG = "#F8FAFC"
INK = "#0F172A"
MUTED = "#475569"
LINE = "#94A3B8"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


F_TITLE = font(54, True)
F_SUB = font(26)
F_GROUP = font(30, True)
F_NODE = font(23, True)
F_SMALL = font(19)
F_TINY = font(17)


def rounded(draw: ImageDraw.ImageDraw, box, fill, outline="#CBD5E1", width=2, radius=28):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text_center(draw: ImageDraw.ImageDraw, box, lines, fnt, fill=INK, spacing=7):
    if isinstance(lines, str):
        lines = lines.split("\n")
    heights = []
    widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=fnt)
        widths.append(bbox[2] - bbox[0])
        heights.append(bbox[3] - bbox[1])
    total_h = sum(heights) + spacing * (len(lines) - 1)
    y = box[1] + ((box[3] - box[1]) - total_h) / 2
    for line, tw, th in zip(lines, widths, heights):
        x = box[0] + ((box[2] - box[0]) - tw) / 2
        draw.text((x, y), line, font=fnt, fill=fill)
        y += th + spacing


def wrapped_lines(text: str, width: int = 18) -> list[str]:
    result: list[str] = []
    for part in text.split("\n"):
        result.extend(wrap(part, width=width, break_long_words=False) or [""])
    return result


def node(draw, x, y, w, h, title, desc="", fill="#FFFFFF", outline="#CBD5E1"):
    box = (x, y, x + w, y + h)
    rounded(draw, box, fill, outline, width=3, radius=22)
    if desc:
        title_box = (x + 18, y + 18, x + w - 18, y + 52)
        text_center(draw, title_box, title, F_NODE)
        desc_lines = wrapped_lines(desc, 20)
        text_center(draw, (x + 18, y + 66, x + w - 18, y + h - 14), desc_lines, F_TINY, MUTED, spacing=4)
    else:
        text_center(draw, box, wrapped_lines(title, 12), F_NODE)
    return box


def group(draw, x, y, w, h, title, fill="#FFFFFF", outline="#CBD5E1"):
    box = (x, y, x + w, y + h)
    rounded(draw, box, fill, outline, width=3, radius=34)
    draw.text((x + 28, y + 18), title, font=F_GROUP, fill=INK)
    return box


def arrow(draw, a, b, color="#64748B", width=4, label: str | None = None):
    ax, ay = a
    bx, by = b
    draw.line((ax, ay, bx, by), fill=color, width=width)
    # arrow head
    import math

    angle = math.atan2(by - ay, bx - ax)
    length = 20
    spread = 0.45
    p1 = (bx - length * math.cos(angle - spread), by - length * math.sin(angle - spread))
    p2 = (bx - length * math.cos(angle + spread), by - length * math.sin(angle + spread))
    draw.polygon([b, p1, p2], fill=color)
    if label:
        mx, my = (ax + bx) / 2, (ay + by) / 2
        bbox = draw.textbbox((0, 0), label, font=F_TINY)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        rounded(draw, (mx - tw / 2 - 12, my - th / 2 - 8, mx + tw / 2 + 12, my + th / 2 + 8), "#FFFFFF", "#CBD5E1", 1, 10)
        draw.text((mx - tw / 2, my - th / 2), label, font=F_TINY, fill=MUTED)


def pill(draw, x, y, text, fill, outline):
    bbox = draw.textbbox((0, 0), text, font=F_TINY)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    box = (x, y, x + tw + 34, y + th + 20)
    rounded(draw, box, fill, outline, width=2, radius=18)
    draw.text((x + 17, y + 10), text, font=F_TINY, fill=INK)
    return box


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw.text((90, 60), "车辆故障诊断 Agent 架构与完整工作流程", font=F_TITLE, fill=INK)
    draw.text(
        (92, 132),
        "FastAPI + Redis Queue + LangGraph Multi-Agent + Tool/Data Provider + Memory Feedback + Fallback",
        font=F_SUB,
        fill=MUTED,
    )

    # Top: API and orchestration
    group(draw, 80, 210, 3240, 430, "1. 请求入口与异步任务编排", "#EFF6FF", "#93C5FD")
    n_user = node(draw, 130, 310, 310, 150, "用户/前端/维修人员", "提交 VIN、症状、DTC、传感器快照\n查询状态、结果、回填维修 outcome", "#FFFFFF", "#60A5FA")
    n_api = node(draw, 540, 310, 300, 150, "FastAPI Router", "POST tasks\nGET status/result\nPOST cancel/outcome", "#DBEAFE", "#2563EB")
    n_schema = node(draw, 940, 310, 290, 150, "Pydantic Schema", "参数校验\n分析师选择\n诊断深度/工具参数", "#FFFFFF", "#60A5FA")
    n_service = node(draw, 1330, 300, 360, 170, "Diagnosis Service", "创建任务 / 入队 / 执行\n进度保存 / 取消 / 超时\nGraph 缓存", "#DBEAFE", "#2563EB")
    n_repo = node(draw, 1810, 300, 310, 170, "Task Repository", "MongoDB 生产存储\nSQLite 测试注入\n保存 state/result", "#FFFFFF", "#60A5FA")
    n_queue = node(draw, 2240, 300, 300, 170, "Redis Task Queue", "RPUSH 入队 / BLPOP 取任务\n队列满返回 503", "#FFEDD5", "#F97316")
    n_worker = node(draw, 2660, 300, 300, 170, "Worker Pool", "并发执行任务\nstream snapshot 保存进度", "#FFEDD5", "#F97316")
    n_status = node(draw, 3000, 320, 250, 130, "状态可观测", "progress\ncurrent_node\ngraph_trace\ntool_errors", "#FFFFFF", "#60A5FA")

    for a, b in [
        (n_user, n_api),
        (n_api, n_schema),
        (n_schema, n_service),
        (n_service, n_repo),
        (n_service, n_queue),
        (n_queue, n_worker),
        (n_worker, n_status),
    ]:
        arrow(draw, ((a[2]), (a[1] + a[3]) / 2), (b[0], (b[1] + b[3]) / 2))
    arrow(draw, (n_repo[2], n_repo[3] - 38), (n_service[2], n_service[3] - 38), "#64748B", 3, "save/load")

    # Middle: LangGraph
    group(draw, 80, 700, 3240, 900, "2. LangGraph 多 Agent 诊断核心", "#ECFDF5", "#6EE7B7")
    n_state = node(draw, 130, 810, 250, 150, "Initial State", "diagnosis_id / vin\nsymptoms / DTC\nmessages\ntrace", "#FFFFFF", "#10B981")
    n_vin = node(draw, 470, 800, 260, 170, "VIN Context", "车辆档案\n历史 DTC\n维护记录", "#D1FAE5", "#059669")
    n_sym = node(draw, 820, 800, 260, 170, "Symptom", "症状数量\n严重程度\n主诉与案例", "#D1FAE5", "#059669")
    n_dtc = node(draw, 1170, 800, 260, 170, "DTC Analyst", "故障码解释\n组合模式\n历史+当前 DTC", "#D1FAE5", "#059669")
    n_tel = node(draw, 1520, 800, 270, 170, "Telemetry", "传感器快照\n时序信号\n事件与规则", "#D1FAE5", "#059669")
    n_know = node(draw, 1880, 800, 270, 170, "Knowledge", "维修案例\n知识库命中\n相似经验", "#D1FAE5", "#059669")
    n_hyp = node(draw, 2250, 790, 270, 135, "Hypothesis", "提出可能根因\n点火 / 燃油\n漏气 / 压缩", "#F0FDF4", "#22C55E")
    n_counter = node(draw, 2250, 990, 270, 135, "Counterfactual", "反证与风险提醒\n避免只凭 DTC 换件", "#F0FDF4", "#22C55E")
    n_plan = node(draw, 2640, 800, 270, 170, "Diagnostic Planner", "融合报告\n辩论记录\n相似 Memory\n输出检查计划", "#BBF7D0", "#16A34A")
    n_repair = node(draw, 3000, 730, 250, 130, "Repair Advisor", "维修建议\n费用区间\n驾驶建议", "#D1FAE5", "#059669")
    n_safe = node(draw, 3000, 930, 250, 130, "Safety Analyst", "安全风险\n可驾驶性\n停车条件", "#D1FAE5", "#059669")
    n_judge = node(draw, 3000, 1180, 250, 150, "Safety Judge", "生成最终\nstructured_result", "#99F6E4", "#0D9488")

    sequence = [n_state, n_vin, n_sym, n_dtc, n_tel, n_know, n_hyp]
    for a, b in zip(sequence, sequence[1:]):
        arrow(draw, (a[2], (a[1] + a[3]) / 2), (b[0], (b[1] + b[3]) / 2))
    arrow(draw, (n_hyp[1] + 1600, 925), (n_counter[0] + 135, n_counter[1]), "#059669", 4, "debate")
    arrow(draw, (n_counter[0] + 135, n_counter[3]), (n_hyp[0] + 135, n_hyp[3]), "#059669", 4)
    arrow(draw, (n_hyp[2], (n_hyp[1] + n_hyp[3]) / 2), (n_plan[0], (n_plan[1] + n_plan[3]) / 2), "#059669", 4, "max rounds")
    arrow(draw, (n_plan[2], 850), (n_repair[0], (n_repair[1] + n_repair[3]) / 2))
    arrow(draw, (n_repair[0] + 125, n_repair[3]), (n_safe[0] + 125, n_safe[1]))
    arrow(draw, (n_safe[0] + 125, n_safe[3]), (n_judge[0] + 125, n_judge[1]), label="judge")
    arrow(draw, (n_safe[0], 995), (n_repair[0], 795), "#059669", 3, "safety loop")

    # Tool strip under analyst nodes
    tool_y = 1220
    tools = [
        (470, "tools_vin_context", "VIN profile\nDTC history\nmaintenance"),
        (820, "tools_symptom", "repair cases"),
        (1170, "tools_dtc", "DTC dictionary\nDTC combinations"),
        (1520, "tools_telemetry", "snapshot / timeseries\nevents / rule engine"),
        (1880, "tools_knowledge", "repair cases\nknowledge source"),
    ]
    for x, title, desc in tools:
        box = node(draw, x, tool_y, 260 if x < 1520 else 270, 150, title, desc, "#FFFFFF", "#94A3B8")
        arrow(draw, (box[0] + (box[2] - box[0]) / 2, box[1]), (box[0] + (box[2] - box[0]) / 2, 970), "#94A3B8", 3)
        arrow(draw, (box[0] + (box[2] - box[0]) / 2 + 18, 970), (box[0] + (box[2] - box[0]) / 2 + 18, box[1]), "#94A3B8", 3)

    # Bottom: data, memory, fallback, result
    group(draw, 80, 1660, 1050, 620, "3. 工具与数据源", "#F8FAFC", "#CBD5E1")
    node(draw, 130, 1760, 280, 120, "Tool Executor", "max_tool_calls\nretry + timeout\ntool_errors 不阻断流程", "#FEFCE8", "#CA8A04")
    node(draw, 460, 1760, 280, 120, "Data Provider Mode", "auto: Mongo 优先\nmongo: 强制真实库\nmock: 演示数据", "#FEF3C7", "#D97706")
    node(draw, 790, 1760, 280, 120, "Provider Fallback", "Mongo 不可用或无数据\n-> mock/local 数据", "#FEFCE8", "#CA8A04")
    data_nodes = [
        ("vehicle_profiles", 130, 1940),
        ("vin_dtc_history", 370, 1940),
        ("sensor_snapshots", 610, 1940),
        ("sensor_timeseries", 850, 1940),
        ("event_logs", 130, 2080),
        ("repair_cases", 370, 2080),
        ("local_dtc", 610, 2080),
        ("telemetry_rules", 850, 2080),
    ]
    for label, x, y in data_nodes:
        node(draw, x, y, 210, 90, label, "", "#FFFFFF", "#CBD5E1")

    group(draw, 1190, 1660, 930, 620, "4. Memory 反馈闭环", "#FDF2F8", "#F9A8D4")
    n_outcome = node(draw, 1240, 1760, 260, 130, "Outcome 回填", "真实根因\n维修动作\n是否解决", "#FFFFFF", "#DB2777")
    n_mem = node(draw, 1570, 1760, 260, 130, "Memory Store", "Mongo / SQLite / InMemory\nvehicle_memory_cases", "#FCE7F3", "#DB2777")
    n_search = node(draw, 1570, 1990, 260, 130, "相似案例检索", "token overlap\n返回 top 3 memories", "#FFFFFF", "#DB2777")
    n_use = node(draw, 1240, 1990, 260, 130, "Planner 使用", "进入 similar_memory_cases\n辅助置信度与排序", "#FCE7F3", "#DB2777")
    arrow(draw, (n_outcome[2], 1825), (n_mem[0], 1825), "#DB2777")
    arrow(draw, (n_mem[0] + 130, n_mem[3]), (n_search[0] + 130, n_search[1]), "#DB2777")
    arrow(draw, (n_search[0], 2055), (n_use[2], 2055), "#DB2777")
    arrow(draw, (n_use[0] + 130, n_use[1]), (n_outcome[0] + 130, n_outcome[3]), "#DB2777", 3)

    group(draw, 2180, 1660, 1140, 620, "5. 稳定性与最终输出", "#F0FDFA", "#5EEAD4")
    node(draw, 2230, 1760, 270, 125, "LLM Fallback", "工具决策失败\n-> 默认策略\nPlanner 失败\n-> 规则计划", "#FEFCE8", "#CA8A04")
    node(draw, 2560, 1760, 270, 125, "任务容错", "超时 -> failed\n取消 -> cancelled\n重启后重新入队", "#FEFCE8", "#CA8A04")
    node(draw, 2890, 1760, 270, 125, "可观测性", "x-request-id\ngraph_trace\nanalyst_conclusions", "#FFFFFF", "#0D9488")
    n_result = node(draw, 2360, 1980, 640, 170, "structured_result", "summary / safety_level / drivability\nconfidence_score / ranked_hypotheses\ninspection_plan / repair_advice\ntelemetry_findings / reports / trace / errors", "#CCFBF1", "#0D9488")
    arrow(draw, (n_judge[0] + 125, n_judge[3]), (n_result[0] + 320, n_result[1]), "#0D9488", 5, "final result")

    # Legend
    legend_y = 2320
    pill(draw, 90, legend_y, "API / Service", "#DBEAFE", "#2563EB")
    pill(draw, 330, legend_y, "Queue / Worker", "#FFEDD5", "#F97316")
    pill(draw, 590, legend_y, "Agent Node", "#D1FAE5", "#059669")
    pill(draw, 820, legend_y, "Tool / Provider", "#FFFFFF", "#94A3B8")
    pill(draw, 1080, legend_y, "Memory", "#FCE7F3", "#DB2777")
    pill(draw, 1280, legend_y, "Fallback / Risk", "#FEFCE8", "#CA8A04")

    draw.text((2380, 2324), "Output: vehicle_fault_diagnosis_agent_architecture.png", font=F_TINY, fill=MUTED)

    img.save(OUT, "PNG", optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
