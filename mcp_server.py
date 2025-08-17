from flask import Flask, request, jsonify

import sys
import os

sys.path.append(os.path.dirname(__file__))
from commit import (
    set_start_time_manual,
    log_work,
    close_ticket,
    get_open_tickets,
    extract_commit_info,
    extract_commit_comment,
    set_start_time,
    get_hours_logged,
    delete_last_worklog,
    delete_all_worklogs,
    get_all_worklogs,
)


 # --- IMPORTS & SETUP ---
# Import Tempo API helpers from commit.py (must be before endpoints)
try:
    from commit import get_tempo_hours_logged, get_tempo_all_worklogs
except ImportError:
    get_tempo_hours_logged = None
    get_tempo_all_worklogs = None


# --- FLASK APP INIT ---
app = Flask(__name__)


# --- TEMPO API ENDPOINTS ---
@app.route("/tempo_hours", methods=["GET"])
def api_tempo_hours():
    if not get_tempo_hours_logged:
        return jsonify({"error": "Tempo API not available"}), 500
    date_str = request.args.get("date")
    user_key = request.args.get("user")
    try:
        hours = get_tempo_hours_logged(date_str, user_key)
        return jsonify({"hours": hours, "date": date_str, "user": user_key})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tempo_worklogs", methods=["GET"])
def api_tempo_worklogs():
    if not get_tempo_all_worklogs:
        return jsonify({"error": "Tempo API not available"}), 500
    date_str = request.args.get("date")
    user_key = request.args.get("user")
    try:
        logs = get_tempo_all_worklogs(date_str, user_key)
        return jsonify({"worklogs": logs, "date": date_str, "user": user_key})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


 # --- JIRA API ENDPOINTS ---
@app.route("/start", methods=["POST"])
def api_start():
    hhmm = request.json.get("time")
    set_start_time_manual(hhmm)
    return jsonify({"status": "ok", "start_time": hhmm})


@app.route("/log", methods=["POST"])
def api_log():
    data = request.json
    ticket_key = data.get("ticket")
    hours = data.get("hours")
    comment = data.get("comment", "")
    close_flag = data.get("close", "N")
    date_str = data.get("date")
    log_work(ticket_key, hours, comment, date_str)
    if close_flag.lower() in ["c", "y"]:
        close_ticket(ticket_key)
    set_start_time()
    return jsonify(
        {
            "status": "ok",
            "ticket": ticket_key,
            "hours": hours,
            "comment": comment,
            "close": close_flag,
            "date": date_str,
        }
    )


@app.route("/close", methods=["POST"])
def api_close():
    data = request.json
    ticket_key = data.get("ticket")
    date_str = data.get("date")
    close_ticket(ticket_key, date_str)
    return jsonify({"status": "ok", "ticket": ticket_key, "date": date_str})


@app.route("/tickets", methods=["GET"])
def api_tickets():
    hierarchy = get_open_tickets()
    return jsonify({"tickets": hierarchy})


@app.route("/commit", methods=["POST"])
def api_commit():
    data = request.json
    commit_msg = data.get("commit_msg", "")
    date_str = data.get("date")
    ticket_key, hours, close_flag, start_time = extract_commit_info(commit_msg)
    comment = "On commit: " + extract_commit_comment(commit_msg)
    if ticket_key and hours:
        log_work(ticket_key, hours, comment, date_str)
        if close_flag.lower() in ["c", "y"]:
            close_ticket(ticket_key, date_str)
        set_start_time()
        return jsonify(
            {"status": "ok", "ticket": ticket_key, "hours": hours, "date": date_str}
        )
    else:
        return (
            jsonify({"status": "error", "message": "Could not extract ticket/hours"}),
            400,
        )


@app.route("/hours", methods=["GET"])
def api_hours():
    date_str = request.args.get("date")
    hours = get_hours_logged(date_str)
    return jsonify({"hours": hours, "date": date_str})


@app.route("/undo_last_log", methods=["POST"])
def api_undo_last_log():
    data = request.json
    date_str = data.get("date") if data else None
    result = delete_last_worklog(date_str)
    return jsonify(result)


@app.route("/undo_all_logs", methods=["POST"])
def api_undo_all_logs():
    data = request.json
    date_str = data.get("date") if data else None
    result = delete_all_worklogs(date_str)
    return jsonify(result)


@app.route("/worklogs", methods=["GET"])
def api_worklogs():
    date_str = request.args.get("date")
    logs = get_all_worklogs(date_str)
    return jsonify({"worklogs": logs, "date": date_str})



# --- SERVER RUN LOGIC ---
def run_server():
    app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    run_server()
