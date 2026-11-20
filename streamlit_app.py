# -*- coding: utf-8 -*-
"""BOPET 文献问答 + 生产方案自循环的 Streamlit 前端。

本地运行：
    streamlit run streamlit_app.py

Streamlit Cloud：
- 在 Secrets 中配置 SILICONFLOW_API_KEY；
- 确保 data/database/bopet.db 已随仓库上传；
- 依赖见 requirements.txt。
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config import CONFIG
from qa_agent import (
    QAAgent,
    QAError,
    check_database,
    fallback_keywords,
    keep_measurement_for_parameter,
    material_note,
)
from plan_agent import PlanAgent, _rule_plan
from production_model import (
    ASSUMPTIONS,
    BASELINE,
    MEASURE_BY_ID,
    PRODUCTS,
    baseline_result,
    enforce_constraints,
    evaluate_plan,
    format_kpi_row,
    format_plan,
)
from system_demo import best_increment, build_guidance, collect_evidence
from tools.evidence_retriever import DB_PATH
import control_adapter

# Allow the same keys to come from .streamlit/secrets.toml without hard-coding
# them. Environment variables still win; this only fills missing values.
for _secret_key in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL",
                    "LLM_API_KEY", "SILICONFLOW_API_KEY",
                    "INTERNLM_API_KEY", "INTERNLM_BASE_URL", "INTERNLM_MODEL",
                    "SHUSHENG_API_KEY", "LLM_TIMEOUT", "LLM_MAX_RETRIES"):
    try:
        if _secret_key in st.secrets:
            os.environ.setdefault(_secret_key, str(st.secrets[_secret_key]))
    except Exception:
        pass

from agents.controller import AgentController
from agents.providers import get_provider
from core.constraints import ConstraintEngine
from core.physics import FORMULAS
from core.schemas import CandidatePlan, ConstraintType
from optimizers.adaptive_search import AdaptiveSearch
from scenarios.benchmark import BenchmarkScenario
from scenarios.bopet import BOPET_BASELINE, BOPET_VARIABLES
from scenarios.bopet_measures import BOPETMeasureScenario
from scenarios.bopet_process import BOPETProcessScenario
from services.optimization_engine import EngineConfig, OptimizationEngine
from services.evidence_catalog import catalog_stats, load_records
from ui.navigation import render_sidebar as render_product_sidebar
from ui.pages import constraints as constraints_page
from ui.pages import evaluation as evaluation_page
from ui.pages import evidence as evidence_page
from ui.pages import optimization as optimization_page
from ui.pages import overview as overview_page
from ui.pages import review as review_page
from ui.pages import settings as settings_page
from ui.pages import validation as validation_page
from ui.theme import inject_styles


# =========================================================
# 页面配置与密钥
# =========================================================

st.set_page_config(
    page_title="BOPET Intelligence",
    page_icon=":material/analytics:",
    layout="wide",
)

inject_styles()


def load_api_key():
    """优先环境变量，其次 Streamlit Secrets，最后返回空。"""

    key = (os.getenv("INTERNLM_API_KEY") or os.getenv("LLM_API_KEY")
           or os.getenv("SILICONFLOW_API_KEY"))

    if key:
        return key

    try:
        key = (st.secrets.get("INTERNLM_API_KEY") or st.secrets.get("LLM_API_KEY")
               or st.secrets.get("SILICONFLOW_API_KEY"))
    except Exception:
        key = None

    if key:
        os.environ["LLM_API_KEY"] = str(key)

    return str(key) if key else ""


API_KEY = load_api_key()


@st.cache_data(show_spinner=False)
def db_snapshot():
    return check_database()


@st.cache_resource(show_spinner=False)
def qa_agent():
    return QAAgent(CONFIG)


@st.cache_resource(show_spinner=False)
def plan_agent():
    return PlanAgent(CONFIG)


# =========================================================
# 侧边栏
# =========================================================

def render_sidebar():
    with st.sidebar:
        st.title("🎞️ BOPET AI Demo")
        st.caption("文献问答 + 方案闭环 + 受控写入（演示）")

        status = db_snapshot()
        st.divider()
        st.subheader("数据库")
        st.caption(f"SQLite：{status['path']}")

        if status.get("exists") and status.get("tables"):
            st.success("数据库已连接")
            for table, count in status["tables"].items():
                st.caption(f"{table}：{count:,} 条")
        else:
            st.error("数据库未找到或表为空")
            st.caption("请确认 data/database/bopet.db 已上传。")

        st.divider()
        st.subheader("Qwen")
        if API_KEY:
            st.success("API Key 已配置")
        else:
            st.warning("未配置 API Key")
            st.caption(
                "本地：设置环境变量 SILICONFLOW_API_KEY；"
                "云端：在 Streamlit Secrets 中添加同名项。"
            )

        st.divider()
        st.caption(
            "数据边界：文献库来自 PDF 抽取；生产反馈为竞赛基线"
            "下的工程估算，不是企业真实产线数据。"
            "受控写入为本地演示日志，不连接真实 PLC。"
        )


# =========================================================
# 文献问答
# =========================================================

def render_qa_result(result):
    question = result.get("question", "")
    keywords = result.get("keywords") or []
    evidence = result.get("evidence") or []
    answer = result.get("answer") or ""

    st.markdown(f"#### 问题：{question}")

    if keywords:
        st.markdown(
            "**检索关键词：** "
            + " ".join(f"`{keyword}`" for keyword in keywords)
        )

    if answer:
        heading = (
            "### AI 回答"
            if result.get("answered_by_model")
            else "### 检索结果"
        )
        st.markdown(heading)
        st.markdown(answer)

    if not evidence:
        st.info("当前数据库未检索到相关证据。")
        return

    st.markdown(f"### 检索证据（{len(evidence)} 条）")

    for index, item in enumerate(evidence, 1):

        page = item.get("page")
        page_text = f"P.{page}" if page is not None else "页码缺失"
        source = item.get("evidence_source") or "未知来源"

        with st.expander(
            f"证据 {index}｜论文 {item.get('paper_id')}｜{page_text}｜{source}",
            expanded=index <= 2,
        ):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{item.get('title') or '题名缺失'}**")
            c2.metric("检索分数", item.get("retrieval_score") or 0)

            st.caption(
                f"主题：{item.get('topic') or '—'} ｜ "
                f"数据类型：{item.get('data_type') or '—'} ｜ "
                f"材料初判：{item.get('material_candidate') or '—'}"
            )

            st.markdown(
                f"**参数：** {item.get('parameter_type') or '未识别'} ｜ "
                f"**测量值：** "
                + (
                    "、".join(item.get("measurement") or [])
                    or "未自动提取"
                )
            )

            note = material_note(item.get("material_candidate"))
            if "非 BOPET" in note or "待核实" in note:
                st.warning(note)

            if item.get("target_parameter_match") is False:
                st.caption("目标参数匹配：否（该数值可能不是问题所问参数）")

            st.code(item.get("original_text") or "", language=None)

    rows = []

    for item in evidence:

        if item.get("target_parameter_match") is not True:
            continue

        values = [
            value for value in item.get("measurement") or []
            if keep_measurement_for_parameter(
                value, item.get("parameter_type")
            )
        ]

        if not values:
            continue

        rows.append({
            "论文编号": item.get("paper_id"),
            "页码": item.get("page"),
            "参数": item.get("parameter_type"),
            "数值": "、".join(values),
            "材料初判": item.get("material_candidate"),
            "证据来源": item.get("evidence_source"),
        })

    if rows:
        st.markdown("### 程序汇总（规则提取，未经模型改写）")
        st.dataframe(rows, hide_index=True, width="stretch")

    st.markdown("### 文献来源")
    st.dataframe(
        [
            {
                "证据": f"证据 {index}",
                "论文编号": item.get("paper_id"),
                "页码": item.get("page"),
                "来源": item.get("evidence_source"),
            }
            for index, item in enumerate(evidence, 1)
        ],
        hide_index=True,
        width="stretch",
    )


def render_qa_tab():
    st.subheader("文献数据库问答")
    st.caption(
        "Qwen 理解问题 → 生成检索关键词 → 查询本地 SQLite → "
        "把真实证据交给 Qwen → 输出带论文编号和页码的回答。"
    )

    examples = [
        "有没有关于拉伸温度的实验数据？",
        "PET 薄膜的热收缩率是多少？",
        "有没有关于收卷张力的研究？",
    ]

    st.caption("示例：" + " ｜ ".join(examples))

    with st.form("qa_form"):
        question = st.text_area(
            "输入问题",
            key="qa_question",
            height=90,
            placeholder="例如：有没有关于薄膜拉伸温度的实验数据？",
        )

        only_retrieval = st.checkbox(
            "仅检索数据库（不调用 Qwen）",
            value=not bool(API_KEY),
            help="不调用模型时，只展示 SQLite 检索到的原始证据。",
        )

        submitted = st.form_submit_button(
            "开始问答",
            type="primary",
            width="stretch",
        )

    if submitted:

        if not question.strip():
            st.warning("请输入问题。")
            return

        with st.status("正在处理...", expanded=True) as status:

            try:
                agent = qa_agent()

                if only_retrieval:
                    keywords = fallback_keywords(question)
                    st.write("系统：检索关键词：" + "、".join(keywords))
                    st.write("系统：正在查询 SQLite 数据库...")
                    evidence = agent.retrieve(keywords)
                    result = {
                        "question": question.strip(),
                        "keywords": keywords,
                        "evidence": evidence,
                        "answer": "（仅检索模式：未调用 Qwen 生成回答）",
                        "answered_by_model": False,
                    }
                else:
                    result = agent.ask(
                        question.strip(),
                        on_step=lambda message: st.write("系统：" + message),
                    )

                st.session_state["qa_result"] = result
                status.update(label="完成", state="complete")

            except QAError as exc:
                st.session_state["qa_result"] = None
                status.update(label="失败", state="error")
                st.error(f"流程失败（{exc.step}）：{exc.message}")

            except Exception as exc:
                st.session_state["qa_result"] = None
                status.update(label="失败", state="error")
                st.error(f"未预期错误：{type(exc).__name__}: {exc}")

    result = st.session_state.get("qa_result")

    if result:
        st.divider()
        render_qa_result(result)


# =========================================================
# 方案自循环
# =========================================================

def execute_loop(rounds, use_llm, on_round):
    """运行方案-反馈闭环，返回 baseline/history/best/evidence。"""

    baseline = baseline_result()
    evidence = collect_evidence()
    agent = plan_agent()

    history = []
    best = baseline
    no_improvement = 0

    for round_index in range(1, rounds + 1):

        if use_llm:
            plan, info = agent.propose(
                round_index,
                history,
                evidence,
                best if best["measures"] else None,
            )
        else:
            plan, _ = enforce_constraints(
                _rule_plan(round_index, history)
            )
            info = {"source": "rule", "warning": None}

        action = plan.get("action", "explore")

        if action == "stop":
            on_round({
                "round": round_index,
                "stop": True,
                "reason": plan.get("reason", ""),
            })
            break

        result = evaluate_plan(plan)

        # 与命令行版一致的局部搜索保护
        if (
            use_llm
            and round_index > 1
            and result["objective"] <= best["objective"]
        ):
            guard_plan, guard_result = best_increment(best)

            if guard_plan and guard_result["objective"] > result["objective"]:
                added = sorted(
                    set(guard_plan["measures"]) - set(best["measures"])
                )
                guard_plan["reason"] = (
                    "在当前最优方案上追加 "
                    + "、".join(added)
                    + "，单措施局部搜索反馈更优。"
                )
                plan = guard_plan
                result = guard_result
                info = {
                    "source": "rule_guard",
                    "warning": "Qwen 方案未带来改善，已用单措施局部搜索补齐",
                }

        plan_text = format_plan(plan)

        history.append({
            "round": round_index,
            "plan": plan,
            "measures": plan.get("measures", {}),
            "plan_text": plan_text,
            "result": result,
            "objective": result["objective"],
            "source": info.get("source"),
            "reason": plan.get("reason", ""),
            "warning": info.get("warning"),
        })

        improved = result["objective"] > best["objective"]

        if improved:
            best = result
            no_improvement = 0
        else:
            no_improvement += 1

        on_round({
            "round": round_index,
            "stop": False,
            "plan_text": plan_text,
            "objective": result["objective"],
            "result": result,
            "improved": improved,
        })

        if (
            len(history) >= 2
            and plan["measures"] == history[-2]["measures"]
            and result["objective"] <= history[-2]["objective"]
        ):
            break

        if round_index >= 2 and no_improvement >= 2:
            break

    return baseline, history, best, evidence


def render_plan_result(data):
    baseline = data["baseline"]
    history = data["history"]
    best = data["best"]
    report = data["report"]

    st.divider()
    st.markdown("### 最优方案")
    st.info(format_plan(best["plan"]))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "合格产量",
        f"{best['qualified_t']:.1f} t",
        f"{best['qualified_t'] - baseline['qualified_t']:+.1f} t",
    )
    c2.metric(
        "交付率",
        f"{best['demand_fill'] * 100:.1f}%",
        f"{(best['demand_fill'] - baseline['demand_fill']) * 100:+.1f} pp",
    )
    c3.metric(
        "月度贡献",
        f"{best['contribution']:,.0f} 元",
        f"{best['monthly_gain']:+,.0f} 元",
    )
    c4.metric(
        "投资 / 回收期",
        f"{best['capex_wan']:.0f} 万",
        (
            f"{best['payback_months']:.1f} 个月"
            if best["payback_months"]
            else "未计算"
        ),
    )

    st.markdown("### 指标对比")

    rows = []
    specs = [
        ("合格产量 (t)", "qualified_t", 1),
        ("总产量 (t)", "output_t", 1),
        ("交付率", "demand_fill", 4),
        ("换型次数", "changeover_count", 0),
        ("换型损失 (h)", "transition_h", 1),
        ("单位成本 (元/t)", "unit_cost", 0),
        ("月度贡献 (元)", "contribution", 0),
        ("目标值 (元)", "objective", 0),
    ]

    for label, key, digits in specs:

        base_value = baseline.get(key)
        best_value = best.get(key)

        if base_value is None or best_value is None:
            continue

        if key == "demand_fill":
            base_text = f"{base_value * 100:.1f}%"
            best_text = f"{best_value * 100:.1f}%"
            delta_text = f"{(best_value - base_value) * 100:+.1f} pp"
        else:
            base_text = f"{base_value:,.{digits}f}"
            best_text = f"{best_value:,.{digits}f}"
            delta_text = f"{best_value - base_value:+,.{digits}f}"

        rows.append({
            "指标": label,
            "基线": base_text,
            "最优方案": best_text,
            "变化": delta_text,
        })

    st.dataframe(rows, hide_index=True, width="stretch")

    st.markdown("### 产品结构对比")

    base_products = {
        item["id"]: item for item in baseline.get("by_product", [])
    }
    best_products = {
        item["id"]: item for item in best.get("by_product", [])
    }

    product_rows = []

    for product in PRODUCTS:

        product_id = product["id"]
        base_p = base_products.get(product_id, {})
        best_p = best_products.get(product_id, {})

        product_rows.append({
            "产品": f"{product_id} {product['name']}",
            "厚度": product["thickness"],
            "需求 (t)": product["demand_t"],
            "基线合格 (t)": base_p.get("qualified_t"),
            "最优合格 (t)": best_p.get("qualified_t"),
            "交付率": f"{best_p.get('demand_fill', 0) * 100:.1f}%",
        })

    st.dataframe(product_rows, hide_index=True, width="stretch")

    st.markdown("### 迭代轨迹")

    st.dataframe(
        [
            {
                "轮次": item["round"],
                "方案": item["plan_text"],
                "投资 (万)": item["result"]["capex_wan"],
                "合格 (t)": item["result"]["qualified_t"],
                "交付率": f"{item['result']['demand_fill'] * 100:.1f}%",
                "目标值": f"{item['objective']:,.0f}",
                "来源": item["source"],
            }
            for item in history
        ],
        hide_index=True,
        width="stretch",
    )

    st.markdown("### 方案指导摘要")
    st.markdown(build_guidance(best, baseline))

    if best.get("warnings"):
        st.caption("约束处理：" + "；".join(best["warnings"]))

    st.download_button(
        "下载 JSON 报告",
        data=json.dumps(report, ensure_ascii=False, indent=2),
        file_name=(
            "bopet_plan_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".json"
        ),
        mime="application/json",
        width="stretch",
    )


def render_plan_tab():
    st.subheader("生产系统方案自循环")
    st.caption(
        "Qwen 选择措施组合 → 工程模型反馈产量/质量/成本 → "
        "历史反馈回传 → 增量调整或停止。"
    )

    baseline = baseline_result()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("基线合格产量", f"{baseline['qualified_t']:.0f} t")
    c2.metric("基线交付率", f"{baseline['demand_fill'] * 100:.1f}%")
    c3.metric("基线换型", f"{baseline['changeover_count']:.0f} 次")
    c4.metric("基线月度贡献", f"{baseline['contribution']:,.0f} 元")

    st.markdown("#### 产品结构")
    st.dataframe(
        [
            {
                "产品": f"{item['id']} {item['name']}",
                "厚度": item["thickness"],
                "需求 (t)": item["demand_t"],
                "单价 (元/t)": item["price_cny_t"],
                "基线合格 (t)": item["qualified_t"],
                "基线交付率": f"{item['qualified_t'] / item['demand_t'] * 100:.1f}%",
            }
            for item in PRODUCTS
        ],
        hide_index=True,
        width="stretch",
    )

    with st.container(border=True):
        cc1, cc2, cc3 = st.columns([1, 1, 2])
        rounds = cc1.slider("最大迭代轮数", 2, 6, 4)
        rule_only = cc2.toggle(
            "规则模式（不调用 Qwen）",
            value=not bool(API_KEY),
        )
        run = cc3.button(
            "运行方案自循环",
            type="primary",
            width="stretch",
            disabled=(not API_KEY and not rule_only),
        )

    if run:

        progress = st.progress(0.0, text="准备中...")

        with st.status("正在运行方案-反馈闭环...", expanded=True) as status:

            def on_round(info):
                if info.get("stop"):
                    status.write(
                        f"第 {info['round']} 轮：模型判断停止 —— "
                        f"{info.get('reason') or '无理由'}"
                    )
                    return

                status.write(
                    f"第 {info['round']} 轮｜{info['plan_text']}｜"
                    f"目标值 {info['objective']:,.0f}"
                )
                progress.progress(
                    min(1.0, info["round"] / rounds),
                    text=f"第 {info['round']} 轮完成",
                )

            try:
                baseline2, history, best, evidence = execute_loop(
                    rounds,
                    not rule_only,
                    on_round,
                )
                status.update(label="闭环完成", state="complete")
                progress.progress(1.0, text="完成")

                report = {
                    "generated_at": datetime.now().isoformat(
                        timespec="seconds"
                    ),
                    "data_mode": "ENGINEERING_ESTIMATE_NOT_REAL_PRODUCTION",
                    "baseline": baseline2,
                    "history": [
                        {
                            "round": item["round"],
                            "plan": item["plan"],
                            "measures": item["measures"],
                            "plan_text": item["plan_text"],
                            "result": item["result"],
                            "objective": item["objective"],
                            "source": item["source"],
                            "reason": item["reason"],
                        }
                        for item in history
                    ],
                    "best": best,
                    "evidence": evidence,
                    "assumptions": ASSUMPTIONS,
                    "constraints": {
                        "budget_wan": BASELINE["budget_wan"],
                        "shutdown_window_h": BASELINE["shutdown_window_h"],
                        "max_total_install_h": ASSUMPTIONS["max_total_install_h"],
                    },
                    "guidance": build_guidance(best, baseline2),
                }

                st.session_state["plan_result"] = {
                    "baseline": baseline2,
                    "history": history,
                    "best": best,
                    "report": report,
                }

            except Exception as exc:
                status.update(label="运行失败", state="error")
                st.error(f"{type(exc).__name__}: {exc}")

    data = st.session_state.get("plan_result")

    if data and data.get("history"):
        render_plan_result(data)
    elif data:
        st.info("没有产生有效方案，请检查基线或模型输出。")


# =========================================================
# 受控写入（演示）
# =========================================================

def render_control_tab():
    st.subheader("受控写入（演示模式）")
    st.warning(
        "DEMO：不连接真实 PLC / OPC UA。写入只落到本地审计日志，"
        "用于演示“预演 → 校验 → 审批 → 写入 → 回滚”。"
        "真实写入还需要标签映射、安全联锁评审、限幅限速和现场标定。"
    )

    state = control_adapter.get_state()
    st.session_state.setdefault("control_version", 0)
    version = int(st.session_state.control_version)
    flash = st.session_state.pop("control_flash", None)
    if flash:
        st.success(flash)

    log_all = control_adapter.get_log(limit=200)
    log_rows = control_adapter.log_rows(limit=30)
    last_write = next(
        (row for row in log_rows if row["动作"] == "写入"),
        None,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("运行模式", "DEMO")
    c2.metric("当前 DR", f"{control_adapter.compute_dr(state):.2f}")
    c3.metric("可写变量", "5 / 24")
    c4.metric(
        "最近写入",
        last_write["记录"] if last_write else "—",
    )
    st.caption(
        "可写：模唇间隙、Choker、冷鼓温度、线速度调整、收卷 taper；"
        "其余 19 项只读或待现场标定。"
    )

    left, right = st.columns([1.05, 1.95], gap="large")

    with left:
        st.markdown("#### ① 设定值")
        st.caption(
            f"当前回退点：模唇 {state['lip_gap_mm']:.2f} mm ｜ "
            f"冷鼓 {state['drum_temp_c']:.1f} °C ｜ "
            f"线速 {state['speed_trim_pct']:+.1f}%"
        )

        with st.form("control_setpoints_form"):
            values = {}
            for key, meta in control_adapter.PARAMETERS.items():
                values[key] = st.number_input(
                    f"{meta['label']}（{meta['unit']}）",
                    min_value=float(meta["min"]),
                    max_value=float(meta["max"]),
                    value=float(state[key]),
                    step=float(meta["step"]),
                    key=f"control_{key}_{version}",
                    help=f"依据：{meta['evidence']}；单次步长 ±{meta['max_delta']:g} {meta['unit']}",
                )
            submitted = st.form_submit_button(
                "预演并校验",
                type="primary",
                width="stretch",
            )

        if submitted:
            current = control_adapter.get_state()
            candidate = {
                key: float(values[key])
                for key in control_adapter.PARAMETERS
            }
            checks = control_adapter.validate(candidate, current)
            preview = control_adapter.preview(candidate, current)
            st.session_state["control_candidate"] = candidate
            st.session_state["control_checks"] = checks
            st.session_state["control_preview"] = preview
            st.session_state["control_preview_current"] = current

        if st.button("重置为当前值", width="stretch"):
            st.session_state.control_version += 1
            for key in ("control_candidate", "control_checks", "control_preview"):
                st.session_state.pop(key, None)
            st.rerun()

    with right:
        candidate = st.session_state.get("control_candidate")
        checks = st.session_state.get("control_checks") or []
        preview = st.session_state.get("control_preview")
        current = st.session_state.get("control_preview_current") or state

        if not candidate or not preview:
            st.info("先在左侧改参数，点“预演并校验”。预演通过后才允许审批写入。")
        else:
            baseline_preview = control_adapter.preview(current, current)
            st.markdown("#### ② 预演结果")

            def _delta(value: float, baseline: float, unit: str) -> str | None:
                diff = value - baseline
                if abs(diff) < 0.005:
                    return None
                return f"{diff:+.2f} {unit}"

            m1, m2, m3, m4 = st.columns(4)
            m1.metric(
                "预测厚度 σ",
                f"{preview['thickness_sigma_um']:.2f} μm",
                delta=_delta(
                    preview["thickness_sigma_um"],
                    baseline_preview["thickness_sigma_um"],
                    "μm",
                ),
                delta_color="inverse",
            )
            m2.metric(
                "预测切边率",
                f"{preview['trim_rate_pct']:.2f}%",
                delta=_delta(
                    preview["trim_rate_pct"],
                    baseline_preview["trim_rate_pct"],
                    "pp",
                ),
                delta_color="inverse",
            )
            m3.metric(
                "预测降级率",
                f"{preview['downgrade_rate_pct']:.2f}%",
                delta=_delta(
                    preview["downgrade_rate_pct"],
                    baseline_preview["downgrade_rate_pct"],
                    "pp",
                ),
                delta_color="inverse",
            )
            m4.metric(
                "预测合格",
                f"{preview['qualified_t']:.1f} t",
                delta=_delta(
                    preview["qualified_t"],
                    baseline_preview["qualified_t"],
                    "t",
                ),
            )
            st.caption(
                f"风险：{preview['risk']} ｜ {preview['note']} ｜ "
                f"DR {preview['dr']:.2f}"
            )

            status_label = {"ok": "通过", "warn": "注意", "block": "拦截"}
            rows = [
                {
                    "项目": item["项目"],
                    "建议值": item["建议值"],
                    "状态": status_label.get(item["状态"], item["状态"]),
                    "说明": item["说明"],
                    "证据": item["证据"],
                }
                for item in checks
            ]
            st.dataframe(rows, hide_index=True, width="stretch")

            blocked = control_adapter.has_blocker(checks)
            if blocked:
                st.error("存在硬拦截项，写入按钮已禁用。先修正参数或降低变化幅度。")
            elif any(item["状态"] == "warn" for item in checks):
                st.warning("存在注意项：可以写入，但建议先做小步试车。")

            input_values = {
                key: float(
                    st.session_state.get(
                        f"control_{key}_{version}",
                        candidate[key],
                    )
                )
                for key in control_adapter.PARAMETERS
            }
            dirty = any(
                abs(input_values[key] - float(candidate[key])) > 1e-9
                for key in input_values
            )
            if dirty:
                st.warning("左侧参数已改动，当前预演结果已过期；请重新点“预演并校验”。")

            st.markdown("#### ③ 审批与写入")
            approver = st.text_input(
                "审批人",
                placeholder="工艺工程师姓名",
                key=f"control_approver_{version}",
            )
            note = st.text_input(
                "变更说明（可选）",
                placeholder="例如：厚度中心偏高，模唇回调 0.01 mm",
                key=f"control_note_{version}",
            )
            confirm = st.checkbox(
                "我已核对预演结果，并知道回退点",
                key=f"control_confirm_{version}",
            )
            can_write = (
                not blocked
                and not dirty
                and bool(approver.strip())
                and confirm
            )
            if st.button(
                "审批并写入（演示）",
                type="primary",
                disabled=not can_write,
                width="stretch",
            ):
                try:
                    record = control_adapter.write_setpoints(
                        candidate,
                        approver=approver,
                        note=note,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                except OSError as exc:
                    st.error(
                        "演示日志不可写：当前环境可能是只读文件系统。"
                        f"（{type(exc).__name__}: {exc}）"
                    )
                else:
                    st.session_state.control_flash = (
                        f"已写入 {record['id']}：审批人 {record['approver']}。"
                        "本地演示日志已记录，可在下方回滚。"
                    )
                    st.session_state.control_version += 1
                    for key in (
                        "control_candidate",
                        "control_checks",
                        "control_preview",
                        "control_preview_current",
                    ):
                        st.session_state.pop(key, None)
                    st.rerun()

    st.divider()
    st.markdown("#### ④ 审计与回滚")
    if log_rows:
        st.dataframe(log_rows, hide_index=True, width="stretch")
    else:
        st.caption("暂无审计记录。完成一次写入后，这里会出现可回滚的写入点。")

    write_rows = [row for row in log_rows if row["动作"] == "写入"]
    if write_rows:
        options = {row["记录"]: row for row in write_rows}
        selected = st.selectbox(
            "选择回退点",
            list(options.keys()),
            format_func=lambda rid: (
                f"{rid} ｜ {options[rid]['时间']} ｜ "
                f"{options[rid]['审批人']} ｜ 模唇 {options[rid]['模唇/mm']} mm"
            ),
        )
        rb_approver = st.text_input(
            "回滚审批人",
            placeholder="工艺工程师姓名",
            key=f"control_rb_approver_{version}",
        )
        rb_confirm = st.checkbox(
            "确认回滚到该写入前的 setpoint",
            key=f"control_rb_confirm_{version}",
        )
        if st.button(
            "回滚（演示）",
            disabled=not (rb_approver.strip() and rb_confirm),
            width="stretch",
        ):
            try:
                record = control_adapter.rollback(
                    selected,
                    approver=rb_approver,
                )
            except ValueError as exc:
                st.error(str(exc))
            except OSError as exc:
                st.error(
                    "演示日志不可写：当前环境可能是只读文件系统。"
                    f"（{type(exc).__name__}: {exc}）"
                )
            else:
                st.session_state.control_flash = (
                    f"已回滚 {record['target']}，生成记录 {record['id']}。"
                )
                st.session_state.control_version += 1
                st.rerun()


# =========================================================
# 数据库概览
# =========================================================

def render_database_tab():
    st.subheader("数据库与部署说明")

    status = db_snapshot()
    st.code(str(DB_PATH), language=None)

    if not status.get("exists"):
        st.error("找不到数据库。请把 data/database/bopet.db 一起上传到 GitHub。")
        return

    if DB_PATH.exists():
        st.caption(f"文件大小：{DB_PATH.stat().st_size / 1024 / 1024:.2f} MB")

    st.markdown("#### 数据表")

    try:
        conn = sqlite3.connect(
            f"file:{DB_PATH.as_posix()}?mode=ro",
            uri=True,
        )
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' ORDER BY name"
        )
        table_names = [row["name"] for row in cursor.fetchall()]

        rows = []

        for table in table_names:
            try:
                count = cursor.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
            except sqlite3.DatabaseError:
                count = "读取失败"

            rows.append({"表名": table, "记录数": count})

        st.dataframe(rows, hide_index=True, width="stretch")

        target_options = [
            table for table in
            ("evidence_01_50", "evidence_51_100", "table_data")
            if table in table_names
        ]

        if target_options:
            target = st.selectbox("查看字段", target_options)

            columns = cursor.execute(
                f'PRAGMA table_info("{target}")'
            ).fetchall()
            st.dataframe(
                [
                    {
                        "字段": column["name"],
                        "类型": column["type"],
                    }
                    for column in columns
                ],
                hide_index=True,
                width="stretch",
            )

        conn.close()

    except Exception as exc:
        st.error(f"读取数据库失败：{type(exc).__name__}: {exc}")

    st.markdown("#### 部署到 Streamlit Cloud")

    st.markdown(
        """
