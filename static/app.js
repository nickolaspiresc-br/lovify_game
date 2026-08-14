const socket = io();

let room = null;
let isAdmin = false;

// Inicializa os corações de fundo dinamicamente
document.addEventListener("DOMContentLoaded", () => {
  createHeartsBackground();
});

function createHeartsBackground() {
  const container = document.getElementById("heartsBg");
  if (!container) return;

  const symbols = ["❤️", "💖", "💕", "💗", "💓", "🥜"];
  const heartCount = 18;

  for (let i = 0; i < heartCount; i++) {
    const heart = document.createElement("div");
    heart.classList.add("heart-fall");
    heart.innerText = symbols[Math.floor(Math.random() * symbols.length)];
    heart.style.left = `${Math.random() * 100}%`;
    heart.style.animationDuration = `${5 + Math.random() * 6}s`;
    heart.style.animationDelay = `${Math.random() * 5}s`;
    heart.style.fontSize = `${14 + Math.random() * 18}px`;
    container.appendChild(heart);
  }
}

const $ = (id) => document.getElementById(id);

function showError(message) {
  if ($("error")) {
    $("error").hidden = false;
    $("error").textContent = message;
  }
  if ($("gameMessage")) $("gameMessage").textContent = message;
}

function nameValue() {
  return $("name").value.trim();
}

function createRoom() {
  if (!nameValue()) {
    showError("Por favor, digite seu nome antes de continuar 💕");
    return;
  }
  socket.emit("create_room", { name: nameValue() });
}

function showJoin() {
  if (!nameValue()) {
    showError("Por favor, digite seu nome antes de continuar 💕");
    return;
  }
  $("joinBox").hidden = false;
  if ($("error")) $("error").hidden = true;
  $("roomCode").focus();
}

function joinRoom() {
  const code = $("roomCode").value.trim();
  if (!code) {
    showError("Digite o código da sala 🔑");
    return;
  }
  socket.emit("join_room", {
    name: nameValue(),
    room: code
  });
}

socket.on("room_created", data => {
  room = data.room;
  isAdmin = data.role === "admin";
  openRoom();
});

socket.on("joined_room", data => {
  room = data.room;
  isAdmin = false;
  openRoom();
});

function openRoom() {
  $("home").hidden = true;
  $("room").hidden = false;
  if ($("bigCode")) $("bigCode").textContent = room;
  $("startBtn").hidden = !isAdmin;
}

socket.on("room_update", data => {
  $("players").innerHTML = data.players
    .map(name => `<li>${escapeHtml(name)}</li>`)
    .join("");

  $("startBtn").hidden = !isAdmin || !data.can_start;
});

function startGame() {
  socket.emit("start_game", { room });
}

socket.on("new_question", data => {
  $("room").hidden = true;
  $("game").hidden = false;

  $("status").textContent = `Rodada ${data.round}`;
  $("question").textContent = data.question;

  $("answerPhase").hidden = false;
  $("guessPhase").hidden = true;
  $("resultPhase").hidden = true;

  $("answer").value = "";
  $("guess").value = "";
  $("gameMessage").textContent = "";
});

function submitAnswer() {
  socket.emit("submit_answer", {
    room,
    answer: $("answer").value
  });
}

socket.on("answer_received", data => {
  $("gameMessage").textContent = data.message;
  $("answerPhase").hidden = true;
});

socket.on("start_guessing", () => {
  $("guessPhase").hidden = false;
  $("resultPhase").hidden = true;
  $("gameMessage").textContent = "Ambos responderam! Agora adivinhe a resposta da sua Paçoquinha! 🧠💖";
});

function submitGuess() {
  socket.emit("submit_guess", {
    room,
    guess: $("guess").value
  });
}

socket.on("round_result", data => {
  $("guessPhase").hidden = true;
  $("resultPhase").hidden = false;
  $("results").innerHTML = "";

  data.results.forEach(r => {
    const div = document.createElement("div");
    div.className = "result";
    div.innerHTML = `
      <strong>${escapeHtml(r.name)}</strong>
      <p>Resposta real: <em>"${escapeHtml(r.real_answer_of_partner)}"</em></p>
      <p>Palpite: <em>"${escapeHtml(r.guess)}"</em></p>
      <p style="color: var(--primary); font-weight:700; margin-top:6px;">
        +${r.points} pontos (Total: ${r.total})
      </p>
    `;
    $("results").appendChild(div);
  });

  $("nextBtn").hidden = !isAdmin;
});

function nextRound() {
  socket.emit("next_round", { room });
}

socket.on("error_message", data => {
  showError(data.message);
});

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}