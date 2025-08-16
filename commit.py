"""
JIRA Hours Logging Script - Usage Instructions

How to Start:
- To begin your workday and set the start time, run:
    python commit.py start
- To set a specific start time (e.g., 09:30am), run:
    python commit.py start -st 09:30am

How to Print Current Start Time:
- To print the last saved start time, run:
    python commit.py start -p

How to Use:
- After starting your workday, you can log hours automatically using commit messages with the '-a' flag.
- If you do not start your workday, you must provide hours with each commit using '-h', or set the start time in your first commit of the day using '-st <time>'.
- The first commit after 6am each day must set the start time (with '-st') or you must start your workday manually as above.

How to Run:
- The script is intended to be run automatically via a git post-commit hook, or manually for interactive logging.
- To run manually and log hours interactively:
    python commit.py

1. Setup Git Post-Commit Hook:
   Add the following to .git/hooks/post-commit and make it executable:
   #!/bin/bash
   python "/Users/AqibMumtaz/Aqib Mumtaz/BitLogix/BitLogix-ASR/Model-End/scripts/commit.py"

2. Logging Hours via Commit Message (All Supported Patterns):
   - (AHPM-124 -h 2h) <your comment>
   - (AHPM-124 -h 2h -c) <your comment>         # '-c' closes the ticket
   - (AHPM-124 -h 45m) <your comment>
   - (AHPM-124 -h 1h 15m) <your comment>
   - (AHPM-124 -h 1h 5m -c) <your comment>
   - (AHPM-124 -h 90m) <your comment>
   - (AHPM-124) <your comment> -h 2h -c
   - (AHPM-124) <your comment> -h 1h 30m
   - (AHPM-124) <your comment> -h 45m
   - (AHPM-124) <your comment> -h 1h 5m -c
   - (AHPM-124) <your comment> -h 90m
   - (AHPM-124) <your comment> -st 12:30pm -c   # set start time, auto-calculate hours, and optionally close
   - (AHPM-124 -a) <your comment>               # auto-calculate hours from previous start time
   - (AHPM-124 -a -c) <your comment>
   - (AHPM-124 -c -a) <your comment>
   - (AHPM-124) <your comment> -a
   - (AHPM-124) <your comment> -a -c
   - (AHPM-124) <your comment> -c -a

   Flags:
   -h <duration>   : Specify hours/minutes to log (e.g., -h 2h, -h 1h 30m, -h 45m)
   -st <time>      : Set manual start time (e.g., -st 09:30am)
   -a              : Auto-calculate hours from previous start time
   -c              : Close the ticket after logging work

   All previous patterns are retained and supported.
   Zero duration (e.g., 0h, 0m, 0h 0m) is ignored/skipped.

   **Git Commit Usage Example:**
   git commit -m "(AHPM-124 -h 2h) Fixed bug in login flow"
   git commit -m "(AHPM-124) Refactored code -h 1h 30m"
   git commit -m "(AHPM-124) Updated docs -st 09:30am -c"
   git commit -m "(AHPM-124 -a -c) Auto log hours and close"

3. Manual Logging (Interactive):
   - Run the script directly:
     python commit.py
   - You will be prompted to select a ticket and enter hours.

4. Start Workday (Automatic/Manual Start Time):
   - To start your workday now:
     python commit.py start
   - To start your workday at a specific time (e.g., 09:30am):
     python commit.py start -st 09:30am
   - To print the last saved start time:
     python commit.py start -p

5. Auto-Tracking:
   - The script tracks your start time and can auto-calculate hours spent since last log.
   - Use '-a' in your commit message to auto-calculate hours from previous start time.
   - Use '-st <time>' to set a manual start time for the current session.
   - **IMPORTANT:** The first commit of each day after 6am must include `-st <time>` to set the day's start time, or you must start your workday manually using `python commit.py start`. Otherwise, you must provide hours with each commit using `-h`.

6. Check JIRA:
   - After logging, check your JIRA issue for worklog and status.


7. Notes:
   - If neither commit message nor interactive input provides ticket/hours, logging is skipped.
   - Credentials are hardcoded; consider securing them for production use.


"""

import requests
import getpass
import re
import subprocess
import sys
import os
import time
from configs import Configs
from datetime import datetime, timedelta


# === CONFIGURATION SECTION ===

JIRA_BASE_URL = Configs.JIRA_BASE_URL
JIRA_USER = Configs.JIRA_USER
JIRA_API_TOKEN = Configs.JIRA_API_TOKEN
START_TIME_FILE = os.environ.get("START_TIME_FILE", "./.worklog_start_time")
JIRA_ROUND_MINUTES = int(os.environ.get("JIRA_ROUND_MINUTES", "15"))
JIRA_MIN_LOG_MINUTES = int(os.environ.get("JIRA_MIN_LOG_MINUTES", "15"))
JIRA_DONE_STATUS = os.environ.get("JIRA_DONE_STATUS", "Done")
JIRA_SEARCH_JQL = os.environ.get(
    "JIRA_SEARCH_JQL", "assignee=currentUser() AND statusCategory!=Done"
)
JIRA_DAY_CUTOFF_TIME = os.environ.get(
    "JIRA_DAY_CUTOFF_TIME", "06:00"
)  # Format: "HH:MM"


def set_start_time():
    # Ensure the directory exists before writing the file
    os.makedirs(os.path.dirname(START_TIME_FILE), exist_ok=True)
    with open(START_TIME_FILE, "w") as f:
        f.write(str(time.time()))


