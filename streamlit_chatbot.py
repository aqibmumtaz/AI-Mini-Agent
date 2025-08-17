# --- IMPORTS ---
import streamlit as st
import requests
import openai
import json
import re
import time
from datetime import datetime, timedelta
from configs import Configs
from gradio_chatbot import (
    get_iso_date,
    get_human_date,
    extract_command_ai,
    get_open_tickets,
    normalize_hours,
    call_mcp_server,
    format_log_command_response,
    format_close_command_response,
)


# --- HOURS LABEL HELPER ---
def refresh_hours_label(selected_date):
    try:
        resp = requests.get(
            f"http://localhost:5000/hours",
            params={"date": get_iso_date(selected_date)},
        )
        hours = resp.json().get("hours", 0.0)
        if hasattr(selected_date, "date"):
            date_obj = selected_date.date()
        else:
            date_obj = selected_date
        human_date = get_human_date(date_obj)
        return f"{human_date} — Hours: {hours} h"
    except Exception:
        return "Hours: N/A"


# --- SESSION STATE INITIALIZATION ---
if "today" not in st.session_state:
    st.session_state["today"] = datetime.now()
if "date_state" not in st.session_state:
    st.session_state["date_state"] = st.session_state["today"]
if "history" not in st.session_state:
    st.session_state["history"] = []
if "selected_ticket_tuple" not in st.session_state:
    st.session_state["selected_ticket_tuple"] = (None, "")
if "display_list" not in st.session_state:
    st.session_state["display_list"] = []
if "confirm_undo" not in st.session_state:
    st.session_state["confirm_undo"] = False
if "confirm_undo_all" not in st.session_state:
    st.session_state["confirm_undo_all"] = False

# --- LOAD OPEN TICKETS (Gradio parity) ---
try:
    _, display_list, ticket_count = get_open_tickets()
except Exception as e:
    display_list = []
    ticket_count = 0


def refresh_ticket_list():
    try:
        _, display_list, ticket_count = get_open_tickets()
    except Exception as e:
        display_list = []
        ticket_count = 0
    st.session_state["display_list"] = display_list
    st.session_state["ticket_count"] = ticket_count


if "ticket_count" not in st.session_state:
    st.session_state["ticket_count"] = 0
refresh_ticket_list()


# --- Two-column layout for Gradio parity ---
st.set_page_config(page_title="AI Mini Agent Chatbot", layout="wide")
st.title("AI Mini Agent Chatbot (Sample Title)")

left_col, right_col = st.columns([1, 3], gap="large")

# --- Left column: Open tickets and info ---
with left_col:
    st.markdown(
        f"#### Open Tickets ({ticket_count}) (🏢 Project > 🏷️ Epic > 🗂️ Main Task > 🔖 Ticket)"
    )
    ticket_labels = [label for label, key, _ in display_list]
    selected_ticket_label = (
        st.radio(
            label="Select a ticket:",
            options=ticket_labels,
            index=0 if ticket_labels else None,
            key="ticket_radio",
        )
        if ticket_labels
        else None
    )
    selected_ticket_tuple = (None, "")
    if selected_ticket_label:
        for label, key, full_label in display_list:
            if label == selected_ticket_label:
                selected_ticket_tuple = (key, full_label)
                break
    st.session_state["selected_ticket_tuple"] = selected_ticket_tuple
    if selected_ticket_tuple[1]:
        st.markdown(
            f"**Selected Ticket:**\n{selected_ticket_tuple[1]}", unsafe_allow_html=True
        )

with left_col:
    st.markdown(
        f"#### Open Tickets ({st.session_state['ticket_count']}) (🏢 Project > 🏷️ Epic > 🗂️ Main Task > 🔖 Ticket)"
    )
    ticket_labels = [label for label, key, _ in st.session_state["display_list"]]
    selected_ticket_label = (
        st.radio(
            label="Select a ticket:",
            options=ticket_labels,
            index=0 if ticket_labels else None,
            key="ticket_radio",
        )
        if ticket_labels
        else None
    )
    selected_ticket_tuple = (None, "")
    if selected_ticket_label:
        for label, key, full_label in st.session_state["display_list"]:
            if label == selected_ticket_label:
                selected_ticket_tuple = (key, full_label)
                break
    st.session_state["selected_ticket_tuple"] = selected_ticket_tuple
    if selected_ticket_tuple[1]:
        st.markdown(
            f"**Selected Ticket:**\n{selected_ticket_tuple[1]}", unsafe_allow_html=True
        )

