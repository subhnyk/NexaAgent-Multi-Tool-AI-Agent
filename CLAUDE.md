# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A Streamlit chatbot that fronts a LangGraph agent powered by Google Gemini. The agent can answer directly or call tools (web search, calculator, stock price, PDF reader, file analyzer, chart generator, Python executor, GitHub search, geocoder). Per-thread PDF RAG uses FAISS over Gemini embeddings. Conversation state is persisted via a SQLite checkpointer.

## Run

The repo's two source files live at the repo root (the README's reference to an `app/` subfolder does not match the actual layout — files are `langgraph_backend.py` and `streamlit_frountend.py` at the top level, and the frontend filename is misspelled).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
streamlit run streamlit_frountend.py
```

There is no test suite, linter config, or build step. The `requirements.txt` includes `langchain-openai` but the project only uses `langchain-google-genai`; the import is dead weight unless the embedding fallback in `langgraph_backend.py:3` is exercised.

## Environment

Required in `.env` (do not commit):

- `GEMINI_API_KEY` — used for the LLM and embeddings
- `GITHUB_TOKEN` — used by the GitHub search tool (anonymous mode is not configured)
- `ALPHAVANTAGE_API_KEY` — *not* required today; the `get_stock_price` tool at `langgraph_backend.py:130` has the key hardcoded in the URL. Replace it with `os.getenv("ALPHAVANTAGE_API_KEY")` before relying on the tool in any other context, and rotate the leaked key.

Optional LangSmith tracing: `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`.

## Architecture

Two files, no package:

- **`langgraph_backend.py`** — defines the LLM (`ChatGoogleGenerativeAI`), the FAISS-based PDF RAG pipeline, the tool list, the LangGraph `StateGraph`, the SQLite checkpointer, and a small helper API (`retrieve_all_threads`, `ingest_pdf`, `thread_document_metadata`). Importing this module opens a SQLite connection to `chatbot.db` and instantiates the global `chatbot` graph — the Streamlit frontend imports these as side effects.
- **`streamlit_frountend.py`** — Streamlit UI. Manages `st.session_state` for `thread_id`, `message_history`, `chat_threads`, `chat_titles`, and `ingested_docs`. Renders the sidebar (new chat button, upload widget, conversation list) and the main chat panel. Calls `chatbot.stream(...)` with `stream_mode="messages"` to stream AI output and surface a `st.status` block when tool calls run.

**Graph shape** (`langgraph_backend.py:330`):

```
START → chat_node → (tools_condition) → tools → chat_node → … → END
                                      ↘ END
```

`chat_node` invokes `llm_with_tools`. `tools_condition` is the standard LangGraph prebuilt routing — if the LLM emitted a tool call, control flows to `tool_node` (a `ToolNode(tools)`), then loops back to `chat_node` until the LLM answers directly.

**State and persistence:**

- `ChatState` is a `TypedDict` with `messages: Annotated[list[BaseMessage], add_messages]`. Only the message list is checkpointed.
- The checkpointer is `SqliteSaver(conn)` over a `chatbot.db` SQLite file opened with `check_same_thread=False`. Thread IDs come from Streamlit via `chatbot.get_state(config={"configurable": {"thread_id": ...}})`.
- `retrieve_all_threads()` walks `checkpointer.list(None)` to enumerate every thread ID ever used.

**Per-thread PDF RAG:**

- `ingest_pdf(file_bytes, thread_id, filename)` writes the upload to a temp file, splits with `RecursiveCharacterTextSplitter` (1000/200), builds an in-memory FAISS store, and stashes the retriever in two module-level dicts: `_THREAD_RETRIEVERS[thread_id]` and `_THREAD_METADATA[thread_id]`. The temp file is deleted once the embeddings are in memory.
- These dicts live in process memory only — restarting the backend or running multiple workers will lose retrievers. The SQLite thread history persists; the FAISS indices do not.
- No tool currently calls these retrievers. The graph can answer from a PDF only if the model decides to ask the user to re-upload, or if a future tool is added that calls `_get_retriever(thread_id)` and feeds the results back into the chat node.

**Tools** (`langgraph_backend.py:296`): `search_tool` (DuckDuckGo), `calculator`, `get_stock_price` (Alpha Vantage — key hardcoded), `read_pdf` (PyMuPDF), `analyze_file` (CSV/Excel/JSON via pandas), `create_visualization` (matplotlib; only CSV, output goes to `output_chart.png` in CWD), `python_executor` (`exec` — unconstrained), `github_search` (PyGithub), `find_place` (geopy/Nominatim).

## Gotchas

- `streamlit_frountend.py` is misspelled (no `e` in "frontend"). The launch command above uses the actual filename. Don't rename it without also updating the README and any deployment config.
- `llm = ChatGoogleGenerativeAI(model="gemini-3.6-flash", ...)` at `langgraph_backend.py:30` — there is no Gemini 3.6 model. This will fail at first call. Should be `gemini-1.5-flash` (or the current production model ID).
- `get_stock_price` has a hardcoded Alpha Vantage API key in the URL string. Treat the key as compromised; rotate it.
- `python_executor` runs `exec(code)` with no sandbox. The LLM can be prompted to call it with arbitrary code.
- `create_visualization` always writes to `output_chart.png` in the current working directory, overwriting on every call. Multiple parallel invocations will race.
- The frontend duplicates the upload widget — there's a commented-out block at `streamlit_frountend.py:120` and the live one at `:138`. Only the live block runs.
- The "uploaded file" path is injected into the LLM prompt as a literal string (`streamlit_frountend.py:299`), not via the retriever or a tool argument. Long absolute paths will eat context window.
- `chatbot.db` is created on first import of `langgraph_backend.py`. Deleting it wipes all conversation history. The `.gitignore` excludes it.