1. 把整个项目上传到 GitHub，确认包含 `data/database/bopet.db`。
2. 在 Streamlit Cloud 新建 App，入口选择 `streamlit_app.py`。
3. 在 **Settings → Secrets** 添加：

```toml
SILICONFLOW_API_KEY = "sk-你的key"
```

4. 依赖由 `requirements.txt` 自动安装。
5. 没有 API Key 时，页面仍可用“仅检索 / 规则模式”演示。
        """
    )


# =========================================================
# 主页面
# =========================================================

def _v3_metrics(report, hard_count, uncal_count):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("决策变量", f"{len(BOPET_VARIABLES)} 项", border=True)
    c2.metric("硬边界变量", f"{hard_count} 项", border=True)
    c3.metric("待现场标定", f"{uncal_count} 项", border=True)
    c4.metric("公式库", f"{len(FORMULAS)} 条", border=True)
    if report["hard_feasible"]:
        st.success("基线 24 变量离线预检：硬约束通过；未标定项不等同于现场联锁。", icon=":material/check_circle:")
    else:
        st.error("基线离线预检存在硬约束失败/未知项，禁止进入审批。", icon=":material/error:")


def _v3_overview(report, hard_count, uncal_count, summary):
    _v3_metrics(report, hard_count, uncal_count)
    st.info(
        "本工作台把 V3 拆成六块：总览、证据与约束、优化控制台、多维评价、审核与反馈、实验验证。"
        "规则/Mock 模式无需 API Key，所有写入只落本地。",
        icon=":material/dashboard:",
    )
    if summary:
        best = summary.get("best_evaluation") or {}
        a, b, c, d = st.columns(4)
        a.metric("最近评价候选", summary["candidates_evaluated"], border=True)
        b.metric("最近迭代", summary["iterations"], border=True)
        c.metric("停止原因", summary["stop_reason"], border=True)
        d.metric("最近最优", f"{best.get('objective_value', 0):,.2f}" if best.get("objective_value") is not None else "—", border=True)
    else:
        st.caption("暂无运行结果；到“优化控制台”设置预算并运行。")


def _v3_constraints():
    stats = catalog_stats()
    a, b, c = st.columns(3)
    a.metric("文献证据行", stats["total_evidence_rows"], border=True)
    b.metric("不同论文", stats["distinct_papers"], border=True)
    c.metric("核验状态", "UNVERIFIED", border=True)
    st.caption("证据库只读；原始 SQLite 未修改。UNVERIFIED 不等于可用于生产硬约束。")
    st.dataframe(
        [{"证据ID": r.evidence_id, "论文": r.source_id, "页": r.source_page,
          "参数类型": r.parameter_name, "原文": r.source_text[:90]}
         for r in load_records(limit=5)],
        hide_index=True,
        alt="文献证据目录前五条：编号、页码、参数类型和原文摘要",
    )
    st.dataframe(
        [{
            "变量": v.variable_id,
            "名称": v.name,
            "类型": str(v.constraint_type),
            "范围": f"{v.lower_bound} — {v.upper_bound} {v.unit}",
            "标定": v.calibration_status,
            "证据": ", ".join(v.evidence_ids),
        } for v in BOPET_VARIABLES],
        hide_index=True,
        alt="24 项 BOPET 决策变量、边界、标定状态和证据编号",
    )
    st.dataframe(
        [{"编号": k, "公式": v["name"], "状态": "已实现" if v["implemented"] else "未实现",
          "来源": v["source"]}
         for k, v in FORMULAS.items()],
        hide_index=True,
        alt="F01 到 F07 公式库实现状态与来源",
    )
    st.caption("证据—约束映射是草案；未标定文献边界只能离线预检，不能自动升级为现场联锁。")


def _render_v3_result(summary):
    best = summary.get("best_evaluation") or {}
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("评价候选", summary["candidates_evaluated"], border=True)
    m2.metric("迭代轮次", summary["iterations"], border=True)
    m3.metric("停止原因", summary["stop_reason"], border=True)
    m4.metric(
        "最优目标值",
        f"{best.get('objective_value', 0):,.2f}" if best.get("objective_value") is not None else "—",
        border=True,
    )
    st.caption(f"数据模式：{best.get('data_mode', 'UNKNOWN')}；运行 ID：{summary['run_id']}")

    rows = summary.get("records", [])
    chart_rows = [
        {"候选序号": i + 1, "目标值": r["objective"]}
        for i, r in enumerate(rows) if r.get("objective") is not None
    ]
    if chart_rows:
        st.line_chart(chart_rows, x="候选序号", y="目标值", height=260,
                      alt="V3 优化过程中每个候选的目标值变化")

    strategy_counts: dict[str, int] = {}
    for r in rows:
        strategy_counts[r["strategy"]] = strategy_counts.get(r["strategy"], 0) + 1
    if strategy_counts:
        st.bar_chart(
            [{"策略": k, "次数": v} for k, v in strategy_counts.items()],
            x="策略", y="次数", height=220,
            alt="V3 状态反馈产生的策略使用次数",
        )

    display = [{
        "轮次": r["iteration"],
        "候选": r["candidate_id"],
        "策略": r["strategy"],
        "步长": r["search_step"],
        "探索比": r["exploration_ratio"],
        "目标值": r["objective"],
        "硬可行": r["hard_feasible"],
    } for r in rows]
    st.dataframe(display, hide_index=True, height=260,
                 alt="V3 每轮候选、策略、搜索参数、目标值和硬可行性")
    st.caption("BOPET 目标是工程模型目标值，不是产线实测；Benchmark 目标仅用于算法对照。")


def _v3_console():
    st.warning(
        "BOPET 措施层是 M1—M7 的工程模型；24 变量选项是物理/约束代理预检，"
        "不是训练后的产量/质量预测。两者都不会写 PLC。",
        icon=":material/info:",
    )
    with st.form("v3_run_form"):
        left, mid, right = st.columns([1.4, 1, 1], vertical_alignment="bottom")
        scenario_name = left.selectbox(
            "实验场景",
            [
                "BOPET 措施层（工程估算）",
                "BOPET 24 变量物理预检（情景）",
                "Benchmark（合成基准）",
            ],
            help="措施层调用 production_model；24 变量走 F01/F04/F05 物理代理；Benchmark 仅验证算法。",
        )
        budget = mid.slider("评价预算", min_value=10, max_value=40, value=20, step=5)
        provider_name = right.selectbox("策略来源", ["rule", "mock", "internlm"],
                                        help="internlm 需要 LLM_MODEL/INTERNLM_API_KEY；无配置时回退规则")
        submitted = st.form_submit_button("运行 V3 自适应闭环", type="primary", width="stretch")

    if submitted:
        if "24 变量" in scenario_name:
            scenario = BOPETProcessScenario()
        elif scenario_name.startswith("BOPET"):
            scenario = BOPETMeasureScenario()
        else:
            scenario = BenchmarkScenario()
        try:
            provider = get_provider(provider_name)
        except Exception as exc:
            st.warning(f"模型服务未配置，回退规则模式：{exc}", icon=":material/key_off:")
            provider = get_provider("rule")
        controller = AgentController(provider)
        engine = OptimizationEngine(
            scenario,
            AdaptiveSearch(scenario),
            controller,
            config=EngineConfig(max_iterations=budget, max_evaluations=budget,
                                seed=7, patience=budget,
                                output_dir=PROJECT_ROOT / "outputs" / "v3_runs"),
        )
        with st.spinner("运行状态反馈闭环…"):
            st.session_state["v3_summary"] = engine.run()

    summary = st.session_state.get("v3_summary")
    if not summary:
        st.info("设置预算后运行；首次运行会写入 outputs/v3_runs。", icon=":material/play_circle:")
        return
    _render_v3_result(summary)


def _v3_evaluation():
    summary = st.session_state.get("v3_summary")
    if not summary:
        st.info("先运行一次闭环，才能查看四维评价。", icon=":material/analytics:")
        return
    best = summary.get("best_evaluation") or {}
    left, right = st.columns(2)
    with left:
        st.markdown("**物理评价**")
        st.json(best.get("physical_result", {}), expanded=True)
    with right:
        st.markdown("**生产评价**")
        st.json(best.get("production_result", {}), expanded=True)
    left2, right2 = st.columns(2)
    with left2:
        st.markdown("**经济评价**")
        st.json(best.get("economic_result", {}), expanded=True)
    with right2:
        st.markdown("**不确定性**")
        st.json(best.get("uncertainty_result", {}), expanded=True)
    st.caption(
        f"评价版本：{best.get('evaluation_version', '—')}；"
        f"硬可行：{best.get('hard_feasible')}；缺失字段：{best.get('missing_fields', [])}"
    )


def _v3_approval():
    summary = st.session_state.get("v3_summary")
    if not summary:
        st.info("先运行一次闭环，才能提交审核。", icon=":material/approval:")
        return
    from services.approval_service import ApprovalService
    from services.feedback_service import FeedbackService
    from core.schemas import EvaluationResult

    candidate = CandidatePlan.model_validate(summary["best_candidate"])
    evaluation = EvaluationResult.model_validate(summary["best_evaluation"])
    with st.form("v3_approval_form"):
        reviewer = st.text_input("审核人", value="engineer")
        decision = st.selectbox("审核结论", ["NEEDS_DATA", "APPROVED", "REJECTED"])
        note = st.text_area("备注", value="离线审核；不写 PLC/MES")
        reviewed = st.form_submit_button("提交审核记录", width="stretch")
    if reviewed:
        try:
            record = ApprovalService(PROJECT_ROOT / "data" / "approval.jsonl").submit(
                candidate, evaluation, reviewer=reviewer or "unknown", decision=decision, note=note)
            st.success(f"审核记录已写入；decision={record['decision']}；plant_write={record['plant_write']}",
                       icon=":material/verified:")
        except Exception as exc:
            st.error(f"审核被拒绝：{exc}", icon=":material/error:")

    template = PROJECT_ROOT / "data" / "feedback" / "trial_feedback_template.csv"
    if template.exists():
        st.download_button(
            "下载 48 h 试车 CSV 模板",
            data=template.read_bytes(),
            file_name="trial_feedback_template.csv",
            mime="text/csv",
            width="stretch",
            icon=":material/download:",
        )
    uploaded = st.file_uploader("导入试车 CSV（模拟数据必须标 SIMULATED）", type=["csv"])
    if uploaded is not None:
        target = PROJECT_ROOT / "data" / "feedback" / f"uploaded_{uploaded.name}"
        target.write_bytes(uploaded.getvalue())
        try:
            rows = FeedbackService(PROJECT_ROOT / "data" / "feedback").import_csv(target)
            st.success(f"已导入 {len(rows)} 行；未连接 PLC/MES。", icon=":material/upload_file:")
        except Exception as exc:
            st.error(f"导入失败：{exc}", icon=":material/error:")


def _v3_experiments():
    import json

    exp = PROJECT_ROOT / "outputs" / "v3_experiments" / "optimizer_comparison_summary.json"
    abl = PROJECT_ROOT / "outputs" / "v3_ablation" / "ablation_summary.json"
    if exp.exists():
        st.markdown("**对照实验：30 次评价 × 3 seeds**")
        data = json.loads(exp.read_text(encoding="utf-8"))
        st.dataframe(
            [{"场景/方法": k, "n": v["n"], "mean": v["mean"], "std": v["std"], "best": v["best"]}
             for k, v in data.items()],
            hide_index=True,
            alt="A/B/C/D 优化器对照实验结果",
        )
        st.caption("D 未优于 A/B；这是负结果，不做事后挑选。")
    else:
        st.info("尚无对照实验；运行 experiments/compare_optimizers.py。")
    if abl.exists():
        st.markdown("**有限消融**")
        data = json.loads(abl.read_text(encoding="utf-8"))
        st.dataframe(
            [{"场景/变体": k, "n": v["n"], "mean": v["mean"], "std": v["std"]}
             for k, v in data.items()],
            hide_index=True,
            alt="去状态反馈、去 anti-regression 的消融结果",
        )
    else:
        st.info("尚无消融结果；运行 experiments/ablation.py。")


def render_v3_tab():
    st.subheader("V3 自适应优化引擎")
    st.caption("六块工作台；规则模式无需 API Key，页面不写 PLC/MES。")
    sections = ["总览", "证据与约束", "优化控制台", "多维评价", "审核与反馈", "实验验证"]
    section = st.segmented_control("V3 工作台", sections, default="优化控制台",
                                   label_visibility="collapsed", width="stretch")

    baseline_candidate = CandidatePlan(
        candidate_id="v3-baseline",
        parameters=dict(BOPET_BASELINE),
        generation_strategy="baseline",
    )
    report = ConstraintEngine(BOPET_VARIABLES).evaluate(baseline_candidate)
    hard_count = sum(1 for v in BOPET_VARIABLES if ConstraintType(v.constraint_type) == ConstraintType.HARD)
    uncal_count = sum(1 for v in BOPET_VARIABLES if v.calibration_status != "CALIBRATED")
    summary = st.session_state.get("v3_summary")

    if section == "总览":
        _v3_overview(report, hard_count, uncal_count, summary)
    elif section == "证据与约束":
        _v3_constraints()
    elif section == "优化控制台":
        _v3_console()
    elif section == "多维评价":
        _v3_evaluation()
    elif section == "审核与反馈":
        _v3_approval()
    else:
        _v3_experiments()


def main():
    page, demo = render_product_sidebar()

    if page == "overview":
        overview_page.render(demo=demo)
    elif page == "evidence":
        evidence_page.render(legacy_qa=render_qa_tab)
    elif page == "constraints":
        constraints_page.render()
    elif page == "optimization":
        optimization_page.render(demo=demo, legacy_plan=render_plan_tab)
    elif page == "evaluation":
        evaluation_page.render(demo=demo)
    elif page == "validation":
        validation_page.render(demo=demo)
    elif page == "review":
        review_page.render(legacy_control=render_control_tab)
    else:
        settings_page.render(legacy_database=render_database_tab)


if __name__ == "__main__":
    main()

