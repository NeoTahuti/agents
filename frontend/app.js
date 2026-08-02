const messagesEl = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const promptInput = document.querySelector("#promptInput");
const sendButton = document.querySelector("#sendButton");
const statusEl = document.querySelector("#status");
const baseUrlInput = document.querySelector("#baseUrlInput");
const modelInput = document.querySelector("#modelInput");
const temperatureInput = document.querySelector("#temperatureInput");
const newChatButton = document.querySelector("#newChatButton");
const contextLimitInput = document.querySelector("#contextLimitInput");
const systemPromptInput = document.querySelector("#systemPromptInput");

let defaultSystemPrompt = "";
const messages = [];

async function loadSystemPrompt() {
  const response = await fetch("/agent_prompt.txt");
  defaultSystemPrompt = response.ok
    ? await response.text()
    : "Voce e o Mega Brain, agente local de engenharia de software para devs.";
  systemPromptInput.value = defaultSystemPrompt.trim();
  resetConversation();
}

function resetConversation() {
  messages.splice(0, messages.length, {
    role: "system",
    content: systemPromptInput.value.trim() || defaultSystemPrompt,
  });
}

function compactMessagesForRequest() {
  const limit = Number(contextLimitInput.value || 8);
  return [messages[0], ...messages.slice(1).slice(-limit)];
}

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
      messages: compactMessagesForRequest(),
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
  const answer = data.choices?.[0]?.message?.content?.trim() || "Sem conteudo na resposta.";
  await applyAgentWrites(answer);
  return answer;
}

async function applyAgentWrites(answer) {
  const writePattern = /<mega-write\s+path="([^"]+)">([\s\S]*?)<\/mega-write>/g;
  const writes = [...answer.matchAll(writePattern)];
  for (const [, path, content] of writes) {
    const response = await fetch("/api/workspace/write", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, content }),
    });
    if (!response.ok) throw new Error(`Falha ao salvar ${path}: ${await response.text()}`);
  }
  if (writes.length) {
    statusEl.textContent = `${writes.length} arquivo(s) salvo(s)`;
  }
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
  resetConversation();
  messagesEl.replaceChildren();
  addMessage(
    "assistant",
    "Nova conversa iniciada. Estou em modo agente de codigo com historico compacto para economizar contexto."
  );
  promptInput.focus();
});

systemPromptInput.addEventListener("change", resetConversation);

loadSystemPrompt();
