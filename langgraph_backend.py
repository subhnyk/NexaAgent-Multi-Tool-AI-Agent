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
    using Alpha Vantage with API key in the URL.
    """
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey=8KOIVWKSXZHREVSX"
    r = requests.get(url)
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

@tool
def create_visualization(file_path: str,column: str,chart_type: str) -> str:
    """
    Create a visualization from a CSV file.
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
            return "Unsupported chart type"

        output = "output_chart.png"

        plt.savefig(output)
        plt.close()

        return output

    except Exception as e:
        return f"Visualization error: {str(e)}"

@tool
def python_executor(code: str) -> str:

    """
    Execute Python code.
    """

    try:
        exec(code)

        return "Code executed successfully"

    except Exception as e:
        return str(e)

    

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
    all_threads = set()

    for checkpoint in checkpointer.list(None):
        config = checkpoint.config
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            all_threads.add(thread_id)
    return list(all_threads)
    # this function retrieves all the existing chat threads from the database by listing all the checkpoints and extracting the unique thread IDs. It returns a list of thread IDs that can be used to manage multiple chat sessions.


def thread_has_document(thread_id: str) -> bool:
    return str(thread_id) in _THREAD_RETRIEVERS


def thread_document_metadata(thread_id: str) -> dict:
    return _THREAD_METADATA.get(str(thread_id), {})
# python langgraph_backend.py