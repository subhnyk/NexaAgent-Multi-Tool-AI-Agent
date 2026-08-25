# 🤖 AI Agent Chatbot

A resume-ready AI Agent Chatbot built with **LangGraph, Gemini, LangChain and Streamlit**.

The application combines conversational AI, tool calling, persistent chat history, PDF RAG, data analysis, visualization and external-service tools in one interface.

## ✨ Features

- 🤖 Gemini-powered conversational AI
- 🔀 LangGraph agent workflow with conditional tool calling
- 🧠 Persistent conversation threads using SQLite checkpointing
- 📚 PDF question answering with FAISS-based retrieval
- 📊 CSV / Excel / JSON dataset analysis
- 📈 Data visualization
- 🧮 Calculator tool
- 🌐 Web search
- 📈 Stock price lookup
- 🐙 GitHub repository search
- 📍 Geographical place lookup
- 🐍 Python code execution tool
- 📄 PDF text extraction
- ⚡ Streaming assistant responses
- 📎 File uploads through Streamlit

## 🏗️ Architecture

```text
User
  │
  ▼
Streamlit Frontend
  │
  ▼
LangGraph Chat Node
  │
  ├── Direct Answer ──────────────┐
  │                              │
  └── Tool Call                   │
          │                       │
          ▼                       │
      Tool Node                   │
          │                       │
          └──────────► Chat Node ─┘
                         │
                         ▼
                    Final Answer

Persistent State
       │
       ▼
 SQLite Checkpointer
```

## 📚 PDF RAG Pipeline

```text
PDF Upload
   ↓
PyPDFLoader
   ↓
Text Splitting
   ↓
Gemini Embeddings
   ↓
FAISS Vector Store
   ↓
Retriever
   ↓
Relevant Context
   ↓
Gemini
   ↓
Answer
```

## 🛠️ Tools

| Tool | Purpose |
|---|---|
| Web Search | Search the web |
| Calculator | Basic arithmetic |
| Stock Price | Fetch stock quote data |
| PDF Reader | Extract PDF text |
| File Analyzer | Analyze CSV / Excel / JSON |
| Visualization | Generate charts |
| Python Executor | Execute Python code |
| GitHub Search | Search GitHub repositories |
| Find Place | Geographical lookup |

## 🧰 Tech Stack

- Python
- Streamlit
- LangChain
- LangGraph
- Google Gemini
- FAISS
- SQLite
- Pandas
- Matplotlib
- PyMuPDF
- PyGithub
- Geopy

## 🚀 Installation

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd AI-Agent-Chatbot
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env`:

```bash
copy .env.example .env
```

Then add your own API keys.

**Never commit `.env` or real API keys to GitHub.**

### 5. Run the application

```bash
streamlit run app/streamlit_frontend.py
```

## 🔐 Environment Variables

```env
GEMINI_API_KEY=
GITHUB_TOKEN=
ALPHAVANTAGE_API_KEY=

LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=Chatbot Project
```

Only add credentials for services you actually use.

## 📁 Project Structure

```text
AI-Agent-Chatbot/
│
├── app/
│   ├── __init__.py
│   ├── langgraph_backend.py
│   └── streamlit_frontend.py
│
├── screenshots/
├── uploads/
│   └── .gitkeep
├── generated/
│   └── .gitkeep
│
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── LICENSE
```

## ⚠️ Security

Do not commit:

- `.env`
- API keys
- GitHub tokens
- LangSmith keys
- SQLite databases
- uploaded private documents

If a secret has already been exposed, revoke or rotate it before publishing the repository.

## 🔮 Future Improvements

- Authentication and user accounts
- PostgreSQL production database
- Redis-based session/cache layer
- More advanced RAG with reranking
- EDA agent
- Machine-learning agent
- SQL agent
- Model comparison agent
- Hyperparameter tuning agent
- Docker deployment
- CI/CD pipeline
- Cloud deployment
- Agent observability and evaluation
