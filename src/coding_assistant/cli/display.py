"""Terminal presentation, separate from model requests and tool execution."""

from __future__ import annotations

import os
import json
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TextIO

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


ASSISTANT_NAME = "Juniper"


class TerminalView:
    """Use styled panels in a terminal and readable text in captured output."""

    def __init__(self, output: TextIO) -> None:
        self.output = output
        self.interactive = output.isatty()
        self.console = Console(
            file=output,
            force_terminal=self.interactive,
            color_system=None if "NO_COLOR" in os.environ else "auto",
            highlight=False,
        )

    def welcome(self, workspace: Path, provider: str, model: str, servers: int,
                execution: str = "Automatic tool execution") -> None:
        try:
            release = version("coding-assistant")
        except PackageNotFoundError:
            release = "development"
        details = (
            f"Workspace  {workspace}\n"
            f"Provider   {provider}\n"
            f"Model      {model}\n"
            f"MCP        {servers} connected server(s)\n"
            f"Version    {release}\n"
            f"Execution  {execution}"
        )
        if self.interactive:
            table = Table.grid(padding=(0, 1))
            table.add_column(style="dim", width=10, no_wrap=True)
            table.add_column(overflow="fold")
            for label, value in (("Workspace", str(workspace)), ("Provider", provider),
                                 ("Model", model), ("MCP", f"{servers} connected server(s)"),
                                 ("Version", release), ("Execution", execution)):
                table.add_row(Text(label), Text(value))
            self.console.print(Panel(
                table,
                title=Text(f"{ASSISTANT_NAME}  |  AI Coding Assistant", style="bold cyan"),
                border_style="cyan", padding=(1, 2),
            ))
        else:
            print(f"{ASSISTANT_NAME} | AI Coding Assistant\n{details}", file=self.output)

    def tool(self, name: str, arguments: object) -> None:
        if arguments is None:
            body = ""
        elif self.interactive and isinstance(arguments, Mapping):
            parts = []
            for key, value in arguments.items():
                if isinstance(value, str):
                    parts.append(f"{key}:\n{value}" if "\n" in value else f"{key}: {value}")
                else:
                    parts.append(f"{key}: {json.dumps(value, ensure_ascii=False, default=str)}")
            body = "\n".join(parts)
        else:
            body = json.dumps(arguments, indent=2, ensure_ascii=False, default=str)
        self.panel("Tool", name, body)

    def panel(self, label: str, name: str, body: str) -> None:
        title = f"[{label}] {name}"
        if self.interactive:
            style = "red" if "error" in label.lower() else "cyan" if label == "Tool" else "green"
            lines = body.splitlines()
            if len(lines) > 16:
                body = "\n".join(lines[:16]) + f"\n... ({len(lines) - 16} more lines)"
            self.console.print(Panel(Text(body), title=Text(title), border_style=style))
        else:
            print(title, file=self.output)
            if body:
                print(body, file=self.output)
        self.output.flush()

    def marker(self, label: str, content: str = "") -> None:
        text = f"[{label}]" + (f" {content}" if content else "")
        if self.interactive:
            style = "red" if label in {"Error", "Failed"} else "green" if label == "Done" else "cyan"
            self.console.print(Text(text, style=style))
        else:
            print(text, file=self.output)
        self.output.flush()

    def tools(self, entries: list[tuple[str, str]]) -> None:
        if not self.interactive:
            print("\n".join(f"  {name} - {description}" for name, description in entries)
                  or "  No tools available.", file=self.output)
            return
        table = Table(title="Available MCP tools", border_style="cyan")
        table.add_column("Tool", style="cyan")
        table.add_column("Description")
        for name, description in entries:
            table.add_row(Text(name), Text(description))
        if not entries:
            table.add_row("None", "No tools available.")
        self.console.print(table)
