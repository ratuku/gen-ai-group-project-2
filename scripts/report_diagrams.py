"""Vector workflow figures shared by the submission PDF builder."""

import math

from reportlab.lib import colors
from reportlab.platypus import Flowable

INK = colors.HexColor("#183344")
TEAL = colors.HexColor("#146B73")
PALE = colors.HexColor("#EAF3F4")


def arrow(canvas, x1, y1, x2, y2, dashed=False):
    canvas.setStrokeColor(INK)
    canvas.setFillColor(INK)
    canvas.setLineWidth(0.8)
    canvas.setDash(3, 2) if dashed else canvas.setDash()
    canvas.line(x1, y1, x2, y2)
    canvas.setDash()
    angle = math.atan2(y2 - y1, x2 - x1)
    shape = canvas.beginPath()
    shape.moveTo(x2, y2)
    for delta in (-0.5, 0.5):
        shape.lineTo(x2 - 5 * math.cos(angle + delta), y2 - 5 * math.sin(angle + delta))
    shape.close()
    canvas.drawPath(shape, fill=1, stroke=0)


def box(canvas, x, y, width, height, text):
    canvas.setFillColor(PALE)
    canvas.setStrokeColor(TEAL)
    canvas.roundRect(x, y, width, height, 5, fill=1, stroke=1)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica", 8)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        canvas.drawCentredString(x + width / 2, y + height / 2 + (len(lines) - 1) * 5 - i * 10 - 3, line)


class StateDiagram(Flowable):
    def __init__(self):
        super().__init__()
        self.width, self.height = 516, 430

    def draw(self):
        c = self.canv
        box(c, 183, 383, 150, 35, "Start CLI / load config")
        box(c, 183, 320, 150, 40, "Connect MCP servers\ndiscover tools")
        box(c, 183, 255, 150, 40, "Read task / request LLM\nstream text and status")
        box(c, 183, 187, 150, 40, "Tool call?\nvalidate name + schema")
        box(c, 4, 187, 142, 40, "Final text / no calls\nsyntax failures? complete/error")
        box(c, 183, 119, 150, 40, "Confirmation or auto policy\nrejection -> tool error result")
        box(c, 183, 51, 150, 40, "Execute MCP / retain result\nPython edit -> read + parse")
        box(c, 368, 187, 144, 40, "Provider or iteration limit\nshow failure; return to prompt")
        for top, bottom in ((383, 360), (320, 295), (255, 227), (187, 159), (119, 91)):
            arrow(c, 258, top, 258, bottom)
        arrow(c, 183, 275, 75, 227)
        arrow(c, 333, 275, 440, 227)
        arrow(c, 333, 71, 353, 71)
        arrow(c, 353, 71, 353, 275)
        arrow(c, 353, 275, 333, 275)
        c.setFillColor(INK)
        c.setFont("Helvetica", 7)
        c.drawString(361, 111, "observe / iterate")
        c.drawString(4, 25, "Completed or failed task -> next prompt. /exit or interruption -> close clients and exit.")
        c.drawString(4, 12, "Invalid calls return errors without execution. Groq retries are bounded inside its adapter.")


