def format_close_response(response):
    # Format the response for close intent
    if isinstance(response, dict):
        ticket = response.get("ticket")
        status = response.get("status")
        if status == "ok" and ticket:
            return f"Ticket {ticket} closed successfully."
        elif status == "ok":
            return "Ticket closed successfully."
        else:
            return str(response)
    return str(response)


# --- All imports moved to the top for clarity and best practices ---

import gradio as gr
import requests
import os
import openai
import re
import json
import threading
import time
from datetime import datetime, timedelta
from configs import Configs


# --- All imports moved to the top for clarity and best practices ---
def get_iso_date(date_obj):
    return date_obj.strftime("%Y-%m-%d")


def get_human_date(date_obj):
    today = datetime.now().date()
    date_str = date_obj.strftime("%d %b %Y")
    if date_obj == today:
        return f"Today, {date_str}"
    elif date_obj == today - timedelta(days=1):
        return f"Yesterday, {date_str}"
    elif date_obj == today + timedelta(days=1):
        return f"Tomorrow, {date_str}"
    else:
        return date_obj.strftime("%A, %d %b %Y")


MCP_SERVER_URL = "http://localhost:5000"
openai.api_key = Configs.OPENAI_API_KEY


def extract_command_ai(user_input):
    """
    Use OpenAI to extract intent and parameters from user input.
    Returns: dict with keys: intent, ticket, hours, comment, close, time, commit_msg
    """
    prompt = f"""You are an assistant for JIRA worklog automation. Extract the user's intent and parameters from the following command. 
Supported intents: start, tickets, close, log, commit, undo, undo_all, show_hours.
Return a JSON object with keys: intent, ticket, hours, comment, close, time, commit_msg.
If a key is not present, set it to null.
If the user command is ambiguous or does not specify a value, set the corresponding key to null.

Tickets are organized in a hierarchy: Project > Epic > Main Task > Ticket. Users may refer to tickets by project, epic, main task, or ticket key. If a user refers to a project, epic, or main task, try to infer the ticket key if possible, otherwise set ticket to null.

# --- Hierarchy Examples ---
User command: "Show me all tickets in Project Alpha."
Output: {{"intent": "tickets", "ticket": null, "hours": null, "comment": null, "close": null, "time": null, "commit_msg": null, "project": "Project Alpha"}}

User command: "Log 1 hour for the 'Speech Model' epic in Project Alpha."
Output: {{"intent": "log", "ticket": null, "hours": "1h", "comment": null, "close": null, "time": null, "commit_msg": null, "epic": "Speech Model", "project": "Project Alpha"}}

User command: "Log 45 minutes for main task 'Data Preprocessing' in Project Alpha."
Output: {{"intent": "log", "ticket": null, "hours": "45m", "comment": null, "close": null, "time": null, "commit_msg": null, "main_task": "Data Preprocessing", "project": "Project Alpha"}}

# --- All previous examples and scenarios retained below ---

# Updated for new terminology:
User command: "Undo last hour."
Output: {{"intent": "undo", "ticket": null, "hours": null, "comment": null, "close": null, "time": null, "commit_msg": null}}

User command: "Delete my last hours entry."
Output: {{"intent": "undo", "ticket": null, "hours": null, "comment": null, "close": null, "time": null, "commit_msg": null}}

User command: "Undo all hours for today."
Output: {{"intent": "undo_all", "ticket": null, "hours": null, "comment": null, "close": null, "time": null, "commit_msg": null}}

User command: "Delete all today's hours."
Output: {{"intent": "undo_all", "ticket": null, "hours": null, "comment": null, "close": null, "time": null, "commit_msg": null}}

User command: "Start my workday at 10am."
Output: {{"intent": "start", "ticket": null, "hours": null, "comment": null, "close": null, "time": "10am", "commit_msg": null}}

User command: "Show me my open tickets."
Output: {{"intent": "tickets", "ticket": null, "hours": null, "comment": null, "close": null, "time": null, "commit_msg": null}}

User command: "Close ticket AHPM-124."
Output: {{"intent": "close", "ticket": "AHPM-124", "hours": null, "comment": null, "close": "c", "time": null, "commit_msg": null}}

User command: "Log 45 minutes for AHPM-124. Updated documentation."
Output: {{"intent": "log", "ticket": "AHPM-124", "hours": "45m", "comment": "Updated documentation.", "close": null, "time": null, "commit_msg": null}}

User command: "Log 1 hour for AHPM-124 and close it. Fixed bug."
Output: {{"intent": "log", "ticket": "AHPM-124", "hours": "1h", "comment": "Fixed bug.", "close": "c", "time": null, "commit_msg": null}}

User command: "Log this commit: (AHPM-124 -h 2h) Fixed bug in login flow"
Output: {{"intent": "commit", "ticket": null, "hours": null, "comment": null, "close": null, "time": null, "commit_msg": "(AHPM-124 -h 2h) Fixed bug in login flow"}}

User command: "Log hours"
Output: {{"intent": "log", "ticket": null, "hours": null, "comment": null, "close": null, "time": null, "commit_msg": null}}

User command: "Log hours for AHPM-124: Speech Model Testing and Performance Benchmarking"
Output: {{"intent": "log", "ticket": "AHPM-124", "hours": null, "comment": null, "close": null, "time": null, "commit_msg": null}}

User command: "Show me all hours I logged today."
Output: {{"intent": "show_hours", "ticket": null, "hours": null, "comment": null, "close": null, "time": null, "commit_msg": null}}

User command: "List today's worklogs."
Output: {{"intent": "show_hours", "ticket": null, "hours": null, "comment": null, "close": null, "time": null, "commit_msg": null}}

User command: "{user_input}"
Output:
    """
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0,
    )
    # Parse JSON from response
    try:
        ai_json = response.choices[0].message.content
        params = json.loads(ai_json)
    except Exception:
        params = {
            "intent": None,
            "ticket": None,
            "hours": None,
            "comment": None,
            "close": None,
            "time": None,
            "commit_msg": None,
        }
    return params


