from __future__ import annotations

from langchain_openai import OpenAIEmbeddings
from langgraph.graph import StateGraph, START, END
from typing import Annotated, Any, Dict, Optional, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_google_genai import ChatGoogleGenerativeAI , GoogleGenerativeAIEmbeddings
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
import sqlite3
import requests
import contextvars
from contextlib import contextmanager

import tempfile

from dotenv import load_dotenv
import os

load_dotenv()

print("Google Generative AI token loaded:",bool(os.getenv("GEMINI_API_KEY")))

    
#-------------------------------------------------------------------------
#My LLM model
llm = ChatGoogleGenerativeAI(model="gemini-3.6-flash",temperature=0.2, google_api_key=os.getenv("GEMINI_API_KEY"))
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=os.getenv("GEMINI_API_KEY"))

def _get_retriever(thread_id: Optional[str]):
    """Fetch the retriever for a thread if available."""
    if thread_id and thread_id in _THREAD_RETRIEVERS:
        return _THREAD_RETRIEVERS[thread_id]
    return None


def ingest_pdf(file_bytes: bytes, thread_id: str, filename: Optional[str] = None) -> dict:
    """
    Build a FAISS retriever for the uploaded PDF and store it for the thread.

    Returns a summary dict that can be surfaced in the UI.
    """
    if not file_bytes:
        raise ValueError("No bytes received for ingestion.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(file_bytes)
        temp_path = temp_file.name

    try:
        loader = PyPDFLoader(temp_path)
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200, separators=["\n\n", "\n", " ", ""]
        )
        chunks = splitter.split_documents(docs)

        vector_store = FAISS.from_documents(chunks, embeddings)
        retriever = vector_store.as_retriever(
            search_type="similarity", search_kwargs={"k": 4}
        )

        _THREAD_RETRIEVERS[str(thread_id)] = retriever
        _THREAD_METADATA[str(thread_id)] = {
            "filename": filename or os.path.basename(temp_path),
            "documents": len(docs),
            "chunks": len(chunks),
        }

        return {
            "filename": filename or os.path.basename(temp_path),
            "documents": len(docs),
            "chunks": len(chunks),
        }
    finally:
        # The FAISS store keeps copies of the text, so the temp file is safe to remove.
        try:
            os.remove(temp_path)
        except OSError:
            pass

        # this function ingests a PDF file, splits it into chunks, creates a FAISS retriever for the thread, and stores metadata about the ingestion. It returns a summary dictionary that can be used in the UI to display information about the uploaded PDF.
# --------------------------------------------------
# PDF retriever store (per thread)
_THREAD_RETRIEVERS: Dict[str, Any] = {}
_THREAD_METADATA: Dict[str, dict] = {}

# Tracks the active chat thread so tools that need per-thread state (e.g. the
# PDF retriever) can resolve the right one. The frontend sets this via
# `set_current_thread_id` before invoking the graph for a turn.
current_thread_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_thread_id", default=None
)


@contextmanager
def set_current_thread_id(thread_id: Optional[str]):
    token = current_thread_id.set(str(thread_id) if thread_id is not None else None)
    try:
        yield
    finally:
        current_thread_id.reset(token)

    
# -----------------------------------------------------------------------------------
# my tools 
search_tool = DuckDuckGoSearchRun(region="us-en")

@tool
def calculator(first_num: float, second_num: float, operation: str) -> dict:
    """
    Perform a basic arithmetic operation on two numbers.
    Supported operations: add, sub, mul, div
    """
    try:
        if operation == "add":
            result = first_num + second_num
        elif operation == "sub":
            result = first_num - second_num
        elif operation == "mul":
            result = first_num * second_num
        elif operation == "div":
            if second_num == 0:
                return {"error": "Division by zero is not allowed"}
            result = first_num / second_num
        else:
            return {"error": f"Unsupported operation '{operation}'"}
        
        return {"first_num": first_num, "second_num": second_num, "operation": operation, "result": result}
    except Exception as e:
        return {"error": str(e)}




@tool
def get_stock_price(symbol: str) -> dict:
    """
    Fetch latest stock price for a given symbol (e.g. 'AAPL', 'TSLA')
    using Alpha Vantage with API key from the ALPHAVANTAGE_API_KEY env var.
    """
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return {"error": "ALPHAVANTAGE_API_KEY is not set in the environment."}
    url = (
        "https://www.alphavantage.co/query"
        f"?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
    )
    r = requests.get(url, timeout=10)
    return r.json()

