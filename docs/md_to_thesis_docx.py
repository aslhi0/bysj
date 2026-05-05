# -*- coding: utf-8 -*-
"""
定稿时一次性生成 Word，日常勿运行。

工作流
------
- 平时：只维护「毕业论文初稿.md」，让助手改内容也只改该文件，不因此生成 docx。
- 定稿：论文内容确认后，在 docs 目录执行
      python md_to_thesis_docx.py
  会读取 毕业论文初稿.md，并生成（覆盖）「毕业论文初稿.docx」。

依赖：pip install python-docx

本脚本不修改 md 文件；旧版会额外生成 毕业论文初稿_正文.txt 已取消，以 md + 定稿时 docx 为准。
"""
import re
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "毕业论文初稿.md"
OUT_DOCX = ROOT / "毕业论文初稿.docx"
DOC_TITLE = "毕业论文初稿"

REPLACEMENTS = [
    (r"针对这一痛点[，,]", "针对上述问题，"),
    (r"针对这一现状[，,]", "针对上述情况，"),
    (r"值得一提的是", ""),
    (r"换言之[，,]", "即，"),
    (r"并非停留于", "不局限于"),
    (r"该问题并非单纯的偶发噪声，而是会系统性削弱", "该问题会削弱"),
    (r"统计学基础在本系统中的作用不是提供抽象理论装饰，而是直接决定", "统计量在本系统中直接决定"),
    (r"该闭环的业务价值在于把测试活动从单次任务提升为持续学习过程：系统不是静态执行器，而是能够基于历史证据不断修正执行策略的决策支持平台。",
     "新执行结果进入分析窗口后会影响后续策略，形成可重复利用历史的闭环。"),
    (r"为后续需求、设计与实现章节提供统一理论坐标：", "为需求、设计、实现各章提供共同参照："),
    (r"平台化治理依赖分层架构，策略可信度依赖统计建模，工程可持续性依赖解耦与演进机制。",
     "分层利于治理；Flaky 策略以统计量表达；工程上可借解耦与演进控制复杂度。"),
    (r"可解释性因此成为连接算法与工程实践的必要桥梁。", "可解释性因此是算法结果能否进入工程流程的前提。"),
    (r"其方法学意义在于：", "在方法上，"),
    (r"其安全意义在于：", "在安全性上，"),
    (r"该机制的工程意义在于：", "在工程上，"),
    (r"若仅实现执行能力而缺少治理，本系统将无法在真实协作环境中稳定运行。",
     "若缺少治理，则执行能力难以在多人协作场景中长期稳定。"),
    (r"因此，本研究证明了在本科毕业设计规模下，构建", "在本科毕业设计规模下，本文说明构建"),
    (r"未来工作将围绕", "后续可围绕"),
]


def apply_replacements(s: str) -> str:
    s = s.strip()
    for a, b in REPLACEMENTS:
        s = re.sub(a, b, s)
    s = re.sub(r" +", " ", s)
    s = s.replace("。。", "。")
    return s


def strip_md(s: str) -> str:
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = s.replace("&nbsp;", " ")
    s = s.replace("**", "")
    return s.strip()


def main():
    text = apply_replacements(SRC.read_text(encoding="utf-8"))
    lines = text.splitlines()
    out: list = []
    in_code = False
    bq: list = []

    def flush_bq():
        nonlocal bq
        if bq:
            s = "；".join(bq)
            out.append("【按语】" + s)
            bq = []

    for line in lines:
        t = line.rstrip()
        st = t.strip()
        if st.startswith("```"):
            flush_bq()
            in_code = not in_code
            if not in_code:
                out.append("")
            continue
        if in_code:
            out.append(t)
            continue
        if st == "" or st == "---":
            flush_bq()
            out.append("")
            continue
        if st.startswith(">"):
            inner = st[1:].strip()
            if inner and inner != ">":
                bq.append(apply_replacements(strip_md(inner)))
            continue
        flush_bq()
        if st.startswith("#"):
            h = apply_replacements(strip_md(st.lstrip("#").strip()))
            out.append(h)
            continue
        if st.startswith("|") and "|-|" not in st:
            if re.match(r"^\|[-:\s|]+\|?\s*$", st):
                continue
            parts = [apply_replacements(strip_md(p)) for p in st.split("|") if p.strip()]
            if parts:
                out.append("，".join(parts))
            continue
        if re.match(r"^[-*+]\s+", st) or re.match(r"^\d+\.\s+", st):
            item = re.sub(r"^[-*+]\s+", "", re.sub(r"^\d+\.\s+", "", st))
            out.append(apply_replacements(strip_md(item)))
            continue
        m_img = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", st)
        if m_img:
            out.append("<<IMAGE:" + m_img.group(2).strip() + ">>")
            continue
        if st:
            out.append(apply_replacements(strip_md(st)))

    flush_bq()
    body = "\n\n".join(x for x in out if x is not None)
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = body.replace("【按语】文档说明", "文档说明")
    body = body.replace("【按语】毕业设计论文（初稿）", DOC_TITLE)
    body = body.replace("毕业设计论文（初稿）", DOC_TITLE)
    body = body.replace("毕业论文初稿；作者：", "毕业论文初稿\n\n作者：")
    body = body.replace("指导教师：<填写姓名>；学院", "指导教师：<填写姓名>\n\n学院")

    doc = Document()
    doc.core_properties.title = DOC_TITLE
    for block in body.split("\n\n"):
        b = block.strip()
        if not b:
            continue
        if b.startswith("<<IMAGE:") and b.endswith(">>"):
            rel = b[8:-2]
            path = (ROOT / rel).resolve()
            if path.is_file():
                para = doc.add_paragraph()
                run = para.add_run()
                run.add_picture(str(path), width=Inches(6.2))
            else:
                doc.add_paragraph(f"（图文件未找到，请将 {rel} 置于与本文档相对路径并重新生成。）")
            continue
        p = doc.add_paragraph(b)
        s0 = b[:20]
        if s0.startswith("第") and "章" in s0[:6] and len(b) < 40:
            p.style = "Heading 1" if "章" in b[:4] else p.style
    try:
        doc.styles["Normal"].font.size = Pt(12)
    except Exception:
        pass
    doc.save(str(OUT_DOCX))

    n = len(body)
    print("OK", n, "chars ->", OUT_DOCX)


if __name__ == "__main__":
    main()