def get_start_time():
    if not os.path.exists(START_TIME_FILE):
        set_start_time()
        return time.time()
    with open(START_TIME_FILE, "r") as f:
        saved_time = float(f.read().strip())
    now = datetime.now()
    saved_dt = datetime.fromtimestamp(saved_time)
    # Parse cutoff time from config (default "06:00")
    cutoff_hour, cutoff_minute = map(int, JIRA_DAY_CUTOFF_TIME.split(":"))
    cutoff = now.replace(
        hour=cutoff_hour, minute=cutoff_minute, second=0, microsecond=0
    )
    # If saved time is not today and current time is after cutoff time, delete the file and use now
    if (saved_dt.date() != now.date()) and (now >= cutoff):
        os.remove(START_TIME_FILE)
        return time.time()
    return saved_time


def get_hours_since_start():
    start = get_start_time()
    if not start:
        return None
    now = time.time()
    seconds = now - start
    hours = round(seconds / 3600, 2)
    return hours


##
# Ensure the script is executable


def get_open_tickets():
    # Fetch tickets with project, epic, and parent info
    # Step 1: Fetch tickets assigned to the user
    jql_user = "assignee=currentUser() AND statusCategory!=Done"
    url = f"{JIRA_BASE_URL}/rest/api/2/search"
    params_user = {
        "jql": jql_user,
        "fields": "key,summary,description,project,parent,issuetype,customfield_10008,customfield_10009",
        "maxResults": 1000,
    }
    response_user = requests.get(
        url, params=params_user, auth=(JIRA_USER, JIRA_API_TOKEN)
    )
    if response_user.status_code != 200:
        print("Error fetching tickets:", response_user.status_code, response_user.text)
        return []
    data_user = response_user.json()
    user_issues = data_user.get("issues", [])

    # Step 2: Collect all parent keys (epic/main task) for user's tickets
    parent_keys = set()
    for issue in user_issues:
        fields = issue.get("fields", {})
        # Epic link
        epic_link = fields.get("customfield_10008") or fields.get("customfield_10009")
        if epic_link:
            parent_keys.add(epic_link)
        parent = fields.get("parent")
        if parent and "key" in parent:
            parent_keys.add(parent["key"])

    # Step 3: Fetch all parent issues (epics/main tasks) needed for hierarchy
    parent_issues = []
    if parent_keys:
        jql_parents = "key in (" + ",".join(parent_keys) + ")"
        params_parents = {
            "jql": jql_parents,
            "fields": "key,summary,description,project,parent,issuetype,customfield_10008,customfield_10009",
            "maxResults": 1000,
        }
        response_parents = requests.get(
            url, params=params_parents, auth=(JIRA_USER, JIRA_API_TOKEN)
        )
        if response_parents.status_code == 200:
            data_parents = response_parents.json()
            parent_issues = data_parents.get("issues", [])

    # Step 4: Build the issues list for hierarchy (user's tickets + their parents)
    issues = user_issues + [
        p for p in parent_issues if p["key"] not in {i["key"] for i in user_issues}
    ]

    # Build hierarchy: Project > Epic > Main Task > Ticket
    hierarchy = {}
    # First pass: collect all Epics per project
    for issue in issues:
        fields = issue.get("fields", {})
        project = fields.get("project", {})
        project_name = project.get("name", "Unknown Project")
        project_id = project.get("id", "unknown")
        ticket_type = fields.get("issuetype", {}).get("name", "Task")
        ticket_key = issue["key"]
        ticket_summary = fields.get("summary", "")
        if project_id not in hierarchy:
            hierarchy[project_id] = {"name": project_name, "epics": {}}
        project_node = hierarchy[project_id]
        # If this issue is an Epic, add as top-level epic
        if ticket_type == "Epic":
            if ticket_key not in project_node["epics"]:
                project_node["epics"][ticket_key] = {
                    "name": ticket_summary,
                    "type": "Epic",
                    "main_tasks": {},
                }
    # Second pass: assign all other issues under their epic/main task, or under No Epic/No Main Task
    for issue in issues:
        fields = issue.get("fields", {})
        project = fields.get("project", {})
        project_id = project.get("id", "unknown")
        ticket_type = fields.get("issuetype", {}).get("name", "Task")
        ticket_key = issue["key"]
        ticket_summary = fields.get("summary", "")
        # Skip Epics themselves (already added)
        if ticket_type == "Epic":
            continue
        epic_link = fields.get("customfield_10008") or fields.get("customfield_10009")
        parent = fields.get("parent")
        parent_key = parent["key"] if parent else None
        parent_summary = (
            parent["fields"]["summary"]
            if parent and "fields" in parent and "summary" in parent["fields"]
            else None
        )
        parent_type = (
            parent["fields"]["issuetype"]["name"]
            if parent
            and "fields" in parent
            and "issuetype" in parent["fields"]
            and "name" in parent["fields"]["issuetype"]
            else None
        )
        project_node = hierarchy[project_id]
        # Find the correct epic for this ticket
        epic_id = None
        epic_node = None
        # debug_info removed
        if epic_link and epic_link in project_node["epics"]:
            epic_id = epic_link
            # debug_info removed
            epic_node = project_node["epics"][epic_id]
        else:
            # Walk up the parent chain to find the nearest epic
            current_parent_key = parent_key
            found_epic = False
            while current_parent_key:
                parent_issue = next(
                    (i for i in issues if i["key"] == current_parent_key), None
                )
                if not parent_issue:
                    break
                parent_fields = parent_issue.get("fields", {})
                parent_type_chain = parent_fields.get("issuetype", {}).get("name", "")
                if parent_type_chain == "Epic":
                    epic_id = current_parent_key
                    found_epic = True
                    # debug_info removed
                    break
                next_parent = parent_fields.get("parent")
                current_parent_key = next_parent["key"] if next_parent else None
            if found_epic and epic_id in project_node["epics"]:
                epic_node = project_node["epics"][epic_id]
            else:
                epic_id = "No Epic"
                # debug_info removed
                if epic_id not in project_node["epics"]:
                    project_node["epics"][epic_id] = {
                        "name": epic_id,
                        "type": "None",
                        "main_tasks": {},
                    }
                epic_node = project_node["epics"][epic_id]
        # debug_info print removed
        # Main task logic
        # If the parent is an epic, place directly under the epic's 'No Main Task'
        if epic_id != "No Epic" and parent_key == epic_id:
            main_task_id = "No Main Task"
            main_task_summary = "No Main Task"
            main_task_type = "None"
        # If the parent is an epic (defensive, in case epic_id logic above missed it)
        elif (
            parent_key
            and parent_key in project_node["epics"]
            and project_node["epics"][parent_key]["type"] == "Epic"
        ):
            main_task_id = "No Main Task"
            main_task_summary = "No Main Task"
            main_task_type = "None"
        # If the parent is a non-epic issue, use it as main task
        elif parent_key:
            main_task_id = parent_key
            main_task_summary = parent_summary if parent_summary else main_task_id
            main_task_type = parent_type if parent_type else "Task"
        else:
            main_task_id = "No Main Task"
            main_task_summary = "No Main Task"
            main_task_type = "None"
        # Do not allow epics as main_tasks under 'No Epic'
        if (
            epic_id == "No Epic"
            and main_task_id in project_node["epics"]
            and project_node["epics"][main_task_id]["type"] == "Epic"
        ):
            # Skip adding this as a main_task under 'No Epic'
            continue
        if main_task_id not in epic_node["main_tasks"]:
            epic_node["main_tasks"][main_task_id] = {
                "summary": main_task_summary,
                "type": main_task_type,
                "tickets": [],
            }
        main_task_node = epic_node["main_tasks"][main_task_id]
        main_task_node["tickets"].append(
            {"key": ticket_key, "summary": ticket_summary, "type": ticket_type}
        )
    # No need to ensure all epics and main_tasks are present, as hierarchy is always constructed with required keys
    return hierarchy


