# BitLogix-ASR JIRA Worklog MCP Server & CLI

## Project Description

BitLogix-ASR JIRA Worklog MCP is a developer productivity toolkit for automating JIRA worklog entries, ticket management, and reporting.  
It supports multiple workflows:  
- **CLI/manual logging** for developers who prefer the terminal or git hooks  
- **HTTP API server** for integration with other tools  
- **Gradio-based chatbot UI** for natural language interaction  
- **Automated task list generation** from git commit history

The toolkit is designed for teams using JIRA, enabling seamless worklog tracking, ticket closing, and reporting directly from developer workflows.

## Architecture Overview

```
+-------------------+      +-------------------+      +-------------------+
|   Developer CLI   |<---->|    commit.py      |<---->|   JIRA Cloud API  |
+-------------------+      +-------------------+      +-------------------+
         ^                        ^
         |                        |
         |                        v
+-------------------+      +-------------------+
|   Git Hook        |----->|  .worklog_start   |
+-------------------+      +-------------------+
         ^
         |
         v
+-------------------+      +-------------------+
| Gradio Chatbot UI |<---->|   mcp_server.py   |
+-------------------+      +-------------------+
         |                        ^
         v                        |
+-------------------+      +-------------------+
| OpenAI API (NLP)  |      |  Task List Gen    |
+-------------------+      +-------------------+
```

- **commit.py**: Core logic for parsing commit messages, logging work, and closing tickets via JIRA REST API.
- **mcp_server.py**: Flask HTTP API exposing endpoints for worklog, ticket management, and commit parsing.
- **gradio_chatbot.py**: Gradio UI for natural language worklog and ticket management, using OpenAI for intent extraction.
- **app.py**: Orchestrates running both the server and chatbot together.
- **generate_task_list.sh**: Bash script to generate a CSV of tasks from git commit history.
- **.worklog_start_time**: Tracks workday start time for accurate hour calculation.

---

## Step-by-step Analysis

### 1. Purpose and Structure

- The scripts automate JIRA worklog management, ticket closing, and reporting, integrating with developer workflows (git, CLI, API, UI).
- Main files:
  - `commit.py`: Core logic for parsing commit messages, logging work, and closing tickets.
  - `mcp_server.py`: Flask API server exposing endpoints for worklog operations.
  - `gradio_chatbot.py`: Gradio UI for natural language interaction with the MCP server.
  - `app.py`: Orchestrates running both the server and chatbot.
  - Utility scripts: `remove_duplicates.py`, `filter_common_words.py`, `generate_task_list.sh`.
  - Data/config: `.worklog_start_time`, `task_list.csv`, etc.

### 2. Key Features

- **JIRA Integration**: Uses REST API with credentials (hardcoded or via env) to log work and close tickets.
- **Commit Message Parsing**: Extracts ticket, hours, and flags from various commit message patterns.
- **Start Time Tracking**: Tracks workday start time in a file for auto-calculating hours.
- **CLI and Interactive Mode**: Allows both automated (via git hook) and manual logging.
- **HTTP API**: Flask server exposes endpoints for start, log, close, tickets, and commit.
- **Chatbot UI**: Gradio interface uses OpenAI to parse user intent and interact with the MCP server.
- **Task List Generation**: Bash script to generate a CSV of tasks from git log.

### 3. File-by-file Summary

- **commit.py**: Handles parsing commit messages, logging work, closing tickets, and start time management. Supports many commit message formats for flexible logging. Includes test functions for extraction logic.
- **mcp_server.py**: Flask API for worklog operations. Endpoints for start, log, close, tickets, and commit. Uses functions from `commit.py`.
- **gradio_chatbot.py**: Gradio UI for natural language worklog interaction. Uses OpenAI API to extract intent and parameters from user input. Dropdown for ticket selection, hours, and comment input. Calls MCP server endpoints based on user intent. Includes a test suite for intent extraction.
- **app.py**: Orchestrates running both the Flask server and Gradio chatbot. Kills any process on ports 5000/7860 before starting. Can run server, chatbot, or both (default: both).
- **remove_duplicates.py**: Removes duplicates from a JSON token list, filters by another list, and sorts.
- **filter_common_words.py**: Filters a JSON token list to only include common English words.
- **generate_task_list.sh**: Generates a CSV of git commit messages since a given date.
- **git/hooks/post-commit**: Git post-commit hook to trigger `commit.py` and log output.
- **task_list.csv**: Stores a CSV log of tasks/commits for reporting.
- **.worklog_start_time**: Stores the timestamp of the last workday start for hour calculations.

