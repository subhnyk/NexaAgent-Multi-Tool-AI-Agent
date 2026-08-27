import streamlit as st
from langgraph_backend import chatbot , retrieve_all_threads, ingest_pdf,thread_document_metadata
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import uuid
import os
# **************************************** utility functions *************************

def generate_thread_id(): # every time a new chat is started, generate a new thread id
    thread_id = uuid.uuid4()
    return thread_id

def reset_chat():
    thread_id = generate_thread_id() 
    st.session_state['thread_id'] = thread_id
    add_thread(st.session_state['thread_id'])
    st.session_state['message_history'] = []  
    # generate a new tread id , save it in session and reset maggage history for the new chat thread


def add_thread(thread_id):
    if thread_id not in st.session_state['chat_threads']:
        st.session_state['chat_threads'].append(thread_id)

def load_conversation(thread_id):
    state = chatbot.get_state(config={'configurable': {'thread_id': thread_id}})
    # Check if messages key exists in state values, return empty list if not
    return state.values.get('messages', [])
# it will load the conversation history for the selected thread id and update the message_history in session state

def get_thread_title(thread_id):
    thread_id = str(thread_id)
    """
    first user message is used as the title for the thread, if no user message is found, "New Chat" is returned as the title.
    This function retrieves the conversation history for the given thread_id and looks for the first HumanMessage in the messages. If found, it extracts the content of that message and uses it as the title. If the content is longer than 35 characters, it truncates it and adds "..." at the end. If no HumanMessage is found, it returns "New Chat" as the title.
    First check cached titles in session state, if not found, load the conversation history and extract the title from the first user message. If no user message is found, return "New Chat" as the title.
    """
    # First check cached title
    if thread_id in st.session_state["chat_titles"]:
        return st.session_state["chat_titles"][thread_id]

    # Only access SQLite if title is not already cached
    messages = load_conversation(thread_id)

    for msg in messages:
        if isinstance(msg, HumanMessage):
            content = msg.content
            # Gemini may return content as a list
            if isinstance(content, list):
                text = ""
                for block in content:

                    if isinstance(block, dict):
                        text += block.get("text", "")

                    elif isinstance(block, str):
                        text += block
                content = text

            if isinstance(content, str):
                title = content.strip()

                if len(title) > 35:
                    title = title[:35] + "..."
                return title
            
    return "New Chat"


# **************************************** Session Setup ******************************
if 'message_history' not in st.session_state:
    st.session_state['message_history'] = []

if 'thread_id' not in st.session_state:
    st.session_state['thread_id'] = generate_thread_id()
    #if thread_id is not in chat_threads, it means this is a new chat, so add it to chat_threads (new dynamic thread id is generated for every new chat)

if 'chat_threads' not in st.session_state:
    st.session_state['chat_threads'] = retrieve_all_threads()  # it will retrieve all the existing chat threads from the database and store them in session state

if 'chat_titles' not in st.session_state:
    st.session_state['chat_titles'] = {}

if "ingested_docs" not in st.session_state:
    st.session_state["ingested_docs"] = {}   

add_thread(st.session_state['thread_id'])

thread_key = str(st.session_state["thread_id"])
thread_docs = st.session_state["ingested_docs"].setdefault(thread_key, {})
threads = st.session_state["chat_threads"][::-1]
selected_thread = None


# **************************************** Sidebar UI *********************************

st.sidebar.title("SUNIL's ASSISTANT")
st.sidebar.markdown(f"**Thread ID:** `{thread_key}`")

if st.sidebar.button('New Chat'):
    reset_chat()
    st.rerun()


st.sidebar.header('OurConversations')

# for thread_id in st.session_state['chat_threads'][::-1]:
#     title = st.session_state['chat_titles'].get(str(thread_id),"New Chat")



if thread_docs:
    latest_doc = list(thread_docs.values())[-1]
    st.sidebar.success(
        f"Using `{latest_doc.get('filename')}` "
        f"({latest_doc.get('chunks')} chunks from {latest_doc.get('documents')} pages)"
    )
else:
    st.sidebar.info("No PDF indexed yet.")
# --------------------------------------------------------------------
# uploaded_pdf = st.sidebar.file_uploader("Upload a PDF for this chat", type=["pdf"])
# if uploaded_pdf:
#     if uploaded_pdf.name in thread_docs:
#         st.sidebar.info(f"`{uploaded_pdf.name}` already processed for this chat.")
#     else:
#         with st.sidebar.status("Indexing PDF…", expanded=True) as status_box:
#             summary = ingest_pdf(
#                 uploaded_pdf.getvalue(),
#                 thread_id=thread_key,
#                 filename=uploaded_pdf.name,
#             )
#             thread_docs[uploaded_pdf.name] = summary
#             status_box.update(label="✅ PDF indexed", state="complete", expanded=False)
# ----------------------------------------------------------------------------
# **************************************** Universal File Upload ************************************

st.sidebar.subheader("📎 Documents & Data")

uploaded_file = st.sidebar.file_uploader(
    "Upload File",
    type=["pdf", "csv", "xlsx", "xls", "json", "txt"],
    help="PDF/TXT → RAG + Tools | CSV/Excel/JSON → Tools")