import pymupdf

@tool
def read_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file.
    """
    try:
        doc = pymupdf.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text[:50000]
    except Exception as e:
        return f"PDF reading error: {str(e)}"


import pandas as pd
import os

@tool
def analyze_file(file_path: str) -> dict:
    """
    Analyze CSV or Excel files and return dataset information.
    """

    try:

        extension = os.path.splitext(file_path)[1].lower()

        if extension == ".csv":
            df = pd.read_csv(file_path)

        elif extension in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)

        elif extension == ".json":
            df = pd.read_json(file_path)

        else:
            return {"error": "Unsupported file format"}

        return {
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": df.columns.tolist(),
            "data_types": df.dtypes.astype(str).to_dict(),
            "missing_values": df.isnull().sum().to_dict(),
            "summary": df.describe(include="all").to_dict()
        }

    except Exception as e:
        return {"error": str(e)}



import matplotlib.pyplot as plt
import uuid as _uuid

_OUTPUT_DIR = "generated"
os.makedirs(_OUTPUT_DIR, exist_ok=True)


@tool
def create_visualization(file_path: str, column: str, chart_type: str) -> str:
    """
    Create a visualization from a CSV file and return its absolute path.

    Each call writes to a fresh file in the 'generated/' directory so concurrent
    calls do not clobber each other.
    """
    try:
        df = pd.read_csv(file_path)

        plt.figure(figsize=(10, 6))

        if chart_type == "histogram":
            df[column].hist()

        elif chart_type == "line":
            plt.plot(df[column])

        elif chart_type == "bar":
            df[column].value_counts().plot(kind="bar")

        elif chart_type == "boxplot":
            df.boxplot(column=column)

        else:
            plt.close()
            return "Unsupported chart type"

        output = os.path.abspath(os.path.join(_OUTPUT_DIR, f"chart_{_uuid.uuid4().hex[:8]}.png"))
        plt.savefig(output)
        plt.close()

        return output

    except Exception as e:
        return f"Visualization error: {str(e)}"

import ast
import signal
import io
import contextlib

# Modules the sandbox refuses outright. Kept narrow on purpose: the executor is
# meant for quick snippets (math, small data transforms), not for shelling out.
_SANDBOX_DENY_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket", "http", "urllib",
    "requests", "ftplib", "smtplib", "ssl", "asyncio", "multiprocessing",
    "ctypes", "cffi", "importlib", "pkgutil", "pathlib", "glob", "tempfile",
    "pickle", "shelve", "code", "codeop", "compileall", "py_compile",
    "webbrowser", "antigravity", "this",
}


class _SandboxTimeout(Exception):
    pass


def _sandbox_alarm(_signum, _frame):
    raise _SandboxTimeout("Execution exceeded 5s timeout.")


def _validate_sandbox_code(code: str) -> str:
    """Reject code that imports blocked modules or uses dangerous builtins.

    Returns an error message string if the code should be refused, or '' if OK.
    """
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    for node in ast.walk(tree):
        # Block 'import x' and 'from x import y' for dangerous modules.
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _SANDBOX_DENY_MODULES:
                    return f"Import of '{root}' is not allowed in the sandbox."
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in _SANDBOX_DENY_MODULES:
                    return f"Import from '{root}' is not allowed in the sandbox."

        # Block dunder access to bypass builtins.
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            return f"Access to dunder attribute '{node.attr}' is not allowed."

        # Block file open() and exec()/eval() outright.
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint"}:
                return f"Call to '{name}' is not allowed in the sandbox."

    return ""


_SAFE_BUILTINS = {
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "callable", "chr", "complex", "dict", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "hash", "hex", "id", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next", "object",
    "oct", "ord", "pow", "print", "range", "repr", "reversed", "round",
    "set", "slice", "sorted", "str", "sum", "tuple", "type", "vars", "zip",
    "True", "False", "None", "Exception", "ValueError", "TypeError",
    "KeyError", "IndexError", "RuntimeError", "StopIteration", "ZeroDivisionError",
    # __import__ is the only path to import statements; the AST gate is what
    # actually keeps the sandbox safe. It rejects os/subprocess/networking
    # before any of this runs.
    "__import__",
}


@tool
def python_executor(code: str) -> str:
    """
    Execute a small Python snippet in a restricted sandbox.

    Imports of os/sys/subprocess/networking and calls to open/exec/eval are
    rejected. Execution is wall-clock-limited to 5 seconds. The tool captures
    stdout and returns it so the model can read the result.
    """
    rejection = _validate_sandbox_code(code)
    if rejection:
        return rejection

    stdout_buffer = io.StringIO()
    sandbox_globals = {"__builtins__": {k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k) for k in _SAFE_BUILTINS}}
    sandbox_locals: dict = {}

    # SIGALRM is the standard POSIX timeout mechanism. It is not available on
    # Windows; on Windows we skip the signal and rely on the AST/import checks
    # for safety.
    use_signal = hasattr(signal, "SIGALRM") and hasattr(signal, "alarm")
    previous_handler = None
    if use_signal:
        previous_handler = signal.signal(signal.SIGALRM, _sandbox_alarm)
        signal.alarm(5)

    try:
        with contextlib.redirect_stdout(stdout_buffer):
            exec(compile(code, "<sandbox>", "exec"), sandbox_globals, sandbox_locals)
        output = stdout_buffer.getvalue()
        return output if output else "Code executed successfully (no output)."
    except _SandboxTimeout as e:
        return f"TimeoutError: {e}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    finally:
        if use_signal:
            signal.alarm(0)
            if previous_handler is not None:
                signal.signal(signal.SIGALRM, previous_handler)

    

from github import Github, Auth

auth = Auth.Token(os.getenv("GITHUB_TOKEN"))

github = Github(auth=auth)

@tool
def github_search(query: str) -> list:
    """
    Search GitHub repositories.
    """
    try:
        repos = github.search_repositories(query)
        results = []
        for repo in repos[:5]:

            results.append({
                "name": repo.full_name,
                "description": repo.description,
                "stars": repo.stargazers_count,
                "url": repo.html_url})
        return results

    except Exception as e:
        return {"error": str(e)}


from geopy.geocoders import Nominatim

geolocator = Nominatim(user_agent="my_chatbot")

@tool
def find_place(place: str) -> dict:
    """
    Find geographical information for a place.
    """
    try:
        location = geolocator.geocode(place)

        if location is None:
            return {"error": "Place not found"}

        return {
            "address": location.address,
            "latitude": location.latitude,
            "longitude": location.longitude}
        
    except Exception as e:
        return {"error": str(e)}

tools = [search_tool, get_stock_price, calculator, read_pdf, analyze_file, create_visualization, python_executor, github_search, find_place]


@tool
def search_uploaded_pdf(query: str) -> str:
    """
    Search the PDF that was uploaded in the current chat thread.

    Returns the top-matching passages from the indexed PDF, or an error if no
    PDF has been uploaded for this thread yet. Use this when the user asks a
    question that should be answered from their uploaded document.
    """
    thread_id = current_thread_id.get()
    if not thread_id:
        return "No active chat thread; cannot resolve a PDF retriever."

    retriever = _get_retriever(thread_id)
    if retriever is None:
        meta = _THREAD_METADATA.get(str(thread_id))
        if meta:
            return (
                f"A PDF named '{meta.get('filename')}' was indexed for this thread, "
                "but the retriever is no longer available (it lives in process "
                "memory and the backend was likely restarted). Please re-upload."
            )
        return "No PDF has been uploaded in this chat yet."

    try:
        docs = retriever.invoke(query)
    except Exception as e:
        return f"Retriever error: {e}"

    if not docs:
        return "No relevant passages found in the uploaded PDF."

    return "\n\n---\n\n".join(
        f"[page {getattr(d, 'metadata', {}).get('page', '?')}] {d.page_content}"
        for d in docs
    )


# Final tools list: includes search_uploaded_pdf so both the LLM and the
# ToolNode know about it.
tools = tools + [search_uploaded_pdf]
llm_with_tools = llm.bind_tools(tools)

# -------------------------------------------------------------------------------------------------------
#My State
from langgraph.graph.message import add_messages

class ChatState(TypedDict):

    messages: Annotated[list[BaseMessage], add_messages]
    # add_maggage is a reducer function that adds messages to the state. It takes a list of BaseMessage objects and appends them to the existing messages in the state.


# -----------------------------------------------------------------------------------------------------
# MY graph node
def chat_node(state: ChatState):
    """LLM node that may answer or request a tool call."""
    messages = state["messages"]
     #  send to llm with tools
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

tool_node = ToolNode(tools)
# ---------------------------------------------------------------------------------------------------------------------
# CHECKPOINTER
conn = sqlite3.connect(database='chatbot.db', check_same_thread=False)  # Create the database file if it doesn't exist
# Initialize title persistence table
conn.execute("CREATE TABLE IF NOT EXISTS thread_titles (thread_id TEXT PRIMARY KEY, title TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
conn.commit()

# Migration: Ensure created_at column exists
cursor = conn.execute("PRAGMA table_info(thread_titles)")
columns = [row[1] for row in cursor.fetchall()]
if "created_at" not in columns:
    try:
        conn.execute("ALTER TABLE thread_titles ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        conn.commit()
    except sqlite3.OperationalError:
        pass

# check same tread is set to False to allow multiple threads to access the database concurrently.


# Checkpointer
checkpointer = SqliteSaver(conn=conn)

# ---------------------------------------------------------------------------------------------------------
# MY GRAPH

graph = StateGraph(ChatState)

# add nodes
graph.add_node("chat_node", chat_node)
graph.add_node("tools", tool_node)

graph.add_edge(START, "chat_node")

graph.add_conditional_edges("chat_node",tools_condition)
graph.add_edge('tools', 'chat_node')

chatbot = graph.compile(checkpointer=checkpointer)

# ---------------------------------------------------------------------------
# helper
def retrieve_all_threads():
    """Retrieve all existing chat threads with their creation timestamps."""
    all_threads = set()
    for checkpoint in checkpointer.list(None):
        config = checkpoint.config
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            all_threads.add(str(thread_id))

    results = []
    for tid in all_threads:
        try:
            cursor = conn.execute("SELECT created_at FROM thread_titles WHERE thread_id = ?", (tid,))
            row = cursor.fetchone()
            created_at = row[0] if row else None
        except sqlite3.OperationalError:
            # Handle case where created_at column might still be missing
            created_at = None
        results.append((tid, created_at))
    return results

    # this function retrieves all the existing chat threads from the database along with their creation timestamps.
    # It returns a list of (thread_id, created_at) tuples.


def thread_has_document(thread_id: str) -> bool:
    return str(thread_id) in _THREAD_RETRIEVERS


def thread_document_metadata(thread_id: str) -> dict:
    return _THREAD_METADATA.get(str(thread_id), {})

def set_thread_title(thread_id: str, title: str):
    """Persist a custom title for a thread, preserving the creation timestamp."""
    thread_id_str = str(thread_id)
    conn.execute(
        "INSERT INTO thread_titles (thread_id, title) VALUES (?, ?) "
        "ON CONFLICT(thread_id) DO UPDATE SET title=excluded.title",
        (thread_id_str, title)
    )
    conn.commit()

def get_persisted_title(thread_id: str) -> Optional[str]:
    """Retrieve a persisted title for a thread."""
    thread_id_str = str(thread_id)
    cursor = conn.execute("SELECT title FROM thread_titles WHERE thread_id = ?", (thread_id_str,))
    row = cursor.fetchone()
    return row[0] if row else None

def delete_thread(thread_id: str):
    """
    Permanently delete a thread's checkpoints and titles from the database.
    Uses a robust approach that only attempts deletion from tables that exist.
    """
    thread_id_str = str(thread_id)

    # Tables that LangGraph SqliteSaver might use
    potential_tables = ["checkpoints", "checkpoint_blobs", "writes"]

    for table in potential_tables:
        try:
            conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id_str,))
        except sqlite3.OperationalError:
            # Table might not exist in this version of LangGraph or hasn't been created yet
            pass

    # Delete custom title
    try:
        conn.execute("DELETE FROM thread_titles WHERE thread_id = ?", (thread_id_str,))
    except sqlite3.OperationalError:
        pass

    conn.commit()


# python langgraph_backend.py