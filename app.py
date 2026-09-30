"""웹 서버 - 실행: python app.py → 브라우저에서 http://localhost:5000"""
import json
import os
import re
import threading
import time
from datetime import datetime

from flask import Flask, request, jsonify, render_template, send_file

import config
import pipeline
import report

app = Flask(__name__)

# 현재 작업 상태 (웹페이지가 주기적으로 읽어 감)
state = {"running": False, "logs": [], "done": 0, "total": 1, "error": None}
lock = threading.Lock()


def log(msg):
    state["logs"].append(f"[{datetime.now():%H:%M:%S}] {msg}")


def progress(done, total):
    state["done"], state["total"] = done, total


def run_job(manual=None):
    """백그라운드에서 분석 실행. 이미 돌고 있으면 무시."""
    with lock:
        if state["running"]:
            return False
        state.update(running=True, logs=[], done=0, total=1, error=None)

    def work():
        try:
            pipeline.run_pipeline(log, progress, manual)
        except Exception as e:
            state["error"] = str(e)
            log(f"오류: {e}")
        finally:
            state["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return True


def scheduler():
    """정해진 시각(config.AUTO_RUN_TIMES)이 되면 자동 실행. 서버가 켜져 있어야 동작."""
    last = None
    while True:
        now = datetime.now().strftime("%H:%M")
        if now in config.AUTO_RUN_TIMES and now != last:
            run_job()
        last = now
        time.sleep(20)


@app.route("/")
def index():
    return render_template("index.html", auto_times=config.AUTO_RUN_TIMES)


@app.post("/api/run")
def api_run():
    body = request.get_json(silent=True) or {}
    manual = [x for x in re.split(r"[,\n]+", body.get("manual", "")) if x.strip()]
    return jsonify(started=run_job(manual))


@app.get("/api/status")
def api_status():
    return jsonify(state)


@app.get("/api/result")
def api_result():
    if not os.path.exists(pipeline.RESULT_FILE):
        return jsonify(None)
    with open(pipeline.RESULT_FILE, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.get("/api/report.md")
def api_report():
    path = report.report_path()
    if not os.path.exists(path):
        return "오늘 보고서가 아직 없습니다.", 404
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


if __name__ == "__main__":
    threading.Thread(target=scheduler, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