if uploaded_file:
    # Save uploaded file
    os.makedirs("uploads", exist_ok=True)
    file_path = os.path.join("uploads",uploaded_file.name )
        
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Make uploaded file available to tools
    st.session_state["uploaded_file"] = file_path
    st.session_state["uploaded_filename"] = uploaded_file.name

    file_extension = os.path.splitext(uploaded_file.name )[1].lower()
        
    # PDF → RAG + Tools
    if file_extension == ".pdf":
        if uploaded_file.name in thread_docs:
            st.sidebar.info(f"`{uploaded_file.name}` already indexed.")
                
        else:
            with st.sidebar.status("🔄 Indexing PDF for RAG...",expanded=True) as status_box:
                
                summary = ingest_pdf(uploaded_file.getvalue(),thread_id=thread_key,filename=uploaded_file.name )
            
                thread_docs[uploaded_file.name] = summary

                status_box.update(label="✅ PDF ready for RAG + Tools",state="complete",expanded=False)
            
    # Other file types → Tools
    else:
        st.sidebar.success(f"✅ `{uploaded_file.name}` ready for tools")
            
        



st.sidebar.subheader("Past conversations")
if not threads:
    st.sidebar.write("No past conversations yet.")
else:
    for thread_id in threads:
        # Get actual title from first user message
        thread_id_str = str(thread_id)

        title = get_thread_title(thread_id_str)

        if st.sidebar.button(title,key=f"thread_{thread_id_str}",width="stretch",use_container_width=True):
         st.session_state['thread_id'] = thread_id
        messages = load_conversation(thread_id_str)
# this will display the list of past conversation threads in the sidebar, and when a thread is selected, it will load the conversation history for that thread and update the message_history in session state.
        
     # it will load the conversation history for the selected thread id and update the message_history in session state

        temp_messages = []

        for msg in messages:

            if isinstance(msg, HumanMessage):
                role = "user"
            else:
                role = "assistant"
            content = msg.content

            if isinstance(content, list):
                text = ""
                for block in content:
                    if isinstance(block, dict):
                        text += block.get("text", "")
                    elif isinstance(block, str):
                        text += block

                content = text
            temp_messages.append({
                "role": role,
                "content": content})
        
        st.session_state["thread_id"] = thread_id_str
        st.session_state['message_history'] = temp_messages
        st.rerun()

# **************************************** Main UI ************************************

# loading the conversation history
for message in st.session_state['message_history']:
    with st.chat_message(message['role']):
        st.text(message['content']) # it will display the message content in the chat message box, based on the role (user or assistant) of the message.
# **************************************** File Upload ************************************

# uploaded_file = st.file_uploader(
#     "📎 Upload File",
#     type=["pdf", "csv", "xlsx", "xls", "json", "txt"],
#     help="Upload a file for PDF reading, file analysis or data visualization"
# )

# if uploaded_file:

#     os.makedirs("uploads", exist_ok=True)

#     file_path = os.path.join(
#         "uploads",
#         uploaded_file.name
#     )

#     with open(file_path, "wb") as f:
#         f.write(uploaded_file.getbuffer())

#     st.session_state["uploaded_file"] = file_path

#     st.success(f"File uploaded: {uploaded_file.name}")


# **************************************** Chat Input ************************************
user_input = st.chat_input('Type here')



if user_input:
        # Create title from first user query
    thread_id = str(st.session_state['thread_id'])

    if thread_id not in st.session_state['chat_titles']:

        title = user_input.strip()

        # Keep title short
        if len(title) > 35:
            title = title[:35] + "..."

        st.session_state['chat_titles'][thread_id] = title

    # first add the message to message_history
    st.session_state['message_history'].append({'role': 'user', 'content': user_input})
    with st.chat_message('user'):
        st.text(user_input)

    # CONFIG = {'configurable': {'thread_id': st.session_state['thread_id']}}
    CONFIG = {
        "configurable": {"thread_id": st.session_state['thread_id']},
        "metadata": {"thread_id": st.session_state['thread_id']},
        "run_name": "chat_turn" }    
        
         
     # first add the message to message_history
     # Assistant streaming block
    with st.chat_message("assistant"):
        # Use a mutable holder so the generator can set/modify it
        status_holder = {"box": None}

        file_context = ""

        if "uploaded_file" in st.session_state:
            file_context = (f"\nUploaded file: "f"{st.session_state['uploaded_file']}" )    
               
        def ai_only_stream():
            
            for message_chunk, metadata in chatbot.stream(
                {"messages": [HumanMessage(content=f"""{user_input}
                    Uploaded file:{st.session_state.get("uploaded_file", "No file uploaded")}
                    """)]},config=CONFIG,
                stream_mode="messages",):

                            
                # Lazily create & update the SAME status container when any tool runs
                if isinstance(message_chunk, ToolMessage):
                    tool_name = getattr(message_chunk, "name", "tool")
                    if status_holder["box"] is None:
                        status_holder["box"] = st.status(f"🔧 Using `{tool_name}` …", expanded=True)
                     
                    else:
                        status_holder["box"].update(label=f"🔧 Using `{tool_name}` …",state="running",expanded=True,)
                            
             # ai response chunk               
            if isinstance(message_chunk, AIMessage):

                content = message_chunk.content

                # Gemini sometimes returns:
                # [{'type': 'text', 'text': 'Hello...'}]

         
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if text:
                            yield text
                    elif isinstance(block, str):
                        yield block

            elif isinstance(content, str):
                if content:
                    yield content

                else:
                    yield content
                    # this function streams the assistant's response in real-time, allowing the user to see the response as it is generated. It handles tool usage and updates the status accordingly.

        ai_message = st.write_stream(ai_only_stream())

        # Finalize only if a tool was actually used
        if status_holder["box"] is not None:
            status_holder["box"].update(label="Tool finished", state="complete", expanded=False )
    # save the assistant message to message_history       
    st.session_state['message_history'].append({'role': 'assistant', 'content': ai_message})

    # streamlit run streamlit_frountend.py