def log_work(ticket_key, time_spent, comment, date_str=None):
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{ticket_key}/worklog"
    payload = {"timeSpent": time_spent, "comment": comment}
    if date_str:
        # Set started date for worklog if API supports it
        payload["started"] = (
            f"{date_str}T09:00:00.000+0000"  # Default 9am, adjust as needed
        )
    response = requests.post(url, json=payload, auth=(JIRA_USER, JIRA_API_TOKEN))
    if response.status_code == 201:
        print("JIRA hours logged.")
    else:
        print("Error logging work:", response.status_code, response.text)


def close_ticket(ticket_key, date_str=None):
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{ticket_key}/transitions"
    response = requests.get(url, auth=(JIRA_USER, JIRA_API_TOKEN))
    if response.status_code != 200:
        print("Error fetching transitions:", response.status_code, response.text)
        return
    transitions = response.json().get("transitions", [])
    done_id = None
    for t in transitions:
        if t["to"]["name"] == "Done":
            done_id = t["id"]
            break
    if done_id:
        payload = {"transition": {"id": done_id}}
        resp = requests.post(url, json=payload, auth=(JIRA_USER, JIRA_API_TOKEN))
        if resp.status_code == 204:
            print(f"Ticket {ticket_key} closed.")
        else:
            print("Error closing ticket:", resp.status_code, resp.text)
    else:
        print(f"No 'Done' transition available for {ticket_key}.")


def extract_ticket_key(commit_msg):
    """Extract JIRA ticket key from commit message (e.g., AHPM-123)."""
    match = re.search(r"\b([A-Z]+-\d+)\b", commit_msg)
    return match.group(1) if match else None


def parse_start_time_str(start_str):
    """
    Parses '12:30pm' or '09:15am' and returns a timestamp for today.
    """
    try:
        match = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)", start_str.lower())
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2))
        ampm = match.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        now = datetime.now()
        manual_time = datetime(now.year, now.month, now.day, hour, minute)
        # If manual time is in the future, use yesterday
        if manual_time > now:
            manual_time -= timedelta(days=1)
        return manual_time.timestamp()
    except Exception:
        return None


def format_jira_duration(hours_float):
    """
    Converts float hours to JIRA duration string, e.g. 2.5 -> '2h 30m'.
    Rounds duration to nearest 15 minutes bracket. Always returns at least '15m'.
    """
    total_minutes = int(round(hours_float * 60 / 15) * 15)
    total_minutes = max(15, total_minutes)  # ensure at least 15 minutes
    h = total_minutes // 60
    m = total_minutes % 60
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0 or h == 0:
        parts.append(f"{m}m")
    return " ".join(parts)


