# -*- coding: utf-8 -*-
"""
server/app.py — локальный веб-сервер (Flask). Точка входа: запускается
run_server.bat (или `python server/app.py` из корня carcheck/).

Слушает 0.0.0.0:8000 по умолчанию (порт/хост настраиваются в server/config.py
через переменные окружения CARCHECK_HOST/CARCHECK_PORT) — это то, что нужно
для доступа через Tailscale (Часть 4 ТЗ).

Авторизация: простой токен в URL (?token=...) либо заголовок
Authorization: Bearer <token>. Токен генерируется один раз и лежит в
server/secret_token.txt — .bat-файл выводит его в консоль при старте.
После первого успешного захода с ?token=... сервер запоминает это в
подписанной cookie на 30 дней, так что токен не нужно таскать в каждой ссылке.
"""

import os
import sys
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # чтобы видеть shared/

from flask import Flask, jsonify, render_template, request, session, redirect, url_for

from server import config
from server import live_api
from server import history_api
from shared.formatting import normalize_plate
from shared.refdata import TEST_PLATES

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY
app.config["SESSION_COOKIE_NAME"] = "carcheck_session"
app.permanent_session_lifetime = 60 * 60 * 24 * 30  # 30 дней


def require_token(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if config.AUTH_DISABLED:
            return view(*args, **kwargs)

        token = request.args.get("token")
        auth_header = request.headers.get("Authorization", "")
        header_token = auth_header[7:] if auth_header.startswith("Bearer ") else None

        if token and token == config.ACCESS_TOKEN:
            session.permanent = True
            session["authed"] = True
            return view(*args, **kwargs)
        if header_token and header_token == config.ACCESS_TOKEN:
            return view(*args, **kwargs)
        if session.get("authed"):
            return view(*args, **kwargs)

        if request.path.startswith("/api/"):
            return jsonify({"error": "לא מורשה. הוסיפו ?token=<טוקן> לכתובת השרת."}), 401
        return (
            "<html dir='rtl' lang='he'><body style='background:#0f1720;color:#e8eef4;font-family:sans-serif;"
            "padding:40px;text-align:center;'>"
            "<h2>נדרש טוקן גישה</h2>"
            "<p>פתחו את כתובת השרת עם הפרמטר <code>?token=הטוקן_שלכם</code>.<br>"
            "הטוקן מודפס לקונסולה בעת הפעלת run_server.bat ונמצא בקובץ "
            "<code>server/secret_token.txt</code>.</p></body></html>", 401
        )
    return wrapped


@app.route("/")
@require_token
def index():
    return render_template("index.html", test_plates=TEST_PLATES)


@app.route("/api/car/<plate>")
@require_token
def api_car(plate):
    plate_norm = normalize_plate(plate)
    if not plate_norm:
        return jsonify({"error": "מספר לא תקין"}), 400

    report = live_api.build_report(plate_norm)
    local = history_api.get_local_data(plate_norm)
    report["local_history"] = local
    return jsonify(report)


@app.route("/api/status")
@require_token
def api_status():
    return jsonify(history_api.get_meta_stats())


@app.route("/healthz")
def healthz():
    # без авторизации — чтобы можно было быстро проверить, что процесс жив
    return jsonify({"status": "ok"})


def print_access_info():
    import socket
    print("=" * 60)
    print("carcheck сервер запущен")
    print(f"Токен доступа: {config.ACCESS_TOKEN}")
    print(f"Локально:      http://127.0.0.1:{config.PORT}/?token={config.ACCESS_TOKEN}")
    try:
        hostname = socket.gethostname()
        print(f"В локальной сети (по имени компьютера): http://{hostname}:{config.PORT}/?token={config.ACCESS_TOKEN}")
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"В локальной сети (по IP):  http://{local_ip}:{config.PORT}/?token={config.ACCESS_TOKEN}")
    except Exception:
        pass
    print("После установки Tailscale тот же порт будет доступен по Tailscale-адресу компьютера.")
    print("=" * 60)


if __name__ == "__main__":
    print_access_info()
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)