SCENARIOS = [
    ("Inspect existing code", "Confirmation mode | operation 1", ["User", "CLI", "Agent", "LLM", "Dispatch/MCP", "Filesystem"], [
        (0, 1, "Submit: explain solution.py"),
        (1, 2, "run(task); discover tool schemas"),
        (2, 3, "Messages + discovered tools"),
        (3, 2, "Select filesystem.read_text_file"),
        (2, 4, "Validate exact name and arguments"),
        (4, 1, "Request approval; show tool + path"),
        (1, 0, "Execute tool? [y/N]"),
        (0, 1, "yes"),
        (1, 4, "Approval granted for this call"),
        (4, 5, "MCP call_tool: read_text_file"),
        (5, 2, "Original code as tool result"),
        (2, 3, "Observe result; request next step"),
        (3, 2, "Stream explanation; no more calls"),
        (2, 1, "Final text + completed(answered)"),
        (1, 0, "Show Done; return to prompt"),
    ], "If approval is rejected, no filesystem call occurs. The rejection is returned to the LLM as a tool error, so it can explain or revise its plan."),
    ("Repair a Python bug", "Automatic mode | operation 2", ["User", "CLI", "Agent", "LLM", "Dispatch/MCP", "Filesystem", "Checks MCP"], [
        (0, 1, "Submit: fix mean and empty-input handling"),
        (1, 2, "run(task) with auto execution policy"),
        (2, 3, "Messages + discovered tools"),
        (3, 2, "Select filesystem.read_text_file"),
        (2, 4, "Validate; auto policy permits call"),
        (4, 5, "MCP call: read existing solution.py"),
        (5, 2, "Return existing code"),
        (2, 3, "Observe code; request next step"),
        (3, 2, "Select filesystem.edit_file or write_file"),
        (2, 4, "Validate name/schema; permit automatically"),
        (4, 5, "MCP call: save repaired source"),
        (5, 2, "Return edit result"),
        (2, 4, "After Python edit: policy-controlled read"),
        (4, 5, "Read saved source through MCP"),
        (5, 2, "Parse syntax locally; retain validation result"),
        (2, 3, "Observe edit + syntax feedback"),
        (3, 2, "Choose checks.run_python_check (pytest)"),
        (2, 4, "Validate check target; auto permit"),
        (4, 6, "stdio MCP: execute workspace tests"),
        (6, 2, "Real exit status + bounded output"),
        (2, 3, "Observe checks; repair or finish"),
        (3, 2, "Final explanation; no more tool calls"),
        (2, 1, "Complete only if syntax is verified"),
        (1, 0, "Show result; return to prompt"),
    ], "Syntax errors feed back for repair and block normal completion until resolved. The model can request the separate Python-check tool to run behavioral tests; those tests establish only what they check. Historical coding evaluation checks ran separately outside the model's writable fixture."),
    ("Implement a documented feature", "Confirmation mode | operation 3", ["User/CLI", "Agent", "LLM", "Dispatch/MCP", "Filesystem", "RAG", "DeepWiki"], [
        (0, 1, "Submit: implement a feature using documentation"),
        (1, 2, "Task + schemas from required MCP servers"),
        (2, 1, "Choose filesystem read"),
        (1, 3, "Validate; ask User/CLI for approval"),
        (0, 3, "Approve this call"),
        (3, 4, "MCP read existing code"),
        (4, 1, "Existing code result"),
        (1, 2, "Observe code; request next step"),
        (2, 1, "Choose rag.search_docs"),
        (1, 3, "Validate + per-call approval"),
        (3, 5, "MCP search: cosine -> cross-encoder"),
        (5, 1, "Original passages + source/page/ID"),
        (1, 2, "Observe passages; identify missing API detail"),
        (2, 1, "Choose deepwiki.ask_wiki_question"),
        (1, 3, "Validate + per-call approval"),
        (3, 6, "HTTP MCP: ask about public repository"),
        (6, 1, "External documentation answer"),
        (1, 2, "Observe local + external evidence"),
        (2, 1, "Choose filesystem write/edit"),
        (1, 3, "Validate + per-call approval"),
        (3, 4, "Save feature; read back for Python syntax check"),
        (4, 1, "Saved source + validation feedback"),
        (1, 2, "Request final explanation with citations"),
        (2, 1, "Final explanation + citations"),
        (1, 0, "Stream final text; complete; return to prompt"),
    ], "Each valid call, including syntax-check reads, requests approval in confirmation mode. The model chooses tools and their order; this is an implementation walkthrough, not a claim that every live task succeeds. If local evidence is insufficient, retrieve another source or acknowledge the gap."),
]


class SequenceDiagram(Flowable):
    def __init__(self, actors, messages):
        super().__init__()
        self.actors, self.messages = actors, messages
        self.width = 516
        self.height = 50 + len(messages) * 20

    def draw(self):
        c = self.canv
        step = 516 / len(self.actors)
        xs = [(i + 0.5) * step for i in range(len(self.actors))]
        top = self.height - 28
        for i, actor in enumerate(self.actors):
            box(c, i * step + 2, top, step - 4, 25, actor)
            c.setStrokeColor(colors.HexColor("#B4C8CD"))
            c.setDash(2, 3)
            c.line(xs[i], top, xs[i], 5)
            c.setDash()
        y = top - 21
        for number, (start, end, label) in enumerate(self.messages, 1):
            x1, x2 = xs[start], xs[end]
            arrow(c, x1, y, x2, y)
            text = f"{number}. {label}"
            c.setFont("Helvetica", 6.8)
            width = c.stringWidth(text, "Helvetica", 6.8)
            mid = max(width / 2 + 2, min(514 - width / 2, (x1 + x2) / 2))
            c.setFillColor(colors.white)
            c.rect(mid - width / 2 - 2, y + 2, width + 4, 9, fill=1, stroke=0)
            c.setFillColor(INK)
            c.drawCentredString(mid, y + 4, text)
            y -= 20