def get_open_tickets():
    try:
        resp = requests.get(f"{MCP_SERVER_URL}/tickets")
        hierarchy = resp.json().get("tickets", {})
        display_list = []
        ticket_count = 0
        for project_id, project in hierarchy.items():
            project_name = project["name"]
            project_first_two = (
                " ".join(project_name.split()[:2])
                if project_name and project_name.lower() != "no project"
                else None
            )
            for epic_id, epic in project["epics"].items():
                epic_name = epic["name"]
                for main_task_id, main_task in epic["main_tasks"].items():
                    main_task_summary = main_task["summary"]
                    for ticket in main_task["tickets"]:
                        label_parts = []
                        if project_name and project_name.lower() != "no project":
                            label_parts.append(
                                f"🏢 {' '.join(project_name.split()[:2])}"
                            )
                        else:
                            label_parts.append("❓ No Project")
                        if epic_id and epic_id.lower() != "no epic":
                            label_parts.append(f"🏷️ {epic_id}")
                        if main_task_id and main_task_id.lower() != "no main task":
                            label_parts.append(f"🗂️ {main_task_id}")
                        ticket_part = f"🔖 {ticket['key']}: {ticket['summary']}"
                        label_parts.append(ticket_part)
                        label = " / ".join(label_parts)
                        full_parts = []
                        if project_name and project_name.lower() != "no project":
                            full_parts.append(f"🏢 {project_name}")
                        else:
                            full_parts.append("❓ No Project")
                        if epic_id and epic_id.lower() != "no epic":
                            full_parts.append(f"🏷️ {epic_id}: {epic_name}")
                        else:
                            full_parts.append("❓ No Epic")
                        if main_task_id and main_task_id.lower() != "no main task":
                            full_parts.append(f"🗂️ {main_task_id}: {main_task_summary}")
                        else:
                            full_parts.append("❓ No Main Task")
                        full_parts.append(f"🔖 {ticket['key']}: {ticket['summary']}")
                        full_label = " › ".join(full_parts)
                        display_list.append((label, ticket["key"], full_label))
                        ticket_count += 1
        return hierarchy, display_list, ticket_count
    except Exception as e:
        print(f"[get_open_tickets] Exception: {e}")
    return {}, [], 0


def normalize_hours(hours):
    """
    Normalize hours string to JIRA format: e.g. '2 hr', '2hr', '2 hours', '2 h' -> '2h'
    and '30 min', '30min', '30 minutes', '30 m' -> '30m'
    Handles combinations like '1 hour 30 min' -> '1h 30m'
    Ensures a space between each time unit (e.g. '1h 15m').



    """
    if not hours:
        return hours
    import re

    s = hours.lower()
    # Replace all hour variants with 'h'
    s = re.sub(r"\b(\d+)\s*(h|hr|hrs|hour|hours)\b", r"\1h", s)
    # Replace all minute variants with 'm'
    s = re.sub(r"\b(\d+)\s*(m|min|mins|minute|minutes)\b", r"\1m", s)
    # Remove all spaces
    s = s.replace(" ", "")
    # Insert a space between each time unit (e.g. '1h15m' -> '1h 15m')
    s = re.sub(r"([hm])", r"\1 ", s).strip()
    # Remove trailing space if any
    s = s.strip()
    return s


