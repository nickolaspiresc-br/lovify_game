const socket = io();

let room = null;
let isAdmin = false;
let pendingFile = null;

// ============================================================================
// INITIALIZATION & BACKGROUND EFFECTS
// ============================================================================
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

// Helper para selecionar elementos por ID
const $ = (id) => document.getElementById(id);

// Exibe mensagens de erro na tela
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

// ============================================================================
// ROOM & CONNECTION MANAGEMENT
// ============================================================================
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

/**
 * Abre a sala principal e exibe o Código da Sala GLOBALMENTE.
 * O código fica no topo da dashboard principal (fora de qualquer sub-jogo).
 */
function openRoom() {
  $("home").hidden = true;
  $("mainDashboard").hidden = false;
  
  // Exibe o código da sala na interface principal
  if ($("bigCode")) $("bigCode").textContent = room;
  $("startBtn").hidden = !isAdmin;
  
  // Garante que o usuário veja o menu de jogos inicialmente
  showGamesMenu();
}

socket.on("room_update", data => {
  $("players").innerHTML = data.players
    .map(name => `<li>${escapeHtml(name)}</li>`)
    .join("");

  $("startBtn").hidden = !isAdmin || !data.can_start;
});

// ============================================================================
// NAVEGAÇÃO ENTRE TABS PRINCIPAIS (JOGOS / CHAT)
// ============================================================================
function switchTab(tab) {
  if (tab === 'games') {
    $("gamesTabSection").hidden = false;
    $("chatTabSection").hidden = true;
    $("tabGamesBtn").classList.add("active");
    $("tabChatBtn").classList.remove("active");
  } else if (tab === 'chat') {
    $("gamesTabSection").hidden = true;
    $("chatTabSection").hidden = false;
    $("tabChatBtn").classList.add("active");
    $("tabGamesBtn").classList.remove("active");
    $("chatBadge").hidden = true;
    scrollToBottomChat();
  }
}

// ============================================================================
// MENU DE JOGOS & LÓGICA DO JOGO DE PERGUNTA E PALPITE
// ============================================================================

/**
 * Exibe o Menu Principal de Jogos.
 * Permite selecionar qual jogo rodar mantendo a sala visível.
 */
function showGamesMenu() {
  if ($("gamesMenu")) $("gamesMenu").hidden = false;
  if ($("game")) $("game").hidden = true;
}

/**
 * Inicia o jogo selecionado (Pergunta e Palpite) enviado pelo servidor.
 */
function startGame() {
  socket.emit("start_game", { room });
}

socket.on("new_question", data => {
  // Oculta a área de espera da sala e exibe a tela do jogo
  if ($("room")) $("room").hidden = true;
  if ($("game")) $("game").hidden = false;

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

// ============================================================================
// CHAT & ENVIO DE ARQUIVOS
// ============================================================================

/**
 * Lida com a escolha do arquivo via <input type="file">
 */
async function handleFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/api/upload", {
      method: "POST",
      body: formData
    });
    const data = await response.json();
    if (data.url) {
      pendingFile = data;
      $("filePreviewName").textContent = `📎 ${data.filename}`;
      $("filePreviewContainer").hidden = false;
    }
  } catch (err) {
    showError("Erro ao carregar o arquivo.");
  }
}

/**
 * Reseta completamente o estado do arquivo anexado e limpa o valor no DOM.
 */
function cancelFileUpload() {
  pendingFile = null;
  if ($("filePreviewContainer")) $("filePreviewContainer").hidden = true;
  if ($("chatFileInput")) $("chatFileInput").value = ""; // Garante a limpeza do elemento HTML
}

/**
 * Envia a mensagem do chat e limpa o campo de texto E o arquivo anexado.
 */
function sendChatMessage() {
  const input = $("chatInput");
  const text = input.value.trim();

  if (!text && !pendingFile) return;

  socket.emit("send_chat_message", {
    room,
    text: text,
    file: pendingFile
  });

  // Limpa o texto da digitação
  input.value = "";

  // Reset total do anexo para que o arquivo não permaneça no input
  cancelFileUpload();
}

socket.on("chat_message_received", msg => {
  const container = $("chatMessages");
  const placeholder = container.querySelector(".chat-placeholder");
  if (placeholder) placeholder.remove();

  const isMe = msg.sender_sid === socket.id;
  const msgDiv = document.createElement("div");
  msgDiv.className = `chat-bubble ${isMe ? 'me' : 'partner'}`;
  msgDiv.id = msg.id;

  let fileContent = "";
  if (msg.file) {
    const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(msg.file.url);
    if (isImage) {
      fileContent = `<div class="chat-media"><img src="${msg.file.url}" alt="Imagem enviada" /></div>`;
    } else {
      fileContent = `<div class="chat-file-link"><a href="${msg.file.url}" target="_blank" download>💾 ${escapeHtml(msg.file.filename)}</a></div>`;
    }
  }

  let editBtnHtml = isMe ? `<button class="btn-edit-msg" onclick="promptEditMessage('${msg.id}')">✏️</button>` : "";

  msgDiv.innerHTML = `
    <div class="chat-sender">${escapeHtml(msg.sender_name)} ${editBtnHtml}</div>
    ${fileContent}
    <div class="chat-text">${escapeHtml(msg.text)}</div>
    <span class="edited-tag" ${msg.edited ? '' : 'hidden'}> (editado)</span>
  `;

  container.appendChild(msgDiv);
  scrollToBottomChat();

  if ($("chatTabSection").hidden) {
    $("chatBadge").hidden = false;
  }
});

function promptEditMessage(msgId) {
  const msgEl = $(msgId);
  if (!msgEl) return;
  const currentText = msgEl.querySelector(".chat-text").innerText;
  const newText = prompt("Edite sua mensagem:", currentText);

  if (newText !== null && newText.trim() !== "") {
    socket.emit("edit_chat_message", {
      room,
      msg_id: msgId,
      text: newText.trim()
    });
  }
}

socket.on("chat_message_edited", data => {
  const msgEl = $(data.id);
  if (msgEl) {
    msgEl.querySelector(".chat-text").innerText = data.text;
    const tag = msgEl.querySelector(".edited-tag");
    if (tag) tag.hidden = false;
  }
});

function scrollToBottomChat() {
  const container = $("chatMessages");
  if (container) container.scrollTop = container.scrollHeight;
}

// ============================================================================
// UTILITÁRIOS
// ============================================================================
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}