def extract_commit_info(commit_msg):
    """
    Extract ticket key, hours, close flag, and start time from commit message.
    Supports parameter style:
      -st <start time>
      -h <hours>
      -a (auto-calculate hours from previous start time)
      -c (close flag)
    Returns (ticket_key, hours, close_flag, start_time) or (None, None, None, None)
    """
    ticket_key = extract_ticket_key(commit_msg)

    # Extract parameters using regex
    start_match = re.search(r"-st\s+(\d{1,2}:\d{2}\s*[ap]m)", commit_msg, re.IGNORECASE)
    hours_match = re.search(r"-h\s*([^\s]+(?:\s+[^\s]+)*)", commit_msg, re.IGNORECASE)
    auto_match = re.search(r"(?<!\w)-a(?!\w)", commit_msg)
    close_match = re.search(r"(?<!\w)-c(?!\w)", commit_msg)

    start_time = None
    hours = None
    close_flag = "N"

    if start_match:
        start_str = start_match.group(1)
        start_time = parse_start_time_str(start_str)
        # Save the start time to file for future auto-calculate
        with open(START_TIME_FILE, "w") as f:
            f.write(str(start_time))
    if hours_match:
        duration_tokens = re.findall(r"\d+h|\d+m", hours_match.group(1))
        hours = " ".join(duration_tokens)
        if hours and hours.strip() in ["0h", "0m", "0h 0m", "0m 0h", ""]:
            hours = None
    # Fallback: extract hours from legacy patterns if not found
    if not hours and not auto_match:
        legacy_hours = re.findall(r"(\d+h|\d+m)", commit_msg)
        hours = " ".join(legacy_hours) if legacy_hours else None
        if hours and hours.strip() in ["0h", "0m", "0h 0m", "0m 0h", ""]:
            hours = None

    if close_match is not None:
        close_flag = "c"

    # If start_time is present, calculate hours since start
    if start_time:
        now = time.time()
        seconds = now - start_time
        hours_float = seconds / 3600
        jira_duration = format_jira_duration(hours_float)
        hours = jira_duration

    # If -a flag is present, auto-calculate hours from previous start time
    if auto_match:
        prev_start = get_start_time()
        now = time.time()
        seconds = now - prev_start
        hours_float = seconds / 3600
        jira_duration = format_jira_duration(hours_float)
        hours = jira_duration
        start_time = prev_start
        # Update start time to now for next auto-log
        set_start_time()

    if not ticket_key or not hours:
        return None, None, None, None

    return ticket_key, hours, close_flag, start_time


def extract_commit_comment(commit_msg):
    """
    Extracts the comment after the closing parenthesis in the commit message,
    and removes trailing time, start time, auto, and close flag if present.
    Example: "(AHPM-124) ⏫ Updates: commit updates -st 12:30pm -c -a" -> "⏫ Updates: commit updates"
    """
    match = re.search(r"\)\s*(.*)", commit_msg)
    comment = match.group(1).strip() if match else commit_msg
    comment = re.sub(
        r"\s+(-st\s+\d{1,2}:\d{2}\s*[ap]m|-h\s+[\dhm\s]+|-a)(\s+-c)?\s*$",
        "",
        comment,
        flags=re.IGNORECASE,
    )
    return comment


def print_start_time():
    ts = get_start_time()
    dt = datetime.fromtimestamp(ts)
    print(f"Current workday start time: {dt.strftime('%Y-%m-%d %H:%M:%S')}")


# Time is saved to file in the following conditions:


# 1. When set_start_time() is called (e.g., after logging work, or if .worklog_start_time is missing)
def set_start_time():
    # Ensure the directory exists before writing the file
    os.makedirs(os.path.dirname(START_TIME_FILE), exist_ok=True)
    with open(START_TIME_FILE, "w") as f:
        f.write(str(time.time()))


# 2. When set_start_time_manual() is called (manual start time via CLI)
def set_start_time_manual(hhmm=None):
    from datetime import datetime, timedelta

    # Ensure the directory exists before writing the file
    os.makedirs(os.path.dirname(START_TIME_FILE), exist_ok=True)
    if hhmm:
        # Accept both "09:30" and "12:45pm" formats
        try:
            # Try HH:MM first
            if re.match(r"^\d{1,2}:\d{2}$", hhmm):
                hour, minute = map(int, hhmm.split(":"))
            else:
                # Try HH:MMam/pm
                match = re.match(r"^(\d{1,2}):(\d{2})\s*([ap]m)$", hhmm.strip().lower())
                if not match:
                    raise ValueError()
                hour = int(match.group(1))
                minute = int(match.group(2))
                ampm = match.group(3)
                if ampm == "pm" and hour != 12:
                    hour += 12
                if ampm == "am" and hour == 12:
                    hour = 0
            now = datetime.now()
            manual_time = datetime(now.year, now.month, now.day, hour, minute)
            # If manual time is in the future, use yesterday
            if manual_time > now:
                manual_time -= timedelta(days=1)
            timestamp = manual_time.timestamp()
        except Exception:
            print(
                "Invalid time format. Use HH:MM (e.g., 09:30) or HH:MMam/pm (e.g., 12:45pm)"
            )
            return
    else:
        timestamp = time.time()
    with open(START_TIME_FILE, "w") as f:
        f.write(str(timestamp))
    dt_str = datetime.fromtimestamp(timestamp).strftime("%H:%M")
    print(f"Workday started at {hhmm if hhmm else 'now'} ({dt_str}).")