# --- Right column: All controls, chat, forms ---
with right_col:
    with st.container():
        st.markdown("#### Worklog Date")
        date_col, prev_col, next_col = st.columns([2, 1, 1])
        with date_col:
            date_input = st.date_input(
                "Select Date",
                value=(
                    st.session_state["date_state"].date()
                    if hasattr(st.session_state["date_state"], "date")
                    else st.session_state["date_state"]
                ),
                key="date_picker",
            )
            st.session_state["date_state"] = datetime.combine(
                date_input, datetime.min.time()
            )
        with prev_col:
            if st.button("←", key="prev_btn"):
                st.session_state["date_state"] -= timedelta(days=1)
        with next_col:
            if st.button("→", key="next_btn"):
                st.session_state["date_state"] += timedelta(days=1)
        st.info(refresh_hours_label(st.session_state["date_state"]))

    with st.container():
        st.markdown("#### Chatbot")
        for user, bot in st.session_state["history"]:
            st.chat_message("user").write(user)
            st.chat_message("assistant").write(bot)

    with st.container():
        st.markdown("#### Log Hours")
        with st.form(key="log_hours_form", clear_on_submit=True):
            hours = st.text_input("Hours (e.g. 1h 30m)")
            comment = st.text_input("Comment")
            log_submitted = st.form_submit_button("Log Hours")
            if log_submitted:
                ticket_key = st.session_state["selected_ticket_tuple"][0]
                hours_input = normalize_hours(hours)
                if hours_input and re.fullmatch(r"\d+(\.\d+)?", hours_input):
                    hours_input = f"{hours_input}h"
                if not ticket_key or not hours_input or not comment:
                    st.warning("Please select a ticket, enter hours, and a comment.")
                else:
                    try:
                        resp = requests.post(
                            f"http://localhost:5000/log",
                            json={
                                "ticket": ticket_key,
                                "hours": hours_input,
                                "comment": comment,
                                "close": "N",
                            },
                        )
                        response = resp.json()
                        st.session_state["history"].append(
                            (
                                f"Log {hours_input} for {ticket_key}: {comment}",
                                str(response),
                            )
                        )
                        st.success("Hours logged!")
                        refresh_ticket_list()
                    except Exception as e:
                        st.session_state["history"].append(
                            (
                                f"Log {hours_input} for {ticket_key}: {comment}",
                                f"Error: {str(e)}",
                            )
                        )
                        st.error(f"Error: {str(e)}")

    with st.container():
        undo_col, undo_all_col, logs_col = st.columns([1, 1, 2])
        with undo_col:
            if st.button("Undo Last Hour"):
                try:
                    resp = requests.post("http://localhost:5000/undo_last_log")
                    result = resp.json()
                    msg = (
                        result.get("message", "Last hour deleted.")
                        if result.get("success")
                        else f"Undo failed: {result.get('message', 'Unknown error')}"
                    )
                    st.session_state["history"].append(("Undo last hour", msg))
                    st.success(msg)
                    refresh_ticket_list()
                except Exception as e:
                    st.session_state["history"].append(
                        ("Undo last hour", f"Error: {str(e)}")
                    )
                    st.error(f"Error: {str(e)}")
        with undo_all_col:
            if st.button("Undo All Hours"):
                try:
                    resp = requests.post("http://localhost:5000/undo_all_logs_today")
                    result = resp.json()
                    msg = (
                        result.get("message", "All today's hours deleted.")
                        if result.get("success")
                        else f"Undo all failed: {result.get('message', 'Unknown error')}"
                    )
                    st.session_state["history"].append(
                        ("Undo all hours for today", msg)
                    )
                    st.success(msg)
                    refresh_ticket_list()
                except Exception as e:
                    st.session_state["history"].append(
                        ("Undo all hours for today", f"Error: {str(e)}")
                    )
                    st.error(f"Error: {str(e)}")
        with logs_col:
            if st.button("List Logs"):
                try:
                    resp = requests.get(
                        f"http://localhost:5000/worklogs",
                        params={"date": get_iso_date(st.session_state["date_state"])},
                    )
                    logs = resp.json().get("worklogs", [])
                    if not logs:
                        logs_text = "No logs for this date."
                    else:
                        lines = []
                        for log in logs:
                            started_raw = log.get("started", "")
                            try:
                                dt = datetime.strptime(
                                    started_raw[:19], "%Y-%m-%dT%H:%M:%S"
                                )
                                started_fmt = dt.strftime("%Y-%m-%d %H:%M")
                            except Exception:
                                started_fmt = started_raw
                            lines.append(
                                f"**{log['issue_key']} ({log['time_spent']})** *{log['summary']}*\n"
                                f"{log['comment']}  {started_fmt}"
                            )
                        logs_text = "\n\n".join(lines)
                    st.session_state["history"].append(
                        (
                            f"List logs for {get_iso_date(st.session_state['date_state'])}",
                            logs_text,
                        )
                    )
                    st.info(logs_text)
                except Exception as e:
                    st.session_state["history"].append(
                        (
                            f"List logs for {get_iso_date(st.session_state['date_state'])}",
                            f"Error: {str(e)}",
                        )
                    )
                    st.error(f"Error: {str(e)}")

    with st.container():
        ticket_key = st.session_state["selected_ticket_tuple"][0]
        user_input = st.text_input(
            "Type your command and press Enter", key="user_input"
        )
        if st.button("Submit Command"):
            merged_input = user_input
            ticket_key = st.session_state["selected_ticket_tuple"][0]
            user_input_lower = user_input.strip().lower()
            if (
                ticket_key
                and (
                    user_input_lower.startswith("log")
                    or user_input_lower.startswith("close")
                )
                and ticket_key not in user_input
            ):
                merged_input = f"{ticket_key}\n{user_input}".strip()
            history, state, *_ = call_mcp_server(
                merged_input, st.session_state["history"]
            )
            st.session_state["history"] = history
        refresh_ticket_list()
        st.experimental_rerun()
