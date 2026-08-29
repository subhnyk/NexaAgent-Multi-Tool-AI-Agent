# Implementation Plan: Fix Date-Grouping Logic in Chat History

## Problem Statement
The current chat history grouping in the Streamlit frontend is simulated using list slicing (`[:3]` for Today, `[3:7]` for Yesterday). This is inaccurate as it doesn't use actual creation timestamps. The database does not store these timestamps.

## Requirements
1. Correctly group conversations based on actual creation timestamps.
2. Rename "Yesterday" to "Past Chats".
3. Only today's chats under "Today", all others under "Past Chats".
4. Handle existing data gracefully (treat threads without timestamps as "Past Chats").
5. Store timestamps for new threads.

## Technical Approach

### 1. Database Migration (`langgraph_backend.py`)
The `thread_titles` table needs a `created_at` column.

- **Schema Update**: Update the `CREATE TABLE` statement to include `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`.
- **Migration**: Add a check to perform an `ALTER TABLE` for existing databases to avoid crashing or losing data.

### 2. Timestamp Persistence (`langgraph_backend.py`)
Ensure the creation date is set and preserved.

- **Modification of `set_thread_title`**:
  - Change `INSERT OR REPLACE` to `INSERT INTO ... ON CONFLICT(thread_id) DO UPDATE SET title=excluded.title`.
  - This ensures that the `created_at` timestamp (set by the default value on the first insert) is not overwritten when the title is updated.

### 3. Retrieving Timestamps (`langgraph_backend.py`)
Update `retrieve_all_threads` to return metadata.

- **Function Update**:
  - Current: Returns `list[str]` (thread IDs).
  - New: Returns `list[tuple[str, Optional[str]]]` (thread ID and created_at string).
  - Implementation:
    1. Get all unique thread IDs from the checkpointer (to ensure all threads are captured).
    2. Query `thread_titles` table for the `created_at` timestamp for each ID.
    3. Return the paired data.

### 4. Frontend Grouping Logic (`streamlit_frountend.py`)
Update how threads are stored and displayed in the sidebar.

- **Session State**: Update `st.session_state['chat_threads']` to store the tuples returned by `retrieve_all_threads`.
- **Grouping implementation**:
  - Use `datetime.now().date()` to get today's date.
  - Parse the `created_at` string from the database into a `datetime` object.
  - Categorize threads:
    - `Today`: `created_at.date() == today`
    - `Past Chats`: `created_at.date() != today` or `created_at is None`.
- **UI Update**:
  - Change the header "**Yesterday**" to "**Past Chats**".
  - Remove the slicing logic (`[:3]` and `[3:7]`) and use the categorized lists.

## Detailed Step-by-Step Execution

### Step 1: Update `langgraph_backend.py`
1. Update `conn.execute("CREATE TABLE IF NOT EXISTS thread_titles ...")` to include `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`.
2. Immediately after, add a migration block:
   ```python
   try:
       conn.execute("ALTER TABLE thread_titles ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
       conn.commit()
   except sqlite3.OperationalError:
       # Column already exists
       pass
   ```
3. Update `set_thread_title` to use `ON CONFLICT(thread_id) DO UPDATE SET title=excluded.title`.
4. Update `retrieve_all_threads` to:
   - Fetch all `thread_id` from checkpointer.
   - Query `SELECT thread_id, created_at FROM thread_titles`.
   - Join the two lists to return `(thread_id, created_at)`.

### Step 2: Update `streamlit_frountend.py`
1. Update session state initialization for `chat_threads`:
   ```python
   if 'chat_threads' not in st.session_state:
       st.session_state['chat_threads'] = retrieve_all_threads()
   ```
2. Update the sidebar rendering loop:
   - Extract `threads = st.session_state["chat_threads"][::-1]`.
   - Create two lists: `today_threads = []` and `past_threads = []`.
   - Loop through `threads` and sort into these lists based on `created_at`.
   - Render the "Today" section using `today_threads`.
   - Render the "Past Chats" section using `past_threads`.
3. Update the "Yesterday" label to "Past Chats".
4. Ensure that the `Delete` and `New Chat` logic handles the tuple format of `chat_threads` instead of just strings.

## Verification Plan
1. **Existing Data**: Launch the app and verify that existing chats (without timestamps) appear under "Past Chats".
2. **New Data**: Create a new chat and verify it appears under "Today".
3. **Timestamp Persistence**: Rename a chat and verify it stays in its correct date group.
4. **Date Transition**: Manually update a `created_at` value in `chatbot.db` to a previous date and verify the chat moves to "Past Chats".
5. **Stability**: Verify no `sqlite3` errors occur during the `ALTER TABLE` migration on a fresh install vs an existing install.

## Critical Files for Implementation
- `langgraph_backend.py`
- `streamlit_frountend.py`
- `chatbot.db` (schema change)
EOF`