# 3. When -st <time> is passed in the commit message (inside extract_commit_info)
def extract_commit_info(commit_msg):
    """
    Extract ticket key, hours, close flag, and start time from commit message.
    Supports parameter style:
      -st <start time>
      -h <hours>
      -a (auto-calculate hours from previous start time)
      -c (close flag)
    Returns (ticket_key, hours, close_flag, start_time) or (None, None, None, None)
    """
    ticket_key = extract_ticket_key(commit_msg)

    # Extract parameters using regex
    start_match = re.search(r"-st\s+(\d{1,2}:\d{2}\s*[ap]m)", commit_msg, re.IGNORECASE)
    hours_match = re.search(r"-h\s*([^\s]+(?:\s+[^\s]+)*)", commit_msg, re.IGNORECASE)
    auto_match = re.search(r"(?<!\w)-a(?!\w)", commit_msg)
    close_match = re.search(r"(?<!\w)-c(?!\w)", commit_msg)

    start_time = None
    hours = None
    close_flag = "N"

    if start_match:
        start_str = start_match.group(1)
        start_time = parse_start_time_str(start_str)
        # Save the start time to file for future auto-calculate
        with open(START_TIME_FILE, "w") as f:
            f.write(str(start_time))
    if hours_match:
        duration_tokens = re.findall(r"\d+h|\d+m", hours_match.group(1))
        hours = " ".join(duration_tokens)
        if hours and hours.strip() in ["0h", "0m", "0h 0m", "0m 0h", ""]:
            hours = None
    # Fallback: extract hours from legacy patterns if not found
    if not hours and not auto_match:
        legacy_hours = re.findall(r"(\d+h|\d+m)", commit_msg)
        hours = " ".join(legacy_hours) if legacy_hours else None
        if hours and hours.strip() in ["0h", "0m", "0h 0m", "0m 0h", ""]:
            hours = None

    if close_match is not None:
        close_flag = "c"

    # If start_time is present, calculate hours since start
    if start_time:
        now = time.time()
        seconds = now - start_time
        hours_float = seconds / 3600
        jira_duration = format_jira_duration(hours_float)
        hours = jira_duration

    # If -a flag is present, auto-calculate hours from previous start time
    if auto_match:
        prev_start = get_start_time()
        now = time.time()
        seconds = now - prev_start
        hours_float = seconds / 3600
        jira_duration = format_jira_duration(hours_float)
        hours = jira_duration
        start_time = prev_start
        # Update start time to now for next auto-log
        set_start_time()

    if not ticket_key or not hours:
        return None, None, None, None

    return ticket_key, hours, close_flag, start_time


def extract_commit_comment(commit_msg):
    """
    Extracts the comment after the closing parenthesis in the commit message,
    and removes trailing time, start time, auto, and close flag if present.
    Example: "(AHPM-124) ⏫ Updates: commit updates -st 12:30pm -c -a" -> "⏫ Updates: commit updates"
    """
    match = re.search(r"\)\s*(.*)", commit_msg)
    comment = match.group(1).strip() if match else commit_msg
    comment = re.sub(
        r"\s+(-st\s+\d{1,2}:\d{2}\s*[ap]m|-h\s+[\dhm\s]+|-a)(\s+-c)?\s*$",
        "",
        comment,
        flags=re.IGNORECASE,
    )
    return comment


def set_start_time_manual(hhmm=None):
    from datetime import datetime, timedelta

    # Ensure the directory exists before writing the file
    os.makedirs(os.path.dirname(START_TIME_FILE), exist_ok=True)
    if hhmm:
        # Accept both "09:30" and "12:45pm" formats
        try:
            # Try HH:MM first
            if re.match(r"^\d{1,2}:\d{2}$", hhmm):
                hour, minute = map(int, hhmm.split(":"))
            else:
                # Try HH:MMam/pm
                match = re.match(r"^(\d{1,2}):(\d{2})\s*([ap]m)$", hhmm.strip().lower())
                if not match:
                    raise ValueError()
                hour = int(match.group(1))
                minute = int(match.group(2))
                ampm = match.group(3)
                if ampm == "pm" and hour != 12:
                    hour += 12
                if ampm == "am" and hour == 12:
                    hour = 0
            now = datetime.now()
            manual_time = datetime(now.year, now.month, now.day, hour, minute)
            # If manual time is in the future, use yesterday
            if manual_time > now:
                manual_time -= timedelta(days=1)
            timestamp = manual_time.timestamp()
        except Exception:
            print(
                "Invalid time format. Use HH:MM (e.g., 09:30) or HH:MMam/pm (e.g., 12:45pm)"
            )
            return
    else:
        timestamp = time.time()
    with open(START_TIME_FILE, "w") as f:
        f.write(str(timestamp))
    dt_str = datetime.fromtimestamp(timestamp).strftime("%H:%M")
    print(f"Workday started at {hhmm if hhmm else 'now'} ({dt_str}).")


def test_start_time_extraction():
    test_cases = [
        # Pattern 1
        "(AHPM-124 -h 2h) Test commit",
        "(AHPM-124 -c -h 2h) Test commit close",
        "(AHPM-124 -h 2h -c) Test commit close",
        "(AHPM-124 -h 45m) Test commit",
        "(AHPM-124 -c -h 45m) Test commit",
        "(AHPM-124 -h 45m -c) Test commit",
        "(AHPM-124 -h 1h 15m) Test commit",
        "(AHPM-124 -c -h 1h 15m) Test commit",
        "(AHPM-124 -h 1h 15m -c) Test commit",
        "(AHPM-124 -h 1h 5m -c) Test commit close",
        "(AHPM-124 -c -h 1h 5m) Test commit close",
        "(AHPM-124 -h 90m) Test commit",
        "(AHPM-124 -c -h 90m) Test commit",
        "(AHPM-124 -h 90m -c) Test commit",
        "(AHPM-124 -h 7m) Test commit",
        "(AHPM-124 -c -h 7m) Test commit",
        "(AHPM-124 -h 7m -c) Test commit",
        "(AHPM-124 -h 22m) Test commit",
        "(AHPM-124 -c -h 22m) Test commit",
        "(AHPM-124 -h 22m -c) Test commit",
        "(AHPM-124 -h 37m) Test commit",
        "(AHPM-124 -c -h 37m) Test commit",
        "(AHPM-124 -h 37m -c) Test commit",
        "(AHPM-124 -h 59m) Test commit",
        "(AHPM-124 -c -h 59m) Test commit",
        "(AHPM-124 -h 59m -c) Test commit",
        "(AHPM-124 -h 16m) Test commit",
        "(AHPM-124 -c -h 16m) Test commit",
        "(AHPM-124 -h 16m -c) Test commit",
        # Pattern 2
        "(AHPM-124) Test commit -h 2h",
        "(AHPM-124) Test commit -c -h 2h",
        "(AHPM-124) Test commit -h 2h -c",
        "(AHPM-124) Test commit -h 1h 30m",
        "(AHPM-124) Test commit -c -h 1h 30m",
        "(AHPM-124) Test commit -h 1h 30m -c",
        "(AHPM-124) Test commit -h 45m",
        "(AHPM-124) Test commit -c -h 45m",
        "(AHPM-124) Test commit -h 45m -c",
        "(AHPM-124) Test commit -h 1h 5m -c",
        "(AHPM-124) Test commit -c -h 1h 5m",
        "(AHPM-124) Test commit -h 90m",
        "(AHPM-124) Test commit -c -h 90m",
        "(AHPM-124) Test commit -h 90m -c",
        "(AHPM-124) Test commit -h 7m",
        "(AHPM-124) Test commit -c -h 7m",
        "(AHPM-124) Test commit -h 7m -c",
        "(AHPM-124) Test commit -h 22m",
        "(AHPM-124) Test commit -c -h 22m",
        "(AHPM-124) Test commit -h 22m -c",
        "(AHPM-124) Test commit -h 37m",
        "(AHPM-124) Test commit -c -h 37m",
        "(AHPM-124) Test commit -h 37m -c",
        "(AHPM-124) Test commit -h 59m",
        "(AHPM-124) Test commit -c -h 59m",
        "(AHPM-124) Test commit -h 59m -c",
        "(AHPM-124) Test commit -h 16m",
        "(AHPM-124) Test commit -c -h 16m",
        "(AHPM-124) Test commit -h 16m -c",
        # Pattern 3 - start time variations to test 15m brackets
        "(AHPM-124) Test commit -st 09:00am",
        "(AHPM-124) Test commit -st 09:07am",
        "(AHPM-124) Test commit -st 09:14am",
        "(AHPM-124) Test commit -st 09:16am",
        "(AHPM-124) Test commit -st 09:22am",
        "(AHPM-124) Test commit -st 09:29am",
        "(AHPM-124) Test commit -st 09:30am",
        "(AHPM-124) Test commit -st 09:37am",
        "(AHPM-124) Test commit -st 09:44am",
        "(AHPM-124) Test commit -st 09:59am",
        "(AHPM-124) Test commit -st 10:00am",
        "(AHPM-124) Test commit -st 10:15am",
        "(AHPM-124) Test commit -st 10:45am",
        "(AHPM-124) Test commit -st 11:00am",
        "(AHPM-124) Test commit -st 11:59am",
        "(AHPM-124) Test commit -st 12:00pm",
        "(AHPM-124) Test commit -st 12:15pm",
        "(AHPM-124) Test commit -st 12:45pm",
        "(AHPM-124) Test commit -st 01:00pm",
        "(AHPM-124) Test commit -st 01:15pm",
        "(AHPM-124) Test commit -st 01:44pm",
        "(AHPM-124) Test commit -st 01:59pm",
        # Pattern 3 with close flag (both orders)
        "(AHPM-124) Test commit -st 09:00am -c",
        "(AHPM-124) Test commit -c -st 09:00am",
        "(AHPM-124) Test commit -st 09:15am -c",
        "(AHPM-124) Test commit -c -st 09:15am",
        "(AHPM-124) Test commit -st 09:45am -c",
        "(AHPM-124) Test commit -c -st 09:45am",
        "(AHPM-124) Test commit -st 10:00am -c",
        "(AHPM-124) Test commit -c -st 10:00am",
        "(AHPM-124) Test commit -st 12:00pm -c",
        "(AHPM-124) Test commit -c -st 12:00pm",
        # Pattern 4: auto-calc hours from previous start time
        "(AHPM-124 -a) Test commit",
        "(AHPM-124 -a -c) Test commit",
        "(AHPM-124 -c -a) Test commit",
        "(AHPM-124) Test commit -a",
        "(AHPM-124) Test commit -a -c",
        "(AHPM-124) Test commit -c -a",
        # Invalid/edge cases (should not extract ticket/duration)
        "(AHPM-124) Test commit -st1:00pm",
        "(AHPM-124) Test commit",
        "(AHPM-124) Test commit -h 0h",
        "(AHPM-124) Test commit m",
        "(AHPM-124) Test commit -h 0h 0m",
    ]
    # Indices of invalid/edge cases
    invalid_indices = set(range(len(test_cases) - 5, len(test_cases)))
    results = []
    for idx, test_commit_msg in enumerate(test_cases):
        print("=" * 60)
        print(f"Testing commit message: {test_commit_msg}")
        result = extract_commit_info(test_commit_msg)
        print("Extracted values:")
        print(f"  ticket_key: {result[0]}")
        print(f"  jira_duration: {result[1]}")
        print(f"  close_flag: {result[2]}")
        print(f"  start_time (timestamp): {result[3]}")
        # For invalid cases, PASS if extraction fails
        if idx in invalid_indices:
            coverage = "PASS" if not result[0] and not result[1] else "FAIL"
        else:
            coverage = "PASS" if result[0] and result[1] else "FAIL"
        results.append(
            (test_commit_msg, coverage, result[0], result[1], result[2], result[3])
        )
        if result[3]:
            print(f"  start_time (datetime): {datetime.fromtimestamp(result[3])}")
            now = time.time()
            seconds = now - result[3]
            hours_float = seconds / 3600
            print(f"  Calculated hours since start: {hours_float}")
            print(f"  JIRA duration string: {format_jira_duration(hours_float)}")
        else:
            print("  [ERROR] Start time could not be parsed from commit message.")
    print("=" * 60)
    print("\nTest Coverage Report:")
    print(
        f"{'Commit Message':<45} {'Result':<6} {'Ticket':<10} {'Duration':<15} {'Close':<6} {'Start Time'}"
    )
    print("-" * 110)
    for msg, cov, ticket, dur, close, stime in results:
        print(
            f"{msg[:44]:<45} {cov:<6} {str(ticket):<10} {str(dur):<15} {str(close):<6} {str(stime)}"
        )
    print("-" * 110)
    total = len(test_cases)
    passed = sum(1 for r in results if r[1] == "PASS")
    failed = sum(1 for r in results if r[1] == "FAIL")
    percent = round((passed / total) * 100, 2) if total else 0
    print(
        f"Total: {total} | Passed: {passed} | Failed: {failed} | Coverage: {percent}%"
    )


def get_hours_logged(date_str=None):
    """
    Returns total hours logged for the given date (YYYY-MM-DD) by the current user (float, in hours).
    """
    from datetime import datetime

    if date_str:
        date_query = date_str
    else:
        date_query = datetime.now().strftime("%Y-%m-%d")
    url = f"{JIRA_BASE_URL}/rest/api/2/search"
    jql = f"worklogAuthor = currentUser() AND worklogDate = {date_query}"
    params = {
        "jql": jql,
        "fields": "worklog",
        "maxResults": 100,
    }
    response = requests.get(url, params=params, auth=(JIRA_USER, JIRA_API_TOKEN))
    if response.status_code != 200:
        return 0.0
    data = response.json()
    total_seconds = 0
    for issue in data.get("issues", []):
        worklogs = issue.get("fields", {}).get("worklog", {}).get("worklogs", [])
        for wl in worklogs:
            started = wl.get("started", "")
            if started.startswith(date_query):
                total_seconds += wl.get("timeSpentSeconds", 0)
    return round(total_seconds / 3600, 2)


def delete_last_worklog(date_str=None):
    """
    Deletes the most recent worklog entry for the current user for the given date.
    Returns a dict: {success: bool, message: str}
    """
    from datetime import datetime

    if date_str:
        date_query = date_str
    else:
        date_query = datetime.now().strftime("%Y-%m-%d")
    url = f"{JIRA_BASE_URL}/rest/api/2/search"
    jql = f"worklogAuthor = currentUser() AND worklogDate = {date_query}"
    params = {
        "jql": jql,
        "fields": "worklog",
        "maxResults": 10,
    }
    response = requests.get(url, params=params, auth=(JIRA_USER, JIRA_API_TOKEN))
    if response.status_code != 200:
        return {"success": False, "message": "Failed to fetch worklogs."}
    data = response.json()
    last_wl = None
    last_issue = None
    for issue in data.get("issues", []):
        worklogs = issue.get("fields", {}).get("worklog", {}).get("worklogs", [])
        for wl in worklogs:
            started = wl.get("started", "")
            if started.startswith(date_query):
                if (not last_wl) or (
                    wl.get("started", "") > last_wl.get("started", "")
                ):
                    last_wl = wl
                    last_issue = issue
    if not last_wl or not last_issue:
        return {"success": False, "message": f"No worklog found for {date_query}."}
    # Delete the worklog
    issue_key = last_issue["key"]
    worklog_id = last_wl["id"]
    del_url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/worklog/{worklog_id}"
    del_resp = requests.delete(del_url, auth=(JIRA_USER, JIRA_API_TOKEN))
    if del_resp.status_code == 204:
        return {"success": True, "message": f"Deleted last worklog for {issue_key}."}
    else:
        return {
            "success": False,
            "message": f"Failed to delete worklog: {del_resp.text}",
        }


def delete_all_worklogs(date_str=None):
    """
    Deletes all worklog entries for the current user for the given date.
    Returns a dict: {success: bool, message: str, deleted: int}
    """
    logs = get_all_worklogs(date_str)
    if not logs:
        return {
            "success": False,
            "message": f"No worklogs found for {date_str or 'today'}.",
            "deleted": 0,
        }
    deleted = 0
    errors = []
    for log in logs:
        issue_key = log["issue_key"]
        worklog_id = log["worklog_id"]
        del_url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/worklog/{worklog_id}"
        del_resp = requests.delete(del_url, auth=(JIRA_USER, JIRA_API_TOKEN))
        if del_resp.status_code == 204:
            deleted += 1
        else:
            errors.append(f"{issue_key} ({worklog_id}): {del_resp.text}")
    if errors:
        return {
            "success": False,
            "message": f"Deleted {deleted} worklogs, but some failed: {'; '.join(errors)}",
            "deleted": deleted,
        }
    return {
        "success": True,
        "message": f"Deleted all {deleted} worklogs for {date_str or 'today'}.",
        "deleted": deleted,
    }