---

## Requirements

- Python 3.7+
- `requests`, `flask`, and `gradio` libraries (`pip install requests flask gradio`)
- OpenAI API key (for chatbot, set as environment variable or in code)

## Usage

### 1. CLI Mode (Manual or Git Hook)

- **Start your workday:**
  ```
  python commit.py start
  ```
- **Set a specific start time:**
  ```
  python commit.py start -st 09:30am
  ```
- **Print current start time:**
  ```
  python commit.py start -p
  ```
- **Log hours via commit message (automated via git hook):**
  ```
  git commit -m "(AHPM-124 -h 2h) Fixed bug in login flow"
  ```
- **Manual logging (interactive):**
  ```
  python commit.py
  ```
- **Undo last log for today:**
  ```
  python commit.py undo_last_log
  ```
- **Undo/delete all logs for today:**
  ```
  python commit.py undo_all_today
  ```

### 2. MCP Server Mode (HTTP API)

- **Start the server:**
  ```
  python mcp_server.py
  ```
- **API Endpoints:**
  - `POST /start`  
    `{ "time": "09:30am" }`  
    Set workday start time.
  - `POST /log`  
    `{ "ticket": "AHPM-124", "hours": "2h", "comment": "Worked on bug", "close": "c" }`  
    Log work and optionally close ticket.
  - `POST /close`  
    `{ "ticket": "AHPM-124" }`  
    Close ticket.
  - `GET /tickets`  
    List open tickets assigned to you.
  - `POST /commit`  
    `{ "commit_msg": "(AHPM-124 -h 2h) Fixed bug" }`  
    Log work from commit message.
  - `POST /undo_last_log`  
    Undo/delete the last worklog for today.
  - `POST /undo_all_logs_today`  
    Undo/delete all worklogs for today.

### 3. Gradio Chatbot UI

- **Start the chatbot UI (and server):**
  ```
  python app.py
  ```
  or to run only the chatbot:
  ```
  python app.py chatbot
  ```
- **Features:**
  - Natural language commands for logging work, closing tickets, etc.
  - Dropdown to select tickets and log hours.
  - Uses OpenAI for intent extraction.
  - Natural language commands for deleting logs, e.g.:
    - "Undo last log."
    - "Delete all today's worklogs."
  - Buttons for "Undo Last Log" and "Undo All Today's Logs".

### 4. Task List Generation

- **Generate a CSV of recent git commit tasks:**
  ```
  bash generate_task_list.sh
  ```
  Optionally provide a start date:
  ```
  bash generate_task_list.sh 2025-06-01
  ```

## Git Hook Setup

To enable automatic JIRA worklog logging after each commit, set up a git post-commit hook:

1. Create or edit `.git/hooks/post-commit` in your repository.
2. Add the following lines (update the path if needed):

   ```
   #!/bin/bash
   python "/Users/AqibMumtaz/Aqib Mumtaz/BitLogix/BitLogix-ASR/Model-End/scripts/commit.py"
   ```

3. Make the hook executable:
   ```
   chmod +x .git/hooks/post-commit
   ```

This will trigger the worklog script after every commit.

---

## Notes

- Credentials are hardcoded for demo; secure them for production.
- All CLI features remain available.
- MCP server runs on port 5000 by default.
- Gradio chatbot runs on port 7860 by default.

## Troubleshooting

- Ensure Python dependencies are installed.
- For API usage, use tools like `curl` or Postman.
- For chatbot, ensure OpenAI API key is set.