def call_mcp_server(user_input, history):
    user_input = user_input.strip()
    response = ""
    print(f"[call_mcp_server] User input: {user_input}")
    try:
        params = extract_command_ai(user_input)
        print(f"[call_mcp_server] Extracted params: {params}")
        selected_ticket = None
        if "\n" in user_input:
            first_line = user_input.split("\n")[0].strip()
            import re

            if re.match(r"^[A-Z]+-\d+$", first_line):
                selected_ticket = first_line
        intent = params.get("intent")
        if intent == "log" and (not params.get("ticket")) and selected_ticket:
            params["ticket"] = selected_ticket
            print(
                f"[call_mcp_server] Patched ticket from UI selection: {selected_ticket}"
            )
        print(f"[call_mcp_server] Intent: {intent}")

        is_refresh_open_tickets = False
        is_close_refresh = False
        # If the user is logging and also closing a ticket, set refresh_open_tickets True and is_close_refresh True
        if intent == "log" and (params.get("close") or "N").lower() in [
            "c",
            "y",
            "yes",
            "true",
        ]:
            is_close_refresh = True
        if intent == "start":
            resp = requests.post(
                f"{MCP_SERVER_URL}/start", json={"time": params.get("time")}
            )
            response = resp.json()
            print(f"[call_mcp_server] /start response: {response}")
        elif intent == "tickets":
            hierarchy, _, ticket_count = get_open_tickets()
            is_refresh_open_tickets = True
            if hierarchy:

                def html_escape(text):
                    import html

                    return html.escape(str(text))

                def render_tickets_hierarchy(hierarchy):
                    html_lines = []
                    for project_id, project in hierarchy.items():
                        project_name = project.get("name", "No Project")
                        project_icon = (
                            "🏢"
                            if project_name and project_name.lower() != "no project"
                            else "❓"
                        )
                        html_lines.append(
                            f"<div style='margin-top:0.5em; font-weight:700;'>{project_icon} {html_escape(project_name)}</div>"
                        )
                        epics = project.get("epics", {})
                        for epic_id, epic in epics.items():
                            epic_name = epic.get("name", "")
                            if epic_id and epic_id.lower() != "no epic":
                                epic_icon = "🏷️"
                                html_lines.append(
                                    f"<div style='margin-left:1.5em; font-weight:600;'>{epic_icon} {html_escape(epic_id)}: {html_escape(epic_name)}</div>"
                                )
                                main_tasks = epic.get("main_tasks", {})
                                for main_task_id, main_task in main_tasks.items():
                                    main_task_summary = main_task.get("summary", "")
                                    if (
                                        main_task_id
                                        and main_task_id.lower() != "no main task"
                                    ):
                                        main_task_icon = "🗂️"
                                        html_lines.append(
                                            f"<div style='margin-left:3em; font-weight:500;'>{main_task_icon} {html_escape(main_task_id)}: {html_escape(main_task_summary)}</div>"
                                        )
                                        tickets = main_task.get("tickets", [])
                                        for ticket in tickets:
                                            ticket_key = ticket.get("key", "?")
                                            ticket_summary = ticket.get("summary", "")
                                            ticket_icon = "🔖"
                                            html_lines.append(
                                                f"<div style='margin-left:4.5em; font-weight:400;'>{ticket_icon} {html_escape(ticket_key)}: {html_escape(ticket_summary)}</div>"
                                            )
                                    else:
                                        tickets = main_task.get("tickets", [])
                                        for ticket in tickets:
                                            ticket_key = ticket.get("key", "?")
                                            ticket_summary = ticket.get("summary", "")
                                            ticket_icon = "🔖"
                                            html_lines.append(
                                                f"<div style='margin-left:3em; font-weight:400;'>{ticket_icon} {html_escape(ticket_key)}: {html_escape(ticket_summary)}</div>"
                                            )
                            else:
                                main_tasks = epic.get("main_tasks", {})
                                for main_task_id, main_task in main_tasks.items():
                                    main_task_summary = main_task.get("summary", "")
                                    if (
                                        main_task_id
                                        and main_task_id.lower() != "no main task"
                                    ):
                                        main_task_icon = "🗂️"
                                        html_lines.append(
                                            f"<div style='margin-left:1.5em; font-weight:500;'>{main_task_icon} {html_escape(main_task_id)}: {html_escape(main_task_summary)}</div>"
                                        )
                                        tickets = main_task.get("tickets", [])
                                        for ticket in tickets:
                                            ticket_key = ticket.get("key", "?")
                                            ticket_summary = ticket.get("summary", "")
                                            ticket_icon = "🔖"
                                            html_lines.append(
                                                f"<div style='margin-left:3em; font-weight:400;'>{ticket_icon} {html_escape(ticket_key)}: {html_escape(ticket_summary)}</div>"
                                            )
                                    else:
                                        tickets = main_task.get("tickets", [])
                                        for ticket in tickets:
                                            ticket_key = ticket.get("key", "?")
                                            ticket_summary = ticket.get("summary", "")
                                            ticket_icon = "🔖"
                                            html_lines.append(
                                                f"<div style='margin-left:1.5em; font-weight:400;'>{ticket_icon} {html_escape(ticket_key)}: {html_escape(ticket_summary)}</div>"
                                            )
                    return "\n".join(html_lines)

                response = (
                    f"<div style='font-weight:600; margin-bottom:0.5em;'>Open Tickets - {ticket_count} (🏢 Project &gt; 🏷️ Epic &gt; 🗂️ Main Task &gt; 🔖 Ticket)</div>"
                    + render_tickets_hierarchy(hierarchy)
                    + "<div style='margin-top:1em;'>You can also use the Open Tickets to select a ticket and log hours.</div>"
                )
            else:
                response = "No open tickets found."
        elif intent == "close":
            ticket = params.get("ticket")
            if ticket:
                resp = requests.post(f"{MCP_SERVER_URL}/close", json={"ticket": ticket})
                response_json = resp.json()
                print(f"[call_mcp_server] /close response: {response_json}")
                if response_json.get("status") == "ok":
                    response = format_close_command_response(response_json)
                else:
                    error_msg = (
                        response_json.get("error")
                        or response_json.get("message")
                        or str(response_json)
                    )
                    response = f"Failed to close ticket: {error_msg}"
                is_close_refresh = True
            else:
                response = "Please specify a ticket key to close."
        elif intent == "log":
            ticket = params.get("ticket")
            hours = params.get("hours")
            comment = params.get("comment")
            close = params.get("close") or "N"
            hours = normalize_hours(hours)
            print(
                f"[call_mcp_server] Logging: ticket={ticket}, hours={hours}, comment={comment}, close={close}"
            )
            if ticket and hours and comment:
                resp = requests.post(
                    f"{MCP_SERVER_URL}/log",
                    json={
                        "ticket": ticket,
                        "hours": hours,
                        "comment": comment,
                        "close": close,
                    },
                )
                response_json = resp.json()
                print(f"[call_mcp_server] /log response: {response_json}")
                if response_json.get("status") == "ok":
                    response = format_log_command_response(response_json)
                else:
                    # If not ok, show error or fallback message
                    error_msg = (
                        response_json.get("error")
                        or response_json.get("message")
                        or str(response_json)
                    )
                    response = f"Failed to log hours: {error_msg}"
            else:
                response = (
                    "Missing ticket, hours, or comment. "
                    "Tip: Use the 'Open Tickets' list on the left to select a ticket, then enter hours and a comment to log hours."
                )
        elif intent == "commit":
            commit_msg = params.get("commit_msg")
            print(f"[call_mcp_server] Commit message: {commit_msg}")
            if commit_msg:
                resp = requests.post(
                    f"{MCP_SERVER_URL}/commit", json={"commit_msg": commit_msg}
                )
                response = resp.json()
                print(f"[call_mcp_server] /commit response: {response}")
            else:
                response = "Missing commit message."
        elif intent == "undo":
            resp = requests.post(f"{MCP_SERVER_URL}/undo_last_log")
            result = resp.json()
            if result.get("success"):
                response = result.get("message", "Last hour deleted.")
            else:
                response = f"Undo failed: {result.get('message', 'Unknown error')}"
            print(f"[call_mcp_server] /undo_last_log response: {result}")
        elif intent == "undo_all":
            resp = requests.post(f"{MCP_SERVER_URL}/undo_all_logs_today")
            result = resp.json()
            if result.get("success"):
                response = result.get("message", "All today's hours deleted.")
            else:
                response = f"Undo all failed: {result.get('message', 'Unknown error')}"
            print(f"[call_mcp_server] /undo_all_logs_today response: {result}")
        elif intent == "show_hours":
            # Use the selected_date from state or default to today
            try:
                selected_date = params.get("selected_date") if params else None
                if not selected_date:
                    selected_date = today
            except Exception:
                selected_date = today
            logs_text = fetch_worklogs(selected_date)
            response = logs_text
            print(f"[call_mcp_server] show_hours response: {logs_text}")
        else:
            response = (
                "You can use natural language commands, e.g.:\n"
                "- 'Start my workday at 09:30am.'\n"
                "- 'Show my open tickets.'\n"
                "- 'Log 2 hours for AHPM-124: Fixed login bug and close it.'\n"
                "- 'Close ticket AHPM-124.'\n"
                "- 'Log this commit: (AHPM-124 -h 2h) Fixed bug.'\n"
                "- Or use the dropdown below to select a ticket and log hours."
            )
            print(f"[call_mcp_server] Fallback response.")
        # Patch history for undo/undo_all to use new terminology in chat
        if intent == "undo":
            history = history + [("Undo last hour", str(response))]
        elif intent == "undo_all":
            history = history + [("Undo all hours for today", str(response))]
        else:
            history = history + [(user_input, str(response))]
        print(f"[call_mcp_server] Updated history: {history[-1]}")
        return history, history, is_refresh_open_tickets, is_close_refresh, intent
    except Exception as e:
        response = f"Error: {str(e)}"
        print(f"[call_mcp_server] Exception: {e}")
        return (
            history + [(user_input, str(response))],
            history + [(user_input, str(response))],
            False,
            False,
            None,
        )