def get_all_worklogs(date_str=None):
    """
    Returns a list of all worklogs for the given date for the current user.
    Each entry: dict with keys: issue_key, summary, comment, time_spent, started, worklog_id
    """
    from datetime import datetime

    if date_str:
        date_query = date_str
    else:
        date_query = datetime.now().strftime("%Y-%m-%d")
    url = f"{JIRA_BASE_URL}/rest/api/2/search"
    jql = f"worklogAuthor = currentUser() AND worklogDate = {date_query}"
    params = {
        "jql": jql,
        "fields": "worklog,summary",
        "maxResults": 20,
    }
    response = requests.get(url, params=params, auth=(JIRA_USER, JIRA_API_TOKEN))
    if response.status_code != 200:
        return []
    data = response.json()
    logs = []
    for issue in data.get("issues", []):
        issue_key = issue.get("key")
        summary = issue.get("fields", {}).get("summary", "")
        worklogs = issue.get("fields", {}).get("worklog", {}).get("worklogs", [])
        for wl in worklogs:
            started = wl.get("started", "")
            if started.startswith(date_query):
                logs.append(
                    {
                        "issue_key": issue_key,
                        "summary": summary,
                        "comment": wl.get("comment", ""),
                        "time_spent": wl.get("timeSpent", ""),
                        "started": started,
                        "worklog_id": wl.get("id", ""),
                    }
                )
    # Sort by started time
    logs.sort(key=lambda x: x["started"])
    return logs


def main():
    try:
        commit_msg = (
            subprocess.check_output(["git", "log", "-1", "--pretty=%B"])
            .decode()
            .strip()
        )
    except Exception as e:
        commit_msg = "Auto-logged from script"

    # Only accept: python commit.py start OR python commit.py start -st <time> OR python commit.py start -p
    if len(sys.argv) > 1 and sys.argv[1] == "start":
        if len(sys.argv) == 2:
            set_start_time_manual()
            return
        elif len(sys.argv) == 4 and sys.argv[2] == "-st":
            st_time = sys.argv[3]
            set_start_time_manual(st_time)
            return
        elif len(sys.argv) == 3 and sys.argv[2] == "-p":
            print_start_time()
            return
        else:
            print(
                "Error: Invalid usage.\nUsage:\n"
                "  python commit.py start\n"
                "  python commit.py start -st <time> (e.g., python commit.py start -st 12:45pm)\n"
                "  python commit.py start -p"
            )
            sys.exit(1)

    ticket_key, hours, close_flag, start_time = extract_commit_info(commit_msg)
    comment = "On commit: " + extract_commit_comment(commit_msg)
    if ticket_key and hours:
        print(
            f"Detected JIRA info in commit message: {ticket_key}, {hours}, close: {close_flag}"
        )
        selected_ticket = ticket_key
        logged_time = hours
        close_ticket_flag = close_flag
        # Start time already saved in extract_commit_info if present
    else:
        if sys.stdin.isatty():
            print("Format: <ticket> <time> <close(y/N)> (e.g., AHPM-123 2h y)")
            inp = input(
                "Enter ticket, time, and close flag (leave blank to choose from list): "
            ).strip()
            if not inp:
                print("Fetching open JIRA tickets assigned to you...")
                issues = get_open_tickets()
                if not issues:
                    print("No open tickets assigned to you.")
                    return
                print("Open tickets:")
                for idx, issue in enumerate(issues, 1):
                    print(f"{idx}. {issue['key']} - {issue['fields']['summary']}")
                try:
                    ticket_index = int(input("Select a ticket number: ")) - 1
                    selected_ticket = issues[ticket_index]["key"]
                except (ValueError, IndexError):
                    print("Invalid selection.")
                    return
                logged_time = input("Enter hours to log (e.g., 1h 30m): ")

                close_ticket_flag = input(
                    "Do you want to close this ticket? (y/N): "
                ).strip()
            else:
                parts = inp.split()
                if len(parts) < 2:
                    print("Invalid input format.")
                    return
                selected_ticket = parts[0]
                logged_time = parts[1]
                close_ticket_flag = parts[2] if len(parts) > 2 else "N"
        else:
            print(
                "No JIRA info found in commit message and not running interactively. Skipping JIRA logging."
            )
            return

    print(f"Logging {logged_time} to JIRA issue {selected_ticket}...")
    log_work(selected_ticket, logged_time, comment)

    if close_ticket_flag.lower() == "c" or close_ticket_flag.lower() == "y":
        close_ticket(selected_ticket)

    set_start_time()  # Reset start time for next period


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_start_time_extraction()
    # Add CLI for deleting last log for today
    elif len(sys.argv) > 1 and sys.argv[1] == "undo_last_log":
        date_str = sys.argv[2] if len(sys.argv) > 2 else None
        result = delete_last_worklog(date_str)
        print(result["message"])
    # Add CLI for deleting all logs for a date
    elif len(sys.argv) > 1 and sys.argv[1] == "undo_all_today":
        date_str = sys.argv[2] if len(sys.argv) > 2 else None
        result = delete_all_worklogs(date_str)
        print(result["message"])
    else:
        main()
