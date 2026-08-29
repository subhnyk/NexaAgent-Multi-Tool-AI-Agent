import streamlit as st
from langgraph_backend import chatbot, retrieve_all_threads, ingest_pdf, thread_document_metadata, set_current_thread_id, delete_thread, set_thread_title, get_persisted_title
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import uuid
import os
from datetime import datetime, date, timezone

# **************************************** Page Config *********************************
st.set_page_config(
    page_title="Sunil's Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# **************************************** Custom CSS *********************************
# We use a large CSS block to completely override the Streamlit look to match the design.
st.markdown("""
<style>
    /* Main App Background */
    .stApp {
        background-color: #0e1117;
        color: #ffffff;
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #161b22 !important;
        border-right: 1px solid #30363d;
    }

    [data-testid="stSidebar"] .stMarkdown {
        color: #c9d1d9 !important;
    }

    /* Sidebar Header */
    .sidebar-title {
        font-size: 22px;
        font-weight: bold;
        color: #ffffff;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    /* New Chat Button */
    .stButton > button {
        width: 100%;
        border-radius: 8px;
        border: 1px solid #30363d;
        background-color: #21262d;
        color: white;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        background-color: #30363d;
        border-color: #8b949e;
    }

    /* Chat History Section */
    .history-header {
        font-size: 14px;
        color: #8b949e;
        text-transform: uppercase;
        margin-top: 20px;
        margin-bottom: 10px;
        font-weight: 600;
    }

    /* Chat Bubble Styling */
    .chat-bubble {
        padding: 12px 16px;
        border-radius: 15px;
        margin-bottom: 10px;
        max-width: 80%;
        line-height: 1.5;
    }
    .user-bubble {
        background-color: #238636;
        color: white;
        margin-left: auto;
        border-bottom-right-radius: 2px;
        text-align: left;
    }
    .assistant-bubble {
        background-color: #21262d;
        color: #c9d1d9;
        margin-right: auto;
        border-bottom-left-radius: 2px;
        border: 1px solid #30363d;
    }

    /* Quick Action Cards */
    .action-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        cursor: pointer;
        transition: transform 0.2s, border-color 0.2s;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    .action-card:hover {
        transform: translateY(-5px);
        border-color: #58a6ff;
    }
    .card-icon {
        font-size: 24px;
        margin-bottom: 8px;
    }
    .card-title {
        font-size: 16px;
        font-weight: bold;
        color: white;
        margin-bottom: 4px;
    }
    .card-desc {
        font-size: 12px;
        color: #8b949e;
    }

    /* Greeting Section */
    .greeting-text {
        font-size: 32px;
        font-weight: bold;
        color: white;
        margin-bottom: 5px;
    }
    .greeting-subtext {
        font-size: 18px;
        color: #8b949e;
        margin-bottom: 30px;
    }

    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Custom Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #0e1117;
    }
    ::-webkit-scrollbar-thumb {
        background: #30363d;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

# **************************************** Utility Functions *************************

def generate_thread_id():
    return str(uuid.uuid4())

def reset_chat():
    thread_id = generate_thread_id()
    st.session_state['thread_id'] = thread_id
    add_thread(st.session_state['thread_id'])
    st.session_state['message_history'] = []

def add_thread(thread_id):
    thread_id_str = str(thread_id)
    if not any(tid == thread_id_str for tid, _ in st.session_state['chat_threads']):
        st.session_state['chat_threads'].append((thread_id_str, None))

def load_conversation(thread_id):
    state = chatbot.get_state(config={'configurable': {'thread_id': thread_id}})
    return state.values.get('messages', [])

def get_thread_title(thread_id):
    thread_id = str(thread_id)
    # 1. Check persisted title in DB
    persisted = get_persisted_title(thread_id)
    if persisted:
        return persisted

    # 2. Check session state cache
    if thread_id in st.session_state["chat_titles"]:
        return st.session_state["chat_titles"][thread_id]

    messages = load_conversation(thread_id)
    for msg in messages:
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, list):
                text = "".join([block.get("text", "") if isinstance(block, dict) else block for block in content])
                content = text
            if isinstance(content, str):
                title = content.strip()
                return title[:35] + "..." if len(title) > 35 else title
    return "New Chat"

def render_thread_row(thread_info):
    thread_id_str, created_at = thread_info
    title = get_thread_title(thread_id_str)

    cols = st.columns([0.8, 0.2])
    with cols[0]:
        if st.button(title, key=f"thread_{thread_id_str}", use_container_width=True):
            messages = load_conversation(thread_id_str)
            temp_messages = []
            for msg in messages:
                role = "user" if isinstance(msg, HumanMessage) else "assistant"
                content = msg.content
                if isinstance(content, list):
                    content = "".join([block.get("text", "") if isinstance(block, dict) else block for block in content])
                temp_messages.append({"role": role, "content": content})
            st.session_state["thread_id"] = thread_id_str
            st.session_state['message_history'] = temp_messages
            st.rerun()
    with cols[1]:
        with st.popover("⋮"):
            # Rename
            new_title = st.text_input("Rename", value=title, key=f"rename_{thread_id_str}")
            if st.button("Save", key=f"save_{thread_id_str}"):
                set_thread_title(thread_id_str, new_title)
                st.session_state['chat_titles'][thread_id_str] = new_title
                st.rerun()

            # Share
            if st.button("Share", key=f"share_{thread_id_str}"):
                st.toast("Share link copied to clipboard! 🔗")

            # Delete
            if st.button("Delete", key=f"delete_{thread_id_str}"):
                delete_thread(thread_id_str)
                if thread_id_str == str(st.session_state['thread_id']):
                    reset_chat()
                st.session_state['chat_threads'] = [t for t in st.session_state['chat_threads'] if t[0] != thread_id_str]
                st.rerun()

# **************************************** Session Setup ******************************

if 'message_history' not in st.session_state:
    st.session_state['message_history'] = []

if 'thread_id' not in st.session_state:
    st.session_state['thread_id'] = generate_thread_id()

if 'chat_threads' not in st.session_state:
    st.session_state['chat_threads'] = retrieve_all_threads()

if 'chat_titles' not in st.session_state:
    st.session_state['chat_titles'] = {}

if "ingested_docs" not in st.session_state:
    st.session_state["ingested_docs"] = {}

add_thread(st.session_state['thread_id'])

thread_key = str(st.session_state["thread_id"])
thread_docs = st.session_state["ingested_docs"].setdefault(thread_key, {})

# **************************************** Sidebar UI *********************************

with st.sidebar:
    st.markdown('<div class="sidebar-title">🤖 NexaAgentS</div>', unsafe_allow_html=True)

    if st.button('➕ New Chat'):
        reset_chat()
        st.rerun()

    st.markdown('<div class="history-header">Chat History</div>', unsafe_allow_html=True)

    # Grouping by actual creation date
    all_threads = st.session_state["chat_threads"][::-1]
    today = date.today()
    today_threads = []
    past_threads = []

    for thread_info in all_threads:
        tid, created_at = thread_info
        if created_at:
            try:
                if isinstance(created_at, str):
                    # SQLite CURRENT_TIMESTAMP is UTC. Parse and convert to local date.
                    dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    dt_local = dt.astimezone().date()
                elif hasattr(created_at, 'date'):
                    dt_local = created_at.date()
                else:
                    dt_local = None

                if dt_local == today:
                    today_threads.append(thread_info)
                else:
                    past_threads.append(thread_info)
            except Exception:
                past_threads.append(thread_info)
        else:
            past_threads.append(thread_info)


    st.markdown("**Today**")
    for thread_info in today_threads:
        render_thread_row(thread_info)

    if past_threads:
        st.markdown("**Past Chats**")
        for thread_info in past_threads:
            render_thread_row(thread_info)


    st.markdown('<div class="history-header">Upload Documents</div>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Browse Files",
        type=["pdf", "csv", "xlsx", "xls", "json", "txt"],
        label_visibility="collapsed"
    )

    if uploaded_file:
        os.makedirs("uploads", exist_ok=True)
        file_path = os.path.join("uploads", uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.session_state["uploaded_file"] = file_path
        st.session_state["uploaded_filename"] = uploaded_file.name
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()

        if file_extension == ".pdf":
            if uploaded_file.name in thread_docs:
                st.info(f"Indexed: {uploaded_file.name}")
            else:
                with st.status("🔄 Indexing PDF...", expanded=True) as status_box:
                    summary = ingest_pdf(uploaded_file.getvalue(), thread_id=thread_key, filename=uploaded_file.name)
                    thread_docs[uploaded_file.name] = summary
                    status_box.update(label="✅ PDF ready", state="complete", expanded=False)
        else:
            st.success(f"✅ {uploaded_file.name} ready")

# **************************************** Main UI ************************************

# Greeting Section
st.markdown('<div class="greeting-text">Hello, User! 👋</div>', unsafe_allow_html=True)
st.markdown('<div class="greeting-subtext">How can I assist you today?</div>', unsafe_allow_html=True)

# Quick Action Cards
col1, col2, col3, col4, col5 = st.columns(5)
actions = [
    {"icon": "📊", "title": "Analyze Data", "desc": "Get insights & trends", "color": "#4CAF50"},
    {"icon": "📈", "title": "Visualize", "desc": "Charts & dashboards", "color": "#FF9800"},
    {"icon": "📄", "title": "Ask from Docs", "desc": "PDF, DOCX, TXT etc.", "color": "#2196F3"},
    {"icon": "💻", "title": "Run Code", "desc": "Python executor", "color": "#9C27B0"},
    {"icon": "🔮", "title": "Forecast", "desc": "Predict future trends", "color": "#F44336"},
]

for i, action in enumerate(actions):
    with [col1, col2, col3, col4, col5][i]:
        st.markdown(f"""
            <div class="action-card">
                <div class="card-icon">{action['icon']}</div>
                <div class="card-title">{action['title']}</div>
                <div class="card-desc">{action['desc']}</div>
            </div>
        """, unsafe_allow_html=True)
        # We use a hidden button to make it clickable since HTML div doesn't trigger Streamlit actions
        if st.button(f"Run {action['title']}", key=f"action_{i}", use_container_width=True):
            st.session_state['input_placeholder'] = f"Help me {action['title'].lower()}."

st.markdown("<br>", unsafe_allow_html=True)

# Chat History Rendering
chat_container = st.container()
with chat_container:
    for message in st.session_state['message_history']:
        role = message['role']
        content = message['content']

        if role == 'user':
            st.markdown(f'<div class="chat-bubble user-bubble">{content}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-bubble assistant-bubble">{content}</div>', unsafe_allow_html=True)

# Chat Input Area
user_input = st.chat_input('Type your message here...')

if user_input:
    # Title Management
    thread_id = str(st.session_state['thread_id'])
    if thread_id not in st.session_state['chat_titles']:
        title = user_input.strip()
        st.session_state['chat_titles'][thread_id] = title[:35] + "..." if len(title) > 35 else title

    # Add user message to history
    st.session_state['message_history'].append({'role': 'user', 'content': user_input})
    st.markdown(f'<div class="chat-bubble user-bubble">{user_input}</div>', unsafe_allow_html=True)

    CONFIG = {
        "configurable": {"thread_id": st.session_state['thread_id']},
        "metadata": {"thread_id": st.session_state['thread_id']},
        "run_name": "chat_turn"
    }

    with st.chat_message("assistant"):
        status_holder = {"box": None}

        def ai_only_stream():
            with set_current_thread_id(st.session_state['thread_id']):
                for message_chunk, metadata in chatbot.stream(
                    {"messages": [HumanMessage(content=user_input)]}, config=CONFIG,
                    stream_mode="messages",):

                    if isinstance(message_chunk, ToolMessage):
                        tool_name = getattr(message_chunk, "name", "tool")
                        if status_holder["box"] is None:
                            status_holder["box"] = st.status(f"🔧 Using `{tool_name}` …", expanded=True)
                        else:
                            status_holder["box"].update(label=f"🔧 Using `{tool_name}` …", state="running", expanded=True)

                    if isinstance(message_chunk, AIMessage):
                        content = message_chunk.content
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict):
                                    text = block.get("text", "")
                                    if text: yield text
                                elif isinstance(block, str):
                                    yield block
                        elif isinstance(content, str):
                            if content: yield content

        ai_message = st.write_stream(ai_only_stream())

        if status_holder["box"] is not None:
            status_holder["box"].update(label="Tool finished", state="complete", expanded=False)

    # Save assistant response to history
    st.session_state['message_history'].append({'role': 'assistant', 'content': ai_message})
    # Rerender to apply bubble styles to the new AI message
    st.rerun()