# Remove fetch_hours_today (no longer used)

with gr.Blocks() as demo:
    import gradio

    today = datetime.now()
    date_state = gr.State(today)

    with gr.Row():
        prev_btn = gr.Button("←")
        date_picker = gr.DateTime(
            value=today,
            label="Select Date",
            show_label=False,
            include_time=False,
            type="datetime",
            elem_id="date-picker-field",
        )
        next_btn = gr.Button("→")

    # --- Add hours logged today at the top using a Label for minimal layout shift ---
    # Move this above the button handlers so it can be referenced

    def refresh_hours_label(selected_date):
        try:
            resp = requests.get(
                f"{MCP_SERVER_URL}/hours", params={"date": get_iso_date(selected_date)}
            )
            hours = resp.json().get("hours", 0.0)
            # Format the date for display
            if hasattr(selected_date, "date"):
                date_obj = selected_date.date()
            else:
                date_obj = selected_date
            human_date = get_human_date(date_obj)
            return f"{human_date} — Hours: {hours} h"
        except Exception:
            return "Hours: N/A"

    hours_today_box = gr.Label(
        value=refresh_hours_label,
        inputs=[date_state],
        every=5.0,
        elem_id="hours-today-box",
    )

    def set_date(new_date):
        # Accepts a datetime, returns datetime and human label
        if not isinstance(new_date, datetime):
            try:
                new_date_obj = datetime.fromisoformat(str(new_date))
            except Exception:
                new_date_obj = datetime.now()
        else:
            new_date_obj = new_date
        return new_date_obj

    def move_date(date_obj, delta_days):
        # Accepts a datetime, returns new datetime and state (for Gradio output)
        if not isinstance(date_obj, datetime):
            try:
                date_obj = datetime.fromisoformat(str(date_obj))
            except Exception:
                date_obj = datetime.now()
        new_date = date_obj + timedelta(days=delta_days)
        # Return for both date_picker and date_state
        return new_date, new_date

    date_picker.change(
        set_date,
        [date_picker],
        [date_state],
    )
    prev_btn.click(
        move_date,
        [date_picker, gr.State(-1)],
        [date_picker, date_state],
    ).then(
        refresh_hours_label,
        [date_state],
        [hours_today_box],
    )
    next_btn.click(
        move_date,
        [date_picker, gr.State(1)],
        [date_picker, date_state],
    ).then(
        refresh_hours_label,
        [date_state],
        [hours_today_box],
    )
    # --- Add hours logged today at the top using a Label for minimal layout shift ---

    def fetch_worklogs(selected_date):
        try:
            resp = requests.get(
                f"{MCP_SERVER_URL}/worklogs",
                params={"date": get_iso_date(selected_date)},
            )
            logs = resp.json().get("worklogs", [])
            if not logs:
                return "No logs for this date."
            lines = []
            for log in logs:
                started_raw = log.get("started", "")
                try:
                    dt = datetime.strptime(started_raw[:19], "%Y-%m-%dT%H:%M:%S")
                    started_fmt = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    started_fmt = started_raw
                lines.append(
                    f"**{log['issue_key']} ({log['time_spent']})** *{log['summary']}*\n"
                    f"{log['comment']}  {started_fmt}"
                )
            return "\n\n".join(lines)
        except Exception as e:
            return f"Error fetching logs: {str(e)}"

    # --- Move ticket selection to a vertical list on the top left, rest of UI to the right ---
    with gr.Row():
        with gr.Column(scale=1, min_width=300):  # increased min_width for more space
            # Only allow selection of actual tickets (not project/epic/main task headers)
            ticket_list = gr.Radio(
                choices=[],
                label="Open Tickets (🏢 Project > 🏷️ Epic > 🗂️ Main Task > 🔖 Ticket)",  # This will be dynamically updated
                interactive=True,
                elem_id="ticket-list",
                show_label=True,
            )
            ticket_info_md = gr.Markdown(value="", visible=False)
        with gr.Column(scale=3):
            # Everything else goes here, so ticket list is always visible from top

            # # Always refresh on first UI load, every 10 seconds, and on page refresh
            # demo.load(
            #     refresh_hours_label,
            #     inputs=[date_state],
            #     outputs=hours_today_box,
            #     queue=False,
            #     every=5.0,  # Pass as float (seconds), not Timer object
            # )
            # hours_today_box now refreshes itself every 5 seconds using the new gr.Label API

            chatbot = gr.Chatbot()
            state = gr.State([])
            selected_ticket_state = gr.State(None)
            confirm_undo_state = gr.State(False)
            confirm_undo_all_state = gr.State(False)
            with gr.Row():
                hours_box = gr.Textbox(label="Hours (e.g. 1h 30m)", max_lines=1)
                comment_box = gr.Textbox(label="Comment", max_lines=1)
                log_btn = gr.Button("Log Hours", elem_id="log-hours-btn")
                with gr.Row():
                    undo_btn = gr.Button("Undo Last Hour", elem_id="undo-last-hour-btn")
                    undo_all_btn = gr.Button(
                        "Undo All Hours", elem_id="undo-all-hours-btn"
                    )
                list_logs_btn = gr.Button("List Logs", elem_id="list-logs-btn")
            txt = gr.Textbox(
                show_label=False, placeholder="Type your command and press Enter"
            )

    # --- ADD: CSS for scrollable open ticket list with max height ---
    demo.css = (
        (getattr(demo, "css", "") or "")
        + """
    #ticket-list {
        max-height: 80vh !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        padding-right: 6px !important;
        box-sizing: border-box !important;
    }
    /* Fallback: some Gradio versions wrap options */
    #ticket-list .wrap, #ticket-list .container, #ticket-list > div {
        max-height: 80vh !important;
        overflow-y: auto !important;
    }
    /* Scrollbar styling */
    #ticket-list::-webkit-scrollbar {
        width: 8px;
    }
    #ticket-list::-webkit-scrollbar-track {
        background: #f1f1f1;
    }
    #ticket-list::-webkit-scrollbar-thumb {
        background: #b5b5b5;
        border-radius: 4px;
    }
    #ticket-list::-webkit-scrollbar-thumb:hover {
        background: #999;
    }
    /* OVERRIDES to remove inner duplicate scrollbars */
    #ticket-list .wrap,
    #ticket-list .container,
    #ticket-list > div {
        overflow: visible !important;
        max-height: none !important;
    }
    /* Ensure only outer element scrolls */
    #ticket-list {
        overflow-y: auto !important;
    }
    """
    )

    # --- When a ticket is selected from the list, store its label for logging ---
    selected_ticket_tuple_state = gr.State((None, ""))
    display_list_state = gr.State([])

    def on_ticket_select(ticket_label, display_list):
        # Use cached display_list to map label to ticket key and hierarchy string
        for label, key, hierarchy_str in display_list:
            if label == ticket_label:
                return (key, hierarchy_str), display_list
        return (None, ""), display_list

    def update_ticket_info_md(selected_ticket_tuple, display_list):
        # Accepts (key, hierarchy_str) tuple and the full display_list
        if (
            selected_ticket_tuple
            and isinstance(selected_ticket_tuple, tuple)
            and selected_ticket_tuple[0]
            and display_list
        ):
            selected_ticket_key = selected_ticket_tuple[0]
            full_label = (
                selected_ticket_tuple[1] if len(selected_ticket_tuple) > 1 else ""
            )
            if not full_label:
                return gr.update(value="", visible=False)
            jira_base_url = "https://bitlogix.atlassian.net/browse/"
            dashboard_url = "https://bitlogix.atlassian.net/jira/dashboards/10172"
            import re

            parts = [p.strip() for p in full_label.split("›")]
            # Try to infer project key from the ticket id (e.g., AHPM-124 -> AHPM)
            ticket_key = None
            for part in parts:
                m = re.match(r"🔖 ([A-Z]+-\d+):", part)
                if m:
                    ticket_key = m.group(1)
                    break
            project_key = ticket_key.split("-")[0] if ticket_key else None
            links = []
            for part in parts:
                # Project (use inferred project_key from ticket id)
                m = re.match(r"🏢 ([^›:]+)", part)
                if m and project_key:
                    links.append(
                        f"<a href='{jira_base_url}{project_key}' target='_blank' style='font-weight:600;text-decoration:underline;'>{part}</a>"
                    )
                    continue
                elif m:
                    links.append(f"<span style='font-weight:600;'>{part}</span>")
                    continue
                # Epic
                m = re.match(r"🏷️ ([A-Z]+-\d+):", part)
                if m:
                    epic_key = m.group(1)
                    links.append(
                        f"<a href='{jira_base_url}{epic_key}' target='_blank' style='font-weight:600;text-decoration:underline;'>{part}</a>"
                    )
                    continue
                # Main Task
                m = re.match(r"🗂️ ([A-Z]+-\d+):", part)
                if m:
                    main_task_key = m.group(1)
                    links.append(
                        f"<a href='{jira_base_url}{main_task_key}' target='_blank' style='font-weight:600;text-decoration:underline;'>{part}</a>"
                    )
                    continue
                # Ticket
                m = re.match(r"🔖 ([A-Z]+-\d+):", part)
                if m:
                    tkey = m.group(1)
                    links.append(
                        f"<a href='{jira_base_url}{tkey}' target='_blank' style='font-weight:600;text-decoration:underline;'>{part}</a>"
                    )
                    continue
                # Fallback: just display as text
                links.append(f"<span>{part}</span>")
            # Format as hierarchy like show tickets
            indent_map = {
                0: 0,  # Project
                1: 1,  # Epic
                2: 2,  # Main Task
                3: 3,  # Ticket
            }
            lines = []
            for i, link in enumerate(links):
                indent = indent_map.get(i, 0)
                lines.append(f"<div style='margin-left:{indent*1.5}em'>{link}</div>")
            md = (
                f"<div style='margin-bottom:0.5em;'><a href='{dashboard_url}' target='_blank' style='font-weight:700; color:#1976d2; text-decoration:underline;'>📊 Open JIRA Dashboard</a></div>"
                + "<div style='font-weight:600; margin-bottom:0.5em;'>Selected Ticket :</div>"
                + "\n".join(lines)
            )
            return gr.update(value=md, visible=True)
        else:
            return gr.update(value="", visible=False)

    # When a ticket is selected, get both the tuple and the display_list, then pass both to update_ticket_info_md
    # On ticket selection, use cached display_list for instant update
    ticket_list.change(
        on_ticket_select,
        [ticket_list, display_list_state],
        [selected_ticket_tuple_state, display_list_state],
    ).then(
        update_ticket_info_md,
        [selected_ticket_tuple_state, display_list_state],
        [ticket_info_md],
    )

    # --- Update log_hours_dropdown to use selected_ticket_state ---
    def log_hours_dropdown(selected_ticket_label, hours, comment, history):
        # Default unit to hours if not specified
        import re

        hours_input = hours.strip() if hours else ""
        hours_input = normalize_hours(hours_input)
        # If user enters only a number (e.g. "1"), treat as "1h" (not "1m")
        if hours_input and re.fullmatch(r"\d+(\.\d+)?", hours_input):
            hours_input = f"{hours_input}h"
        # selected_ticket_label is now the ticket key directly
        ticket_key = selected_ticket_label
        # --- Add logging for dropdown log ---
        print(f"[log_hours_dropdown] Selected ticket label: {selected_ticket_label}")
        print(f"[log_hours_dropdown] Ticket key: {ticket_key}")
        print(f"[log_hours_dropdown] Hours input: {hours_input}")
        print(f"[log_hours_dropdown] Comment: {comment}")
        if not ticket_key or not hours_input or not comment:
            response = "Please select a ticket, enter hours, and a comment."
        else:
            try:
                resp = requests.post(
                    f"{MCP_SERVER_URL}/log",
                    json={
                        "ticket": ticket_key,
                        "hours": hours_input,
                        "comment": comment,
                        "close": "N",
                    },
                )
                response = resp.json()
                print(f"[log_hours_dropdown] /log response: {response}")
            except Exception as e:
                response = f"Error: {str(e)}"
                print(f"[log_hours_dropdown] Exception: {e}")
        history = history + [
            (f"Log {hours_input} for {ticket_key}: {comment}", str(response))
        ]
        print(f"[log_hours_dropdown] Updated history: {history[-1]}")
        return history, history

    # Confirmation state for undo
    confirm_undo_state = gr.State(False)
    # Confirmation state for undo all
    confirm_undo_all_state = gr.State(False)

    def ask_undo_confirmation(history):
        history = history + [
            (
                "Undo Last Hour",
                "Are you sure you want to undo the last hour? Click 'Undo Last Hour' again to confirm.",
            )
        ]
        return history, history, True

    def ask_undo_all_confirmation(history):
        history = history + [
            (
                "Undo All Hours",
                "Are you sure you want to undo ALL hours for today? Click 'Undo All Hours' again to confirm.",
            )
        ]
        return history, history, True

    def do_undo_last_log(history, confirm, date=None):
        if not confirm:
            # First click, ask for confirmation
            return ask_undo_confirmation(history)
        # Second click, perform undo
        try:
            payload = {}
            if date:
                # Convert date to string if it's a date object
                if hasattr(date, "strftime"):
                    payload["date"] = date.strftime("%Y-%m-%d")
                else:
                    payload["date"] = str(date)
            resp = requests.post(f"{MCP_SERVER_URL}/undo_last_log", json=payload)
            if not resp.text.strip():
                response = (
                    "Undo failed: No response from server. Please check backend logs."
                )
            else:
                try:
                    result = resp.json()
                    if result.get("success"):
                        response = result.get("message", "Last hour deleted.")
                    else:
                        response = (
                            f"Undo failed: {result.get('message', 'Unknown error')}"
                        )
                except Exception as e:
                    response = f"Undo failed: Invalid server response. {str(e)}"
        except Exception as e:
            response = f"Error: {str(e)}"
        history = history + [("Undo Last Hour", response)]
        return history, history, False

    def do_undo_all_logs(history, confirm, date=None):
        if not confirm:
            # First click, ask for confirmation
            return ask_undo_all_confirmation(history)
        # Second click, perform undo all
        try:
            payload = {}
            if date:
                if hasattr(date, "strftime"):
                    payload["date"] = date.strftime("%Y-%m-%d")
                else:
                    payload["date"] = str(date)
            resp = requests.post(f"{MCP_SERVER_URL}/undo_all_logs", json=payload)
            if not resp.text.strip():
                response = "Undo all failed: No response from server. Please check backend logs."
            else:
                try:
                    result = resp.json()
                    if result.get("success"):
                        response = result.get("message", "All hours deleted.")
                    else:
                        response = (
                            f"Undo all failed: {result.get('message', 'Unknown error')}"
                        )
                except Exception as e:
                    response = f"Undo all failed: Invalid server response. {str(e)}"
        except Exception as e:
            response = f"Error: {str(e)}"
        history = history + [("Undo All Hours", response)]
        return history, history, False

    def reset_undo_confirmation(*args):
        # Always reset confirmation state to False
        return False

    # No need for a separate reset_undo_all_confirmation function,
    # since reset_undo_confirmation can be used for both states.
    # This is correct and efficient.

    # Add Undo Last Log button handler
    def undo_last_log(history):
        try:
            resp = requests.post(f"{MCP_SERVER_URL}/undo_last_log")
            result = resp.json()
            if result.get("success"):
                response = result.get("message", "Last hour deleted.")
            else:
                response = f"Undo failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            response = f"Error: {str(e)}"
        history = history + [("Undo last hour", response)]
        return history, history

    # Add Undo All Today's Logs button handler
    def undo_all_logs_today(history):
        try:
            resp = requests.post(f"{MCP_SERVER_URL}/undo_all_logs_today")
            result = resp.json()
            if result.get("success"):
                response = result.get("message", "All today's hours deleted.")
            else:
                response = f"Undo all failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            response = f"Error: {str(e)}"
        history = history + [("Undo all hours for today", response)]
        return history, history

    def list_logs_on_chat(history, selected_date):
        logs_text = fetch_worklogs(selected_date)
        history = history + [
            (f"List logs for {get_iso_date(selected_date)}", logs_text)
        ]
        return history, history

    # Update dropdown choices on load and every 5 seconds in the background
    def refresh_open_tickets():
        _, display_list, ticket_count = get_open_tickets()
        return (
            gr.update(
                choices=[label for label, key, _ in display_list],
                label=f"Open Tickets - {ticket_count} (🏢 Project > 🏷️ Epic > 🗂️ Main Task > 🔖 Ticket)",
            ),
            display_list,
        )

    # Always refresh ticket list on load and every 5 seconds, and also allow one-time refresh after user_submit
    # Removed periodic refresh of open tickets to avoid excessive API calls

    # Also refresh ticket list once on initial page load
    demo.load(
        refresh_open_tickets,
        None,
        [ticket_list, display_list_state],
        queue=False,
    )

    log_btn.click(
        log_hours_dropdown,
        [selected_ticket_state, hours_box, comment_box, state, date_state],
        [chatbot, state],
    ).then(
        refresh_hours_label,
        [date_state],
        [hours_today_box],
    ).then(
        reset_undo_confirmation,
        [],
        [confirm_undo_state],
    ).then(
        reset_undo_confirmation,
        [],
        [confirm_undo_all_state],
    )
    undo_btn.click(
        do_undo_last_log,
        [state, confirm_undo_state, date_state],
        [chatbot, state, confirm_undo_state],
    ).then(
        refresh_hours_label,
        [date_state],
        [hours_today_box],
    )
    undo_all_btn.click(
        do_undo_all_logs,
        [state, confirm_undo_all_state, date_state],
        [chatbot, state, confirm_undo_all_state],
    ).then(
        refresh_hours_label,
        [date_state],
        [hours_today_box],
    )
    list_logs_btn.click(
        list_logs_on_chat,
        [state, date_state],
        [chatbot, state],
    ).then(
        refresh_hours_label,
        [date_state],
        [hours_today_box],
    ).then(
        reset_undo_confirmation,
        [],
        [confirm_undo_state],
    ).then(
        reset_undo_confirmation,
        [],
        [confirm_undo_all_state],
    )

    # Function to handle user text input submit (fixes NameError)
    def user_submit(user_input, history, selected_ticket_tuple, selected_date):
        import re

        merged_input = user_input
        ticket_key = None
        if selected_ticket_tuple and isinstance(selected_ticket_tuple, tuple):
            ticket_key = selected_ticket_tuple[0]
        user_input_lower = user_input.strip().lower()
        # Only prepend ticket for log or close commands if ticket is selected and not already present
        if (
            ticket_key
            and (
                user_input_lower.startswith("log")
                or user_input_lower.startswith("close")
            )
            and ticket_key not in user_input
        ):
            merged_input = f"{ticket_key}\n{user_input}".strip()

        # Make selected_date available to backend if needed
        # If selected_date is a string, parse to date
        if isinstance(selected_date, str):
            try:
                selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
            except Exception:
                selected_date_obj = datetime.now().date()
        else:
            selected_date_obj = selected_date

        # Optionally, patch the user_input or state with the date if needed by backend
        # If your backend expects the date in the input, you can add it here
        # For now, just call as before
        history, state, is_refresh_open_tickets, is_close_refresh, intent = (
            call_mcp_server(merged_input, history)
        )
        # Only refresh ticket list and selected ticket if needed
        if is_refresh_open_tickets or is_close_refresh:
            if is_close_refresh:
                time.sleep(1)
            ticket_choices_update, display_list = refresh_open_tickets()
            selected_ticket_tuple_new = selected_ticket_tuple
            # Try to preserve selected ticket after refresh
            if selected_ticket_tuple and isinstance(selected_ticket_tuple, tuple):
                prev_key = selected_ticket_tuple[0]
                for label, key, full_label in display_list:
                    if key == prev_key:
                        selected_ticket_tuple_new = (key, full_label)
                        break
                else:
                    selected_ticket_tuple_new = (None, "")
            return (
                history,
                state,
                ticket_choices_update,
                display_list,
                selected_ticket_tuple_new,
            )
        else:
            # No refresh: return unchanged ticket list and selection
            return history, state, gr.update(), gr.update(), selected_ticket_tuple

    txt.submit(
        user_submit,
        [txt, state, selected_ticket_tuple_state, date_state],
        [chatbot, state, ticket_list, display_list_state],
    ).then(
        refresh_hours_label,
        [date_state],
        [hours_today_box],
    ).then(
        reset_undo_confirmation,
        [],
        [confirm_undo_state],
    ).then(
        reset_undo_confirmation,
        [],
        [confirm_undo_all_state],
    )

    # Add a function to clear the textbox when the chatbot is updated
    def clear_textbox(*args):
        return "", "", ""  # Clear txt, hours_box, comment_box

    # Whenever the chatbot is updated, clear the textbox, hours, and comment fields
    chatbot.change(clear_textbox, inputs=None, outputs=[txt, hours_box, comment_box])

    # Improved JS: scroll to bottom after each update using setTimeout and more robust selector
    gr.HTML(
        """
        <script>
        function scrollChatToBottom() {
            // Try both gradio v3 and v4 selectors
            let chat = document.querySelector('.gr-chatbot, .svelte-chatbot');
            if (chat) {
                chat.scrollTop = chat.scrollHeight;
            }
        }
        // Observe DOM changes and scroll after a short delay
        const observer = new MutationObserver(function(mutations, obs) {
            setTimeout(scrollChatToBottom, 100);
        });
        window.addEventListener('DOMContentLoaded', function() {
            let chat = document.querySelector('.gr-chatbot, .svelte-chatbot');
            if (chat) {
                observer.observe(chat, { childList: true, subtree: true });
                scrollChatToBottom();
            }
        });
        </script>
        """
    )


