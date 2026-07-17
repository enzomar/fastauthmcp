"""Main TUI application for the FastAuthMCP Lab.

Layout:
┌──────────────┬──────────────────────────────────┐
│  Config      │         Chat                     │
│  Panel       │                                  │
│              │                                  │
│  - Scenario  │  User: ...                       │
│  - LLM       │  Assistant: ...                  │
│  - API Key   │  [Tool Call: whoami()]            │
│              │  [Tool Result: {...}]             │
│              │                                  │
├──────────────┴──────────────────────────────────┤
│  Logs (searchable)                              │
└─────────────────────────────────────────────────┘

Run with: python -m fastauthmcp.lab.ui
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.css.query import NoMatches
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    Log,
    Select,
    Static,
)

from fastauthmcp.lab.ui.chat import ChatEngine
from fastauthmcp.lab.ui.scenarios import SCENARIOS


class LabApp(App):
    """FastAuthMCP Lab — Interactive MCP Chat with LLM."""

    TITLE = "FastAuthMCP Lab"
    SUB_TITLE = "Security & Interoperability"

    CSS = """
    #app-grid {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 1fr 3fr;
        grid-rows: 3fr 1fr;
    }
    #config-panel {
        row-span: 1;
        border: solid $primary;
        padding: 1;
        overflow-y: auto;
    }
    #chat-panel {
        row-span: 1;
        border: solid $secondary;
    }
    #log-panel {
        column-span: 2;
        border: solid $surface;
    }
    #chat-messages {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    #chat-input {
        dock: bottom;
        margin-top: 1;
    }
    #log-search {
        dock: top;
        width: 100%;
    }
    #log-output {
        height: 1fr;
    }
    .config-label {
        margin-top: 1;
        color: $text-muted;
        text-style: bold;
    }
    .message-user {
        color: $success;
        margin-bottom: 1;
    }
    .message-assistant {
        color: $primary;
        margin-bottom: 1;
    }
    .message-tool {
        color: $warning;
        margin-bottom: 1;
        padding-left: 2;
    }
    .message-error {
        color: $error;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._engine: ChatEngine | None = None
        self._log_entries: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="app-grid"):
            # Left: Config panel
            with Vertical(id="config-panel"):
                yield Label("⚙ Configuration", classes="config-label")
                yield Label("Scenario")
                yield Select(
                    [(s.label, s.id) for s in SCENARIOS],
                    id="scenario-select",
                    value=SCENARIOS[0].id if SCENARIOS else None,
                )
                yield Label("LLM Provider", classes="config-label")
                yield Select(
                    [
                        ("OpenAI (gpt-4o)", "openai"),
                        ("OpenRouter", "openrouter"),
                        ("GitHub Models", "github"),
                        ("Anthropic (Claude)", "anthropic"),
                        ("Ollama (local)", "ollama"),
                    ],
                    id="llm-select",
                    value="openai",
                )
                yield Label("Model")
                yield Input(
                    placeholder="gpt-4o",
                    id="model-input",
                    value="gpt-4o",
                )
                yield Label("API Key", classes="config-label")
                yield Input(
                    placeholder="sk-... or ghp-...",
                    id="apikey-input",
                    password=True,
                )
                yield Label("Base URL (optional)", classes="config-label")
                yield Input(
                    placeholder="https://api.openai.com/v1",
                    id="baseurl-input",
                )
                yield Label("─" * 20)
                yield Label("Identity (from scenario)", classes="config-label")
                yield Static("No scenario loaded", id="identity-display")

            # Center: Chat panel
            with Vertical(id="chat-panel"):
                yield Vertical(id="chat-messages")
                yield Input(
                    placeholder="Ask the LLM to use tools... (Enter to send)",
                    id="chat-input",
                )

            # Bottom: Log panel
            with Vertical(id="log-panel"):
                yield Input(placeholder="🔍 Search logs...", id="log-search")
                yield Log(id="log-output", highlight=True, max_lines=500)

        yield Footer()

    def on_mount(self) -> None:
        self._emit_log("Lab UI started. Select a scenario and configure LLM to begin.")
        self._update_scenario()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "scenario-select":
            self._update_scenario()
        elif event.select.id == "llm-select":
            self._update_llm_defaults()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chat-input":
            message = event.value.strip()
            if message:
                event.input.value = ""
                self._send_message(message)
        elif event.input.id == "log-search":
            self._filter_logs(event.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "log-search":
            self._filter_logs(event.value)

    def action_clear_chat(self) -> None:
        try:
            container = self.query_one("#chat-messages", Vertical)
            container.remove_children()
        except NoMatches:
            pass
        self._emit_log("Chat cleared")

    # ─── Internal ────────────────────────────────────────────────────────

    def _update_scenario(self) -> None:
        try:
            select = self.query_one("#scenario-select", Select)
            scenario_id = select.value
            if scenario_id is None:
                return

            scenario = next((s for s in SCENARIOS if s.id == scenario_id), None)
            if scenario is None:
                return

            identity_display = self.query_one("#identity-display", Static)
            identity_display.update(
                f"sub: {scenario.identity.get('sub', 'N/A')}\n"
                f"email: {scenario.identity.get('email', 'N/A')}\n"
                f"roles: {scenario.identity.get('roles', [])}"
            )
            self._emit_log(f"Scenario: {scenario.label} (provider: {scenario.provider})")
        except NoMatches:
            pass

    def _update_llm_defaults(self) -> None:
        try:
            llm_select = self.query_one("#llm-select", Select)
            model_input = self.query_one("#model-input", Input)
            baseurl_input = self.query_one("#baseurl-input", Input)

            defaults = {
                "openai": ("gpt-4o", "https://api.openai.com/v1"),
                "openrouter": ("openai/gpt-4o", "https://openrouter.ai/api/v1"),
                "github": ("gpt-4o", "https://models.inference.ai.azure.com"),
                "anthropic": ("claude-sonnet-4-20250514", "https://api.anthropic.com/v1"),
                "ollama": ("llama3.2", "http://localhost:11434/v1"),
            }
            provider = llm_select.value
            if provider in defaults:
                model, base_url = defaults[provider]
                model_input.value = model
                baseurl_input.value = base_url
        except NoMatches:
            pass

    def _send_message(self, message: str) -> None:
        self._add_chat_message("user", message)
        self._emit_log(f"User: {message}")
        asyncio.create_task(self._process_message(message))

    async def _process_message(self, message: str) -> None:
        try:
            engine = self._get_engine()
            self._emit_log("Sending to LLM...")

            async for event in engine.chat(message):
                if event["type"] == "text":
                    self._add_chat_message("assistant", event["content"])
                elif event["type"] == "tool_call":
                    self._add_chat_message(
                        "tool",
                        f"🔧 Tool Call: {event['name']}({event.get('args', '')})",
                    )
                    self._emit_log(f"Tool call: {event['name']}({event.get('args', '')})")
                elif event["type"] == "tool_result":
                    self._add_chat_message("tool", f"   → {event['content']}")
                    self._emit_log(f"Tool result: {event['content'][:100]}")
                elif event["type"] == "error":
                    self._add_chat_message("error", f"❌ {event['content']}")
                    self._emit_log(f"ERROR: {event['content']}")

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            self._add_chat_message("error", f"❌ {error_msg}")
            self._emit_log(f"ERROR: {error_msg}")

    def _get_engine(self) -> ChatEngine:
        try:
            scenario_select = self.query_one("#scenario-select", Select)
            llm_select = self.query_one("#llm-select", Select)
            model_input = self.query_one("#model-input", Input)
            apikey_input = self.query_one("#apikey-input", Input)
            baseurl_input = self.query_one("#baseurl-input", Input)

            scenario_id = scenario_select.value
            scenario = next((s for s in SCENARIOS if s.id == scenario_id), None)

            return ChatEngine(
                provider=str(llm_select.value or "openai"),
                model=model_input.value or "gpt-4o",
                api_key=apikey_input.value,
                base_url=baseurl_input.value or None,
                scenario=scenario,
            )
        except NoMatches:
            return ChatEngine()

    def _add_chat_message(self, role: str, content: str) -> None:
        try:
            container = self.query_one("#chat-messages", Vertical)
            prefix = {"user": "👤", "assistant": "🤖", "tool": "  ", "error": "❌"}.get(role, "")
            css_class = f"message-{role}"
            widget = Static(f"{prefix} {content}", classes=css_class)
            container.mount(widget)
            widget.scroll_visible()
        except NoMatches:
            pass

    def _emit_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self._log_entries.append(entry)
        try:
            log_widget = self.query_one("#log-output", Log)
            log_widget.write_line(entry)
        except NoMatches:
            pass

    def _filter_logs(self, query: str) -> None:
        try:
            log_widget = self.query_one("#log-output", Log)
            log_widget.clear()
            for entry in self._log_entries:
                if not query or query.lower() in entry.lower():
                    log_widget.write_line(entry)
        except NoMatches:
            pass


def main() -> None:
    app = LabApp()
    app.run()


if __name__ == "__main__":
    main()
