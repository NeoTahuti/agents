const messagesEl = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const promptInput = document.querySelector("#promptInput");
const sendButton = document.querySelector("#sendButton");
const statusEl = document.querySelector("#status");
const baseUrlInput = document.querySelector("#baseUrlInput");
const modelInput = document.querySelector("#modelInput");
const temperatureInput = document.querySelector("#temperatureInput");
const newChatButton = document.querySelector("#newChatButton");

const messages = [
  {
    role: "system",
    content: "Voce e o Mega Brain, um assistente local direto, claro e pratico.",
  },
];

function addMessage(role, content) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "EU" : "MB";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;

  article.append(avatar, bubble);
  messagesEl.append(article);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setBusy(isBusy) {
  sendButton.disabled = isBusy;
  promptInput.disabled = isBusy;
  statusEl.textContent = isBusy ? "Pensando" : "Pronto";
}

async function requestCompletion() {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: modelInput.value.trim() || "local-model",
      messages,
      temperature: Number(temperatureInput.value || 0.7),
      stream: false,
      baseUrl: baseUrlInput.value.replace(/\/+$/, ""),
    }),
  });

  const text = await response.text();

  if (!response.ok) {
    throw new Error(text || `HTTP ${response.status}`);
  }

  const data = JSON.parse(text);
  return data.choices?.[0]?.message?.content?.trim() || "Sem conteudo na resposta.";
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();

  const prompt = promptInput.value.trim();
  if (!prompt) return;

  promptInput.value = "";
  messages.push({ role: "user", content: prompt });
  addMessage("user", prompt);
  setBusy(true);

  try {
    const answer = await requestCompletion();
    messages.push({ role: "assistant", content: answer });
    addMessage("assistant", answer);
  } catch (error) {
    const message =
      "Erro ao chamar o LM Studio. Confira se o servidor local esta ligado em Developer > Local Server e teste o CLI para isolar o problema.\n\n" +
      error.message;
    addMessage("assistant", message);
  } finally {
    setBusy(false);
    promptInput.focus();
  }
});

promptInput.addEventListener("input", () => {
  promptInput.style.height = "auto";
  promptInput.style.height = `${promptInput.scrollHeight}px`;
});

newChatButton.addEventListener("click", () => {
  messages.splice(1);
  messagesEl.replaceChildren();
  addMessage(
    "assistant",
    "Nova conversa iniciada. O contexto anterior foi limpo nesta interface."
  );
  promptInput.focus();
});