def test_extract_command_ai():
    test_cases = [
        # Start workday
        ("Start my workday at 10am.", {"intent": "start", "time": "10am"}),
        ("Begin work at 09:30am.", {"intent": "start", "time": "09:30am"}),
        ("Start", {"intent": "start", "time": None}),
        # Tickets
        ("Show me my open tickets.", {"intent": "tickets"}),
        ("List all tickets assigned to me.", {"intent": "tickets"}),
        ("Tickets", {"intent": "tickets"}),
        # Close
        ("Close ticket AHPM-124.", {"intent": "close", "ticket": "AHPM-124"}),
        ("Mark AHPM-124 as done.", {"intent": "close", "ticket": "AHPM-124"}),
        ("Close AHPM-124", {"intent": "close", "ticket": "AHPM-124"}),
        # Log
        (
            "Log 45 minutes for AHPM-124. Updated documentation.",
            {"intent": "log", "ticket": "AHPM-124", "hours": "45m"},
        ),
        (
            "Log 1 hour for AHPM-124 and close it. Fixed bug.",
            {"intent": "log", "ticket": "AHPM-124", "hours": "1h", "close": "c"},
        ),
        (
            "Log AHPM-124 2h Fixed login bug c",
            {"intent": "log", "ticket": "AHPM-124", "hours": "2h", "close": "c"},
        ),
        # Commit
        (
            "Log this commit: (AHPM-124 -h 2h) Fixed bug in login flow",
            {
                "intent": "commit",
                "commit_msg": "(AHPM-124 -h 2h) Fixed bug in login flow",
            },
        ),
        (
            "Commit (AHPM-124 -h 1h 30m) Refactored code",
            {"intent": "commit", "commit_msg": "(AHPM-124 -h 1h 30m) Refactored code"},
        ),
    ]
    results = []
    for idx, (cmd, expected) in enumerate(test_cases):
        print("=" * 60)
        print(f"Test {idx+1}: {cmd}")
        params = extract_command_ai(cmd)
        print("Extracted:", params)
        # Check coverage for main keys in expected
        coverage = "PASS"
        for k, v in expected.items():
            if params.get(k) != v:
                coverage = "FAIL"
                print(f"  Mismatch: {k} -> expected {v}, got {params.get(k)}")
        results.append((cmd, coverage, params))
    print("=" * 60)
    print("\nTest Coverage Report:")
    print(f"{'Command':<45} {'Result':<6} {'Extracted'}")
    print("-" * 90)
    for cmd, cov, params in results:
        print(f"{cmd[:44]:<45} {cov:<6} {str(params)}")
    print("-" * 90)
    total = len(test_cases)
    passed = sum(1 for r in results if r[1] == "PASS")
    failed = sum(1 for r in results if r[1] == "FAIL")
    percent = round((passed / total) * 100, 2) if total else 0
    print(
        f"Total: {total} | Passed: {passed} | Failed: {failed} | Coverage: {percent}%"
    )


