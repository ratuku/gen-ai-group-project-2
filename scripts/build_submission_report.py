"""Build the submission PDF from documented project evidence.

Requires reportlab and pypdf (available in the Codex bundled document runtime).
Run from any directory. The original planning PDF is inserted without redrawing it.
"""

from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf"
TMP = ROOT / "tmp" / "pdfs" / "submission-report"
INK = colors.HexColor("#183344")
TEAL = colors.HexColor("#146B73")
PALE = colors.HexColor("#EAF3F4")
GRAY = colors.HexColor("#50616B")
styles = getSampleStyleSheet()
styles.add(ParagraphStyle("ReportTitle", fontName="Helvetica-Bold", fontSize=27,
                          leading=31, textColor=INK, spaceAfter=14))
styles.add(ParagraphStyle("Deck", fontName="Helvetica", fontSize=12,
                          leading=17, textColor=GRAY, spaceAfter=15))
styles.add(ParagraphStyle("SectionTitle", fontName="Helvetica-Bold", fontSize=18,
                          leading=23, textColor=INK, spaceAfter=13))
styles.add(ParagraphStyle("Subhead", fontName="Helvetica-Bold", fontSize=11,
                          leading=15, textColor=TEAL, spaceBefore=10, spaceAfter=5))
styles.add(ParagraphStyle("Copy", fontName="Helvetica", fontSize=10,
                          leading=14, textColor=INK, spaceAfter=8))
styles.add(ParagraphStyle("SmallCopy", parent=styles["Copy"], fontSize=8.3,
                          leading=11, spaceAfter=5))
styles.add(ParagraphStyle("Cell", parent=styles["Copy"], fontSize=9,
                          leading=12, spaceAfter=0))
styles.add(ParagraphStyle("HeaderCell", parent=styles["Cell"],
                          fontName="Helvetica-Bold", textColor=colors.white))


def p(text, style="Copy"):
    return Paragraph(text, styles[style])


def table(rows, widths):
    cells = [[p(escape(str(x)), "HeaderCell" if i == 0 else "Cell")
              for x in row] for i, row in enumerate(rows)]
    obj = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    obj.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PALE, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#CFDDE0")),
    ]))
    return obj


def footer(canvas, doc):
    page = doc.page if doc.page < 5 else doc.page + 1
    canvas.setStrokeColor(colors.HexColor("#CCDADD"))
    canvas.line(48, 40, 564, 40)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(48, 26, "JUNIPER  |  Group Project 2  |  15 October 2026")
    canvas.drawRightString(564, 26, f"{page} / 6")


class Architecture(Flowable):
    """Vector diagram of the implemented process boundaries."""

    def __init__(self):
        super().__init__()
        self.width = 516
        self.height = 316

    def draw(self):
        c = self.canv

        def box(x, y, w, h, text, fill=PALE, size=9):
            c.setFillColor(fill)
            c.setStrokeColor(TEAL)
            c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
            c.setFillColor(INK)
            c.setFont("Helvetica", size)
            lines = text.split("\n")
            for i, line in enumerate(lines):
                c.drawCentredString(x + w / 2, y + h / 2 + (len(lines)-1)*5 - i*11 - 3, line)

        def arrow(x1, y1, x2, y2):
            import math
            c.setStrokeColor(INK)
            c.setFillColor(INK)
            c.setLineWidth(1)
            c.line(x1, y1, x2, y2)
            a = math.atan2(y2-y1, x2-x1)
            q = c.beginPath()
            q.moveTo(x2, y2)
            for d in (-0.5, 0.5):
                q.lineTo(x2 - 6*math.cos(a+d), y2 - 6*math.sin(a+d))
            q.close()
            c.drawPath(q, fill=1, stroke=0)

        c.setStrokeColor(colors.HexColor("#B4C8CD"))
        c.roundRect(0, 158, 516, 155, 8, fill=0, stroke=1)
        c.setFillColor(GRAY)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(10, 300, "CODING ASSISTANT PROCESS")
        box(12, 244, 104, 39, "User / CLI\nstreamed progress")
        box(155, 244, 126, 39, "Agent loop\nreason / act / observe")
        box(324, 244, 176, 39, "Provider adapter\nGroq or Ollama")
        arrow(116, 263, 155, 263)
        arrow(281, 263, 324, 263)
        box(155, 174, 345, 44, "Tool dispatcher + execution policy + MCP client\nexact names / argument schemas / confirmation or auto")
        arrow(218, 244, 218, 218)
        box(12, 91, 145, 43, "Filesystem MCP\nlocal Node.js / stdio")
        box(185, 91, 145, 43, "DeepWiki MCP\nhosted / HTTP")
        box(358, 91, 145, 43, "Custom RAG MCP\nlocal Python / stdio")
        for x in (84, 257, 430):
            arrow(x if x >= 155 else 174, 174, x, 134)
        box(168, 3, 335, 65, "Corpus -> chunks -> embeddings -> Chroma (offline build)\nQuery -> cosine candidates -> cross-encoder reranking\nOriginal passages + source / page / chunk references", size=8.3)
        arrow(430, 91, 430, 68)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GRAY)
        c.drawString(12, 59, "Arrows show request flow.")
        c.drawString(12, 47, "Results return to the agent.")


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    body = TMP / "report-body.pdf"
    story = []
    add = story.append

    # Page 1: system and design decisions.
    add(p("Juniper", "ReportTitle"))
    add(p("CLI coding assistant | Project report", "Deck"))
    add(p("Group Project 2 - 15 October 2026", "SmallCopy"))
    add(p("1. System and design decisions", "SectionTitle"))
    add(p("Juniper accepts a natural-language coding task in a terminal. An agent loop asks an LLM what to do, executes validated MCP tool calls, returns their results to the model, and streams its answer. It can inspect and edit project files and retrieve local or external documentation. The implementation supports Groq and Ollama; the comparison in this report uses two different Groq-hosted LLMs."))
    add(table([
        ["Design decision", "Reason and implemented behavior"],
        ["Separate providers from the agent", "A shared streaming interface lets the same agent and tools run with Groq or Ollama. Model comparisons therefore reuse the execution pipeline."],
        ["Discover tools through MCP", "A local filesystem server, hosted DeepWiki server, and separate custom RAG server expose tools without coupling the agent to their internals."],
        ["Validate before execution", "The dispatcher checks discovered names and JSON argument schemas. Filesystem roots constrain file access. Tool confirmation is the default; evaluations use explicit auto mode."],
        ["Keep retrieval local and traceable", "Chroma stores document embeddings. Returned snippets retain source, page, and chunk references. Cross-encoder reranking improves ordering within retrieved candidates."],
        ["Bound cloud requests and recovery", "Adapters compact history, pace requests, and expose bounded retries. Evaluation checkpoints allow later resume. Full local history is retained; account limits remain external."],
    ], [158, 358]))
    add(Spacer(1, 12))
    add(p("Evidence status", "Subhead"))
    add(p("This report includes the completed baseline and intermediate diagnostic runs. The latest reliability fixes have regression coverage, but a complete live retest of the final policy is still pending after Groq quota exhaustion. Passing local tests is not proof of successful autonomous coding."))
    add(p("Report guide: model comparison p. 2; advanced RAG p. 3; reflection and evidence p. 4; original planning architecture p. 5; updated architecture and reasons for changes p. 6.", "SmallCopy"))
    add(PageBreak())

    # Page 2: same-task comparison, including both success measures.
    add(p("2. Two LLMs on the same coding tasks", "SectionTitle"))
    add(p("Models: <b>openai/gpt-oss-20b</b> and <b>openai/gpt-oss-120b</b>, both through Groq. The baseline used four identical task definitions, three repetitions per model, fresh conversations, and isolated copies of the same initial files: 24 scored attempts. Only workspace paths differed in task prompts. All runs used the production agent, all three MCP servers (18 discovered tools), auto execution, up to eight iterations, and a 180-second task deadline. Baseline generation settings were SDK defaults."))
    add(p("A code-check pass means saved code met the evaluator's behavioral checks. An end-to-end pass additionally requires successful read/edit tools, required retrieval tools for the documentation task, normal completion, and no terminal agent error. Checks run outside the model's accessible fixture root."))
    add(table([
        ["Identical task", "20B end-to-end", "120B end-to-end"],
        ["Fix mean calculation; raise ValueError for empty input", "1 / 3", "1 / 3"],
        ["Extract unique ASCII words in first-seen order", "3 / 3", "0 / 3"],
        ["Refactor sales totals into a shared helper", "0 / 3", "0 / 3"],
        ["Implement UTF-8 greeting writer using retrieved docs", "0 / 3", "0 / 3"],
        ["Total end-to-end passes", "4 / 12 (33.3%)", "1 / 12 (8.3%)"],
        ["Total code-check passes", "4 / 12", "3 / 12"],
    ], [298, 109, 109]))
    add(p("Insights from the baseline", "Subhead"))
    add(p("20B completed the ASCII-word feature on all three attempts; 120B repeatedly requested unqualified tool names. Conversely, 120B produced two correct sales refactors, but subsequent requests exceeded the account's 8,000-token-per-minute allowance, preventing end-to-end passes. Both models fixed the mean only on their third attempt. Tool use, recovery, and quota constraints strongly affected outcomes; model size alone did not predict success."))
    add(p("Subsequent diagnostics and current limits", "Subhead"))
    add(p("Two intermediate eight-run pilots scored <b>3/8</b> and <b>2/8</b>. The second had zero dispatched tool errors, but still failed on limits, Windows indentation, and ASCII/Unicode logic. A later free-tier batch with pacing, checkpoints, and syntax checks passed the bug-fix task with <b>both models</b>. The next slot hit the daily cap before tool use, and the runner paused: <b>2/3 attempted, 2/8 planned</b>, with five slots unattempted. This remains a partial retest, not a clean overall improvement estimate or general model ranking."))
    add(p("Sources: evaluations/model_comparison/results/2026-10-15/, results/2026-10-15-fixes/, and results/2026-10-15-free-tier/. Each retains its own report, traces, source files, and metadata.", "SmallCopy"))
    add(PageBreak())

    # Page 3: RAG observations, clearly separating direct retrieval from coding.
    add(p("3. Advanced RAG and insights", "SectionTitle"))
    add(p("The chosen technique is <b>cross-encoder reranking</b>. The corpus contains FastMCP documentation and Python, JavaScript, and Java PDFs. Text is chunked and embedded with <b>all-MiniLM-L6-v2</b>; Chroma indexes 10,473 chunks. At query time, cosine search finds candidates, then <b>cross-encoder/ms-marco-MiniLM-L6-v2</b> jointly scores each query/passage pair. The server returns original snippets and references in the new order."))
    add(p("Why this technique", "Subhead"))
    add(p("A semantically related passage can rank highly without answering the question. Reranking adds a query-aware relevance step while reusing the existing vectors. The MCP tool defaults to reranking; cosine mode remains available as the baseline. Cosine similarity and cross-encoder logits are distinct scores, and neither is a confidence percentage."))
    add(p("Recorded direct retrieval comparison", "Subhead"))
    add(p("The documented production-stdio comparison used the same index and queries, top_k=5, and candidate_k=20 for reranking. These are the recorded manual observations in docs/rag-reranking.md, not a new experiment performed for this PDF."))
    add(table([
        ["Question", "Cosine first result", "Reranked first result"],
        ["Register a FastMCP tool", "Release note about tool-name validation", "Tool-registration API documentation (previously second)"],
        ["How does Python break stop a loop?", "Definition, Python PDF p. 28", "Loop example, Python PDF p. 29"],
        ["JavaScript let versus const", "Scope/reassignment discussion, p. 44", "Variable-declaration comparison, p. 44"],
    ], [148, 177, 191]))
    add(p("What we learned", "Subhead"))
    add(p("Reranking made the first FastMCP result more directly useful and changed the top explanations for the language queries. The recorded check verified that all 30 returned snippets preserved their original text and references. However, a JavaScript passage still ranked second for the Python question, and some FastMCP matches addressed authentication rather than tools. A larger labeled query set is needed to measure retrieval quality."))
    add(p("The coding evaluation exposed a different limit: RAG results for the greeting task weakly supported Path.write_text, while DeepWiki supplied more relevant API details. No baseline documentation task completed, so improved grounded coding answers were not demonstrated. Reranking cannot retrieve missing documentation or rescue a relevant passage outside its candidate pool. Increasing the pool adds local scoring latency; source filters and better corpus coverage are practical next steps."))
    add(p("Sources: docs/rag-reranking.md; rag_server/retrieval/; baseline report's Retrieval and grounding section. The retrieval observations and coding pass rates measure different things.", "SmallCopy"))
    add(PageBreak())

    # Page 4: reflection, provenance, and how to locate supporting work.
    add(p("4. Reflection and supporting evidence", "SectionTitle"))
    add(p("What worked", "Subhead"))
    add(p("The provider-neutral loop connected filesystem, external documentation, and local RAG tools through one execution path. Several coding attempts produced correct saved implementations, and the evaluation retained source and traces instead of relying on model claims. Direct retrieval comparisons showed useful changes in first-result relevance. Regression checks after the free-tier reliability work passed 242 tests, with strict type checking passing for 59 files."))
    add(p("What did not work", "Subhead"))
    add(p("The baseline was unreliable: incorrect tool names, optional null arguments, malformed output, long histories, and provider quotas interrupted tasks. Windows line-ending mismatches could trigger an edit that damaged indentation. Tool success did not imply code correctness: the later 120B feature implementation mishandled Unicode when enforcing ASCII words. Retrieval sometimes returned related but insufficient evidence, and scanned PDF pages without extracted text limited corpus coverage."))
    add(p("Changes made and what we would improve", "Subhead"))
    add(p("Implemented changes include tool aliases, optional-null cleanup, bounded recovery, context compaction, Windows-edit normalization, and the correct RAG interpreter. New free-tier controls pace requests and checkpoint batches for resume. Saved Python edits receive syntax checks through policy-controlled reads; failures feed back to the model and block normal completion until repaired. Syntax checks do not execute generated code or prove its behavior."))
    add(p("A complete current-policy live retest remains the priority, retaining failures as well as successes. We would add behavioral validation to the agent workflow, improve documentation coverage and source filtering, and evaluate reranking with independently judged queries. More repetitions, controlled account load, and recorded token usage would strengthen comparisons. These remain proposed improvements, not completed capabilities."))
    add(p("Evidence index (paths relative to repository root)", "Subhead"))
    add(table([
        ["Evidence", "Location"],
        ["24-run baseline and saved code", "evaluations/model_comparison/results/2026-10-15/"],
        ["Fixes, 16 diagnostic runs, final-policy hashes", "evaluations/model_comparison/results/2026-10-15-fixes/"],
        ["RAG method and recorded observations", "docs/rag-reranking.md"],
        ["Free-tier controls and syntax validation", "evaluations/model_comparison/FREE_TIER_TESTING_NOTES.md"],
        ["Original planning architecture (p. 5)", "init-architecture.drawio2.pdf"],
        ["Current structure and configuration (p. 6)", "docs/architecture.md; config/mcp.json; src/coding_assistant/; rag_server/"],
    ], [188, 328]))
    add(Spacer(1, 8))
    add(p("The baseline evaluated commit 6e4735d6b1b81ac2233d00d9e775ccaf5736d83b. Later fixes are local changes identified by retained source hashes. This PDF includes the three-attempt partial free-tier batch from 15 October 2026; later PowerShell runs are not incorporated automatically. Page 5 reproduces the original planning PDF as an unchanged page.", "SmallCopy"))
    add(PageBreak())

    # The original PDF will be inserted immediately before this generated page.
    add(p("5. Updated architecture", "SectionTitle"))
    add(p("The original planning diagram appears on page 5. The diagram below shows the implemented system, including the later reliability changes. It preserves the planned CLI, agent, MCP client, and three-server structure."))
    add(Architecture())
    add(p("What changed from the plan, and why", "Subhead"))
    add(p("<b>Model boundary made explicit.</b> Groq/Ollama adapters sit outside the agent's coordination logic so models can change without replacing the tool pipeline. The planning diagram did not show this boundary."))
    add(p("<b>Execution checks added explicitly.</b> Discovered tool names, schemas, and confirmation policy sit before MCP calls. Provider-side aliases, context budgeting, and retries address the failures observed during evaluation."))
    add(p("<b>RAG design made concrete.</b> The plan's generic retrieval/vector-database branches became an offline ingestion/index build and a query-time cosine-plus-cross-encoder pipeline. Answer generation remains in the main agent/provider; the RAG server returns evidence. Chroma and reranking were chosen to reuse vectors and improve passage ordering."))
    add(p("<b>Deployment boundaries clarified.</b> Filesystem and RAG are local stdio processes; DeepWiki is hosted over HTTP. The RAG executable follows the running Python interpreter to avoid missing dependencies. These refinements explain how the original architecture became executable."))

    doc = SimpleDocTemplate(str(body), pagesize=(612, 792), leftMargin=48,
                            rightMargin=48, topMargin=43, bottomMargin=53,
                            title="Juniper - Group Project 2 Report", author="Group Project 2")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    generated = PdfReader(body)
    if len(generated.pages) != 5:
        raise ValueError(f"Expected 5 authored pages, got {len(generated.pages)}")
    original_path = ROOT / "init-architecture.drawio2.pdf"
    original = PdfReader(original_path)
    if len(original.pages) != 1:
        raise ValueError("Expected one original architecture page")
    writer = PdfWriter()
    for page in generated.pages[:4]:
        writer.add_page(page)
    writer.add_page(original.pages[0])
    writer.add_page(generated.pages[4])
    writer.add_metadata({"/Title": "Juniper - Group Project 2 Report",
                         "/Author": "Group Project 2",
                         "/Subject": "System design, LLM comparison, advanced RAG, reflection, and original/updated architecture"})
    for name, index in [("System and design decisions", 0), ("Two-model comparison", 1),
                        ("Advanced RAG", 2), ("Reflection and evidence", 3),
                        ("Original planning architecture", 4), ("Updated architecture", 5)]:
        writer.add_outline_item(name, index)
    output = ROOT / "PROJECT_REPORT.pdf"
    with output.open("wb") as stream:
        writer.write(stream)
    print(output)


if __name__ == "__main__":
    build()
