import os
import json
import random
import string
import threading
import unicodedata
import re
import uuid
from difflib import SequenceMatcher
from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
UPLOAD_FOLDER = os.path.join("data", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DATA_DIR = "data"
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
USED_FILE = os.path.join(DATA_DIR, "used.json")

SIMILARITY_THRESHOLD = 0.50

rooms = {}
lock = threading.Lock()


def ensure_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    if not os.path.exists(QUESTIONS_FILE):
        with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({"questions": []}, f, ensure_ascii=False, indent=2)
    if not os.path.exists(USED_FILE):
        with open(USED_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)


def load_questions():
    ensure_files()
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("questions", [])


def save_questions(questions):
    with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump({"questions": questions}, f, ensure_ascii=False, indent=2)


def load_used():
    ensure_files()
    with open(USED_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_used(used):
    with open(USED_FILE, "w", encoding="utf-8") as f:
        json.dump(used, f, ensure_ascii=False, indent=2)


def code4():
    while True:
        code = "".join(random.choices(string.digits, k=4))
        if code not in rooms:
            return code


def normalize_text(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", "", text)
    return " ".join(text.split())


def check_approximate_match(real, guess, threshold=SIMILARITY_THRESHOLD):
    norm_real = normalize_text(real)
    norm_guess = normalize_text(guess)

    if not norm_real or not norm_guess:
        return False

    if norm_real == norm_guess:
        return True

    if norm_guess in norm_real or norm_real in norm_guess:
        return True

    similarity = SequenceMatcher(None, norm_real, norm_guess).ratio()
    return similarity >= threshold


def ensure_question_batch(room_code):
    questions = load_questions()
    used = load_used()
    used_ids = set(used.get(room_code, []))

    available = [q for q in questions if q.get("id") not in used_ids]

    if not available and questions:
        used[room_code] = []
        save_used(used)
        available = questions

    if not available:
        fallback = [
            "Qual é uma coisa simples que sempre melhora seu dia?",
            "Qual viagem você gostaria de fazer comigo?",
            "Qual comida você escolheria para comer pelo resto da semana?",
            "Qual é uma memória nossa que você gosta muito?",
            "Qual filme ou série você acha que combina comigo?",
            "Se pudesse aprender qualquer habilidade agora, qual seria?",
            "Qual lugar você gostaria de conhecer?",
            "Qual presente simples você gostaria de receber?",
            "Qual música lembra um momento especial?",
            "Qual seria um dia perfeito para você?"
        ]
        questions = [
            {"id": f"local-{i}-{random.randint(1000,9999)}", "text": text}
            for i, text in enumerate(fallback)
        ]
        save_questions(questions)
        available = questions

    return random.choice(available)


def reset_room_used(room_code):
    used = load_used()
    used.pop(room_code, None)
    save_used(used)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/upload", methods=["POST"])
def upload_file_route():
    if "file" not in request.files:
        return {"error": "Nenhum arquivo enviado"}, 400
    file = request.files["file"]
    if file.filename == "":
        return {"error": "Arquivo sem nome"}, 400

    ext = os.path.splitext(file.filename)[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
    file.save(save_path)

    file_url = f"/uploads/{unique_name}"
    return {"url": file_url, "filename": file.filename}


@socketio.on("create_room")
def create_room(data):
    name = (data.get("name") or "").strip()
    if not name:
        emit("error_message", {"message": "Digite seu nome."})
        return

    with lock:
        room_code = code4()
        rooms[room_code] = {
            "admin_sid": request.sid,
            "players": {
                request.sid: {"name": name, "role": "admin", "score": 0}
            },
            "status": "waiting",
            "current_question": None,
            "answers": {},
            "guesses": {},
            "chat_messages": []
        }

    join_room(room_code)
    emit("room_created", {
        "room": room_code,
        "name": name,
        "role": "admin"
    })


@socketio.on("join_room")
def join_room_event(data):
    name = (data.get("name") or "").strip()
    room_code = str(data.get("room") or "").strip()

    if not name or len(room_code) != 4 or room_code not in rooms:
        emit("error_message", {"message": "Sala não encontrada ou nome inválido."})
        return

    room = rooms[room_code]

    if len(room["players"]) >= 2:
        emit("error_message", {"message": "Essa sala já está cheia."})
        return

    if request.sid in room["players"]:
        return

    room["players"][request.sid] = {"name": name, "role": "player", "score": 0}
    join_room(room_code)

    emit("joined_room", {"room": room_code, "name": name, "role": "player"})
    socketio.emit("room_update", {
        "players": [p["name"] for p in room["players"].values()],
        "can_start": len(room["players"]) == 2
    }, to=room_code)


@socketio.on("start_game")
def start_game(data):
    room_code = str(data.get("room") or "")
    room = rooms.get(room_code)

    if not room or room["admin_sid"] != request.sid:
        emit("error_message", {"message": "Somente o administrador pode iniciar."})
        return

    if len(room["players"]) != 2:
        emit("error_message", {"message": "É necessário ter dois jogadores."})
        return

    room["status"] = "answering"
    room["answers"] = {}
    room["guesses"] = {}
    room["current_question"] = ensure_question_batch(room_code)

    used = load_used()
    used.setdefault(room_code, []).append(room["current_question"]["id"])
    save_used(used)

    socketio.emit("new_question", {
        "question": room["current_question"]["text"],
        "round": len(used.get(room_code, []))
    }, to=room_code)


@socketio.on("submit_answer")
def submit_answer(data):
    room_code = str(data.get("room") or "")
    answer = (data.get("answer") or "").strip()
    room = rooms.get(room_code)

    if not room or room["status"] != "answering":
        emit("error_message", {"message": "Não há uma rodada ativa."})
        return

    if not answer:
        emit("error_message", {"message": "Digite uma resposta."})
        return

    if request.sid not in room["players"]:
        return

    room["answers"][request.sid] = answer

    emit("answer_received", {"message": "Resposta enviada. Esperando o outro jogador..."})

    if len(room["answers"]) == 2:
        room["status"] = "guessing"

        players = list(room["players"].keys())
        target_names = {
            players[0]: room["players"][players[1]]["name"],
            players[1]: room["players"][players[0]]["name"]
        }

        socketio.emit("start_guessing", {
            "target": target_names
        }, to=room_code)


@socketio.on("submit_guess")
def submit_guess(data):
    room_code = str(data.get("room") or "")
    guess = (data.get("guess") or "").strip()
    room = rooms.get(room_code)

    if not room or room["status"] != "guessing":
        emit("error_message", {"message": "A fase de adivinhação não está ativa."})
        return

    if not guess:
        emit("error_message", {"message": "Digite um palpite."})
        return

    room["guesses"][request.sid] = guess

    if len(room["guesses"]) < 2:
        emit("answer_received", {"message": "Palpite enviado. Esperando o outro jogador..."})
        return

    players = list(room["players"].keys())
    results = []

    for sid in players:
        other = players[1] if sid == players[0] else players[0]
        real = room["answers"][other]
        guessed = room["guesses"][sid]
        
        is_match = check_approximate_match(real, guessed)
        points = 2 if is_match else 0
        room["players"][sid]["score"] += points

        results.append({
            "name": room["players"][sid]["name"],
            "guess": guessed,
            "real_answer_of_partner": real,
            "points": points,
            "total": room["players"][sid]["score"]
        })

    room["status"] = "result"

    socketio.emit("round_result", {
        "question": room["current_question"]["text"],
        "results": results
    }, to=room_code)


@socketio.on("next_round")
def next_round(data):
    room_code = str(data.get("room") or "")
    room = rooms.get(room_code)

    if not room or room["admin_sid"] != request.sid:
        emit("error_message", {"message": "Somente o administrador pode avançar."})
        return

    room["answers"] = {}
    room["guesses"] = {}

    question = ensure_question_batch(room_code)

    used = load_used()
    used.setdefault(room_code, []).append(question["id"])
    save_used(used)

    room["current_question"] = question
    room["status"] = "answering"

    socketio.emit("new_question", {
        "question": question["text"],
        "round": len(used.get(room_code, []))
    }, to=room_code)


# HANDLERS DO CHAT
@socketio.on("send_chat_message")
def send_chat_message(data):
    room_code = str(data.get("room") or "")
    text = (data.get("text") or "").strip()
    file_info = data.get("file")
    room = rooms.get(room_code)

    if not room or request.sid not in room["players"]:
        return

    if not text and not file_info:
        return

    msg_id = f"msg-{uuid.uuid4().hex[:8]}"
    sender_name = room["players"][request.sid]["name"]

    msg_obj = {
        "id": msg_id,
        "sender_sid": request.sid,
        "sender_name": sender_name,
        "text": text,
        "file": file_info,
        "edited": False
    }

    room["chat_messages"].append(msg_obj)
    socketio.emit("chat_message_received", msg_obj, to=room_code)


@socketio.on("edit_chat_message")
def edit_chat_message(data):
    room_code = str(data.get("room") or "")
    msg_id = data.get("msg_id")
    new_text = (data.get("text") or "").strip()
    room = rooms.get(room_code)

    if not room or not msg_id or not new_text:
        return

    for msg in room["chat_messages"]:
        if msg["id"] == msg_id and msg["sender_sid"] == request.sid:
            msg["text"] = new_text
            msg["edited"] = True
            socketio.emit("chat_message_edited", {
                "id": msg_id,
                "text": new_text
            }, to=room_code)
            break


@socketio.on("disconnect")
def disconnect():
    for room_code, room in list(rooms.items()):
        if request.sid not in room["players"]:
            continue

        was_admin = room["admin_sid"] == request.sid
        del room["players"][request.sid]

        if was_admin or not room["players"]:
            reset_room_used(room_code)
            del rooms[room_code]
        else:
            room["status"] = "waiting"
            socketio.emit("room_update", {
                "players": [p["name"] for p in room["players"].values()],
                "can_start": False
            }, to=room_code)
        break


if __name__ == "__main__":
    ensure_files()
    print("Rodando em http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)