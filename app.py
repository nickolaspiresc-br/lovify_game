import os
import json
import random
import string
import threading
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DATA_DIR = "data"
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
USED_FILE = os.path.join(DATA_DIR, "used.json")

rooms = {}
lock = threading.Lock()


def ensure_files():
    os.makedirs(DATA_DIR, exist_ok=True)
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


def generate_questions_with_openrouter():
    """Optional IA generation. Put OPENROUTER_API_KEY in the environment."""
    import requests

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return []

    prompt = """Gere 20 perguntas divertidas para um jogo de casal.
Cada pergunta deve permitir uma resposta curta ou média e ser adequada para adolescentes.
Responda SOMENTE com JSON válido neste formato:
{"questions":[{"text":"..."}]}
Não repita perguntas comuns demais."""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "Lovify Game"
            },
            json={
                "model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9
            },
            timeout=45
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()

        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("```", 1)[0].strip()

        data = json.loads(content)
        generated = data.get("questions", [])
        return [{"id": f"ai-{random.randint(100000,999999)}", "text": q["text"]}
                for q in generated if isinstance(q, dict) and q.get("text")]
    except Exception as e:
        print("OpenRouter error:", e)
        return []


def ensure_question_batch(room_code):
    questions = load_questions()
    used = load_used()
    used_ids = set(used.get(room_code, []))

    available = [q for q in questions if q.get("id") not in used_ids]

    if not available:
        generated = generate_questions_with_openrouter()
        if generated:
            questions.extend(generated)
            save_questions(questions)
            available = generated

    if not available:
        # Fallback: the game works without an API key.
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
        questions.extend([
            {"id": f"local-{i}-{random.randint(1000,9999)}", "text": text}
            for i, text in enumerate(fallback)
        ])
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
            "guesses": {}
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

    # Mark question as used immediately.
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

        # Each player must guess the other player's answer.
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

    # MVP scoring: exact normalized match = 2 points; otherwise 0.
    def norm(s):
        return " ".join(s.lower().strip().split())

    players = list(room["players"].keys())
    results = []

    for sid in players:
        other = players[1] if sid == players[0] else players[0]
        real = room["answers"][other]
        guessed = room["guesses"][sid]
        points = 2 if norm(real) == norm(guessed) else 0
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

    # If the selected question is already used, ensure_question_batch should
    # normally avoid it; mark it now.
    used = load_used()
    used.setdefault(room_code, []).append(question["id"])
    save_used(used)

    room["current_question"] = question
    room["status"] = "answering"

    socketio.emit("new_question", {
        "question": question["text"],
        "round": len(used.get(room_code, []))
    }, to=room_code)


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
    print("Lovify rodando em http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)