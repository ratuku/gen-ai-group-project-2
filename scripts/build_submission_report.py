"""Build the submission PDF from documented project evidence.

Requires reportlab and pypdf (available in the Codex bundled document runtime).
Run from any directory. The original planning PDF is inserted without redrawing it.
"""

from pathlib import Path
import json
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)
from report_diagrams import SCENARIOS, SequenceDiagram, StateDiagram


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
    canvas.drawRightString(564, 26, f"{page} / 10")


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
        box(2, 91, 120, 43, "Filesystem MCP\nNode.js / stdio")
        box(133, 91, 120, 43, "DeepWiki MCP\nhosted / HTTP")
        box(264, 91, 120, 43, "Python checks MCP\nlocal / stdio")
        box(395, 91, 120, 43, "Custom RAG MCP\nlocal / stdio")
        for x in (62, 193, 324, 455):
            arrow(x if x >= 155 else 174, 174, x, 134)
        box(168, 3, 335, 65, "Corpus -> chunks -> embeddings -> Chroma (offline build)\nQuery -> cosine candidates -> cross-encoder reranking\nOriginal passages + source / page / chunk references", size=8.3)
        arrow(455, 91, 455, 68)
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
    add(p("Juniper accepts a natural-language coding task in a terminal. An agent loop asks an LLM what to do, executes validated MCP tool calls, returns their results to the model, and streams its answer. It can inspect and edit files, run Python scripts/tests, and retrieve local or external documentation. Groq and Ollama share the provider interface; the model comparison uses two different Groq-hosted LLMs."))
    add(table([
        ["Design decision", "Reason and implemented behavior"],
        ["Separate providers from the agent", "A shared streaming interface lets the same agent and tools run with Groq or Ollama. Model comparisons therefore reuse the execution pipeline."],
        ["Discover tools through MCP", "The required filesystem, hosted DeepWiki, and custom RAG servers are joined by a Python-check server. All tools are dynamically discovered through MCP."],
        ["Validate before execution", "The dispatcher checks names and argument schemas. Confirmation is the default. Python checks validate the target path, use no shell, omit credential environment variables, and bound duration/output; executed code is trusted, not OS-sandboxed."],
        ["Keep retrieval local and traceable", "Chroma stores document embeddings. Returned snippets retain source, page, and chunk references. Cross-encoder reranking improves ordering within retrieved candidates."],
        ["Bound cloud requests and recovery", "Adapters compact history, pace requests, and expose bounded retries. Evaluation checkpoints allow later resume. Full local history is retained; account limits remain external."],
    ], [158, 358]))
    add(Spacer(1, 12))
    add(p("Evidence status", "Subhead"))
    add(p("This report includes the completed baseline and intermediate diagnostic runs. The latest reliability fixes have regression coverage, but a complete live retest of the final policy is still pending after Groq quota exhaustion. Passing local tests is not proof of successful autonomous coding."))
    add(p("Report guide: model comparison p. 2; measured RAG evaluation p. 3; reflection/evidence p. 4; original planning architecture p. 5; updated architecture p. 6; state and three sequence diagrams pp. 7-10.", "SmallCopy"))
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

    # Page 3: measured RAG results loaded from the retained, auditable experiment.
    add(p("3. Advanced RAG and insights", "SectionTitle"))
    add(p("The chosen technique is <b>cross-encoder reranking</b>. The corpus contains FastMCP documentation and Python, JavaScript, and Java PDFs. Text is chunked and embedded with <b>all-MiniLM-L6-v2</b>; Chroma indexes 10,473 chunks. At query time, cosine search finds candidates, then <b>cross-encoder/ms-marco-MiniLM-L6-v2</b> jointly scores each query/passage pair. The server returns original snippets and references in the new order."))
    add(p("Why this technique", "Subhead"))
    add(p("A semantically related passage can rank highly without answering the question. Reranking adds a query-aware relevance step while reusing the existing vectors. The MCP tool defaults to reranking; cosine mode remains available as the baseline. Cosine similarity and cross-encoder logits are distinct scores, and neither is a confidence percentage."))
    add(p("Paired experiment: relevance, answers, and grounding", "Subhead"))
    add(p("Ten fixed questions cover all four documents: eight intended answerable questions, a Path.write_text coverage probe, and an unrelated negative control. Both modes use the same production stdio MCP server and index, top_k=5, and no source filter. Reranking scores 20 cosine candidates. Generation uses the same Groq 20B adapter, evidence-only prompt, temperature 0, and SDK-default text-only reasoning; only the five supplied passages differ. Mode order alternates. This isolates context quality, not autonomous tool selection."))
    metrics = json.loads((ROOT / "evaluations/rag_evaluation/results/2026-10-15/metrics.json").read_text(encoding="utf-8"))
    a, b = (metrics["aggregate"][mode] for mode in ("cosine", "rerank"))
    add(table([
        ["Metric", "Cosine baseline", "Cross-encoder"],
        ["Direct evidence at rank 1 (8 queries)", f"{a['direct_hit_at_1']:.1%}", f"{b['direct_hit_at_1']:.1%}"],
        ["Precision@5 (directly useful passages)", f"{a['precision_at_5']:.1%}", f"{b['precision_at_5']:.1%}"],
        ["Mean reciprocal rank@5", f"{a['reciprocal_rank_at_5']:.3f}", f"{b['reciprocal_rank_at_5']:.3f}"],
        [f"Correct reference facts ({a['generated_answers']} answer pairs)", f"{a['correct_reference_facts']}/{a['possible_reference_facts']}", f"{b['correct_reference_facts']}/{b['possible_reference_facts']}"],
        ["Fully grounded answers", f"{a['fully_grounded_answers']}/{a['generated_answers']}", f"{b['fully_grounded_answers']}/{b['generated_answers']}"],
        ["Median warm retrieval time (10 queries)", f"{a['median_retrieval_seconds']:.3f} s", f"{b['median_retrieval_seconds']:.3f} s"],
    ], [292, 112, 112]))
    add(p("What we learned", "Subhead"))
    add(p("Reranking brought a complete FastMCP tool example into the final context; the baseline answer invented unsupported decorator arguments. Python break moved above a JavaScript passage. Gains were uneven: the reranked Java finally result was JavaScript, and the Python continue context lost a useful Python definition. Neither mode retrieved the required Path.write_text API detail. Source scope and corpus coverage remain important."))
    add(p("Groq's daily limit stopped generation after five complete pairs (10/20 planned answers); remaining answers, including controls, were not tested. All 100 final passages and 200 recorded candidates matched prepared text/metadata. A single assessor graded passages: 2 directly supports a reference fact in the requested language, 1 is related background, 0 is irrelevant/wrong-language. Precision/MRR count grade 2; answer correctness and full claim support are separate. Small samples, no blinded second rater, one generation per condition, and approximate search limit generalization. Warm timings exclude model loading and are not a controlled latency benchmark.", "SmallCopy"))
    add(p("Reproduce: evaluations/rag_evaluation/README.md and results/2026-10-15/. Method reference: <link href='https://github.com/NirDiamant/RAG_Techniques/blob/main/all_rag_techniques/reranking.ipynb' color='#146B73'>NirDiamant RAG_Techniques - Reranking</link> (accessed 15 October 2026). Answer comparisons do not establish improved autonomous coding pass rates.", "SmallCopy"))
    add(PageBreak())

    # Page 4: reflection, provenance, and how to locate supporting work.
    add(p("4. Reflection and supporting evidence", "SectionTitle"))
    add(p("What worked", "Subhead"))
    add(p("The provider-neutral loop connected the required tools and retained code/trace evidence. Several coding attempts saved correct implementations. The measured RAG comparison shows useful changes in passage ordering and answer grounding. Final regression checks passed 249 tests; strict type checking passed for 65 files."))
    add(p("What did not work", "Subhead"))
    add(p("Incorrect tool names, null arguments, malformed output, long histories, and quotas interrupted tasks. Windows line-ending mismatches could damage indentation. Tool success did not imply correct code: a later 120B feature mishandled Unicode when enforcing ASCII words. Retrieval sometimes returned related but insufficient evidence; scanned PDF pages limited corpus coverage."))
    add(p("Changes made and what we would improve", "Subhead"))
    add(p("Implemented fixes include tool aliases, null cleanup, bounded recovery, context compaction, Windows-edit normalization, and the correct RAG interpreter. Free-tier controls pace requests and checkpoint for resume. Python edits receive policy-controlled reads and syntax checks; failures feed back for repair and block normal completion. Syntax checks do not prove behavior."))
    add(p("The final deliverables add a separate MCP tool for trusted Python scripts or pytest, with visible approval, exit status, timeouts, and bounded returned output. It is a building block for behavioral checks, not proof of adequate test coverage. The measured RAG comparison now evaluates relevance, answer facts, and citation grounding. Next we would complete the current-policy coding retest, improve corpus coverage/source filtering, and use more queries, repeated generations, and independent blinded raters. Groq quotas and outages remain outside the project."))
    add(p("Evidence index (paths relative to repository root)", "Subhead"))
    add(table([
        ["Evidence", "Location"],
        ["24-run baseline and saved code", "evaluations/model_comparison/results/2026-10-15/"],
        ["Fixes, 16 diagnostic runs, final-policy hashes", "evaluations/model_comparison/results/2026-10-15-fixes/"],
        ["Measured RAG comparison and answer judgments", "evaluations/rag_evaluation/README.md; results/2026-10-15/"],
        ["Free-tier controls and syntax validation", "evaluations/model_comparison/FREE_TIER_TESTING_NOTES.md"],
        ["Original planning architecture (p. 5)", "init-architecture.drawio2.pdf"],
        ["Current structure and configuration (p. 6)", "docs/architecture.md; config/mcp.json; src/coding_assistant/; rag_server/"],
    ], [188, 328]))
    add(Spacer(1, 8))
    add(p("The coding baseline evaluated commit 6e4735d; later fixes have retained source hashes. The RAG experiment records base commit 031edeb plus executed source hashes. Later command-tool additions were not part of those coding trials. The video demo remains a separate deliverable for the team. Page 5 reproduces the original planning PDF unchanged.", "SmallCopy"))
    add(PageBreak())

    # The original PDF will be inserted immediately before this generated page.
    add(p("5. Updated architecture", "SectionTitle"))
    add(p("The original planning diagram appears on page 5. This diagram shows the final system, including reliability changes and the Python-check server. It preserves the planned CLI, agent, MCP client, and three required server roles."))
    add(Architecture())
    add(p("What changed from the plan, and why", "Subhead"))
    add(p("<b>Model boundary made explicit.</b> Groq/Ollama adapters sit outside the agent's coordination logic so models can change without replacing the tool pipeline. The planning diagram did not show this boundary."))
    add(p("<b>Execution checks added explicitly.</b> Discovered tool names, schemas, and confirmation policy sit before MCP calls. Provider-side aliases, context budgeting, and retries address the failures observed during evaluation."))
    add(p("<b>RAG design made concrete.</b> The plan's generic retrieval/vector-database branches became an offline ingestion/index build and a query-time cosine-plus-cross-encoder pipeline. Answer generation remains in the main agent/provider; the RAG server returns evidence. Chroma and reranking were chosen to reuse vectors and improve passage ordering."))
    add(p("<b>Deployment boundaries clarified.</b> Filesystem and RAG are local stdio processes; DeepWiki is hosted over HTTP. The RAG executable follows the running Python interpreter to avoid missing dependencies. These refinements explain how the original architecture became executable."))
    add(p("<b>Command execution added.</b> A separate local Python-check MCP server runs trusted scripts/tests with per-call policy, target validation, time limits, credential-environment omission, and bounded returned output. This fills the assignment's command-execution capability without adding a shell interface. It is not an OS sandbox."))
    add(PageBreak())
    add(p("6. Task state diagram", "SectionTitle"))
    add(p("The state flow combines user input, model decisions, validation, approval, MCP execution, feedback, and completion. See docs/diagrams.md for editable Mermaid sources and error branches."))
    add(StateDiagram())
    add(p("The CLI can run many tasks in one session. One-shot mode exits after its task. All clients close on exit. The LLM sees full tool results through the agent; the Groq adapter may compact the request view. Python syntax feedback is added after writes, while optional behavioral execution is a distinct checks.run_python_check tool call."))
    for title, subtitle, actors, messages, note in SCENARIOS:
        add(PageBreak())
        add(p(title, "SectionTitle"))
        add(p(subtitle, "Deck"))
        add(SequenceDiagram(actors, messages))
        add(Spacer(1, 8))
        add(p(note, "SmallCopy"))
        if "Repair" in title:
            add(p("The optional Python-check call shown here was added after the recorded coding comparison. Test completeness and assertions determine what a passing check means.", "SmallCopy"))

    doc = SimpleDocTemplate(str(body), pagesize=(612, 792), leftMargin=48,
                            rightMargin=48, topMargin=43, bottomMargin=53,
                            title="Juniper - Group Project 2 Report", author="Group Project 2")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    generated = PdfReader(body)
    if len(generated.pages) != 9:
        raise ValueError(f"Expected 9 authored pages, got {len(generated.pages)}")
    original_path = ROOT / "init-architecture.drawio2.pdf"
    original = PdfReader(original_path)
    if len(original.pages) != 1:
        raise ValueError("Expected one original architecture page")
    writer = PdfWriter()
    for page in generated.pages[:4]:
        writer.add_page(page)
    writer.add_page(original.pages[0])
    for page in generated.pages[4:]:
        writer.add_page(page)
    writer.add_metadata({"/Title": "Juniper - Group Project 2 Report",
                         "/Author": "Group Project 2",
                         "/Subject": "System design, LLM comparison, advanced RAG, reflection, and original/updated architecture"})
    for name, index in [("System and design decisions", 0), ("Two-model comparison", 1),
                        ("Advanced RAG", 2), ("Reflection and evidence", 3),
                        ("Original planning architecture", 4), ("Updated architecture", 5),
                        ("Task state diagram", 6), ("Inspect code sequence", 7),
                        ("Repair bug sequence", 8), ("Grounded feature sequence", 9)]:
        writer.add_outline_item(name, index)
    output = ROOT / "PROJECT_REPORT.pdf"
    with output.open("wb") as stream:
        writer.write(stream)
    print(output)


if __name__ == "__main__":
    build()