# --- Response formatting helpers for log and close commands ---
def format_log_command_response(response):
    # Handles both log and log+close responses
    if isinstance(response, dict):
        hours = response.get("hours")
        ticket = response.get("ticket")
        status = response.get("status")
        comment = response.get("comment")
        closed = response.get("closed") or response.get("close")
        # Enforce hours, ticket, and comment are compulsory; closed is optional
        if status == "ok":
            if not hours or not ticket or not comment:
                return "Error: Missing required information. Please provide hours, ticket, and comment."
            if closed in ["c", "y", "yes", "true", "closed", True]:
                msg = f"Successfully logged {hours} to ticket {ticket}: {comment}, and closed it."
            else:
                msg = f"Successfully logged {hours} to ticket {ticket}: {comment}."
            return msg
        elif (
            status == "ok" and ticket and closed in ["y", "yes", "true", "closed", True]
        ):
            return f"Ticket {ticket} closed."
        elif status == "ok" and ticket:
            return f"Action completed for ticket {ticket}."
        else:
            return str(response)
    return str(response)


def format_close_command_response(response):
    # Format the response for close intent
    if isinstance(response, dict):
        ticket = response.get("ticket")
        status = response.get("status")
        if status == "ok" and ticket:
            return f"Ticket {ticket} closed successfully."
        elif status == "ok":
            return "Ticket closed successfully."
        else:
            return str(response)
    return str(response)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_extract_command_ai()
    else:
        demo.launch()
