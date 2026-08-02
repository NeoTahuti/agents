const $ = (selector) => document.querySelector(selector);
const messagesEl = $("#messages");
const composer = $("#composer");
const promptInput = $("#promptInput");
const sendButton = $("#sendButton");
const statusEl = $("#connectionLabel");
const toastEl = $("#toast");

const STORAGE_KEY = "mega-brain-state-v2";
const defaultState = {
  projects: [{ id: "workspace", name: "Workspace local", threads: [{ id: "welcome", title: "Agente de código", messages: [] }] }],
  activeProjectId: "workspace",
  activeThreadId: "welcome",
  settings: { endpoint: "http://localhost:1234/v1", model: "auto", taskMode: "code", contextLimit: 8 },
};
let state = loadState();
let config = { models: [], skills: [], contextWindow: 8192 };
let defaultSystemPrompt = "";
let pendingFiles = [];

function loadState() {
  try { return { ...defaultState, ...JSON.parse(localStorage.getItem(STORAGE_KEY)) }; } catch { return structuredClone(defaultState); }
}
function saveState() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
function activeProject() { return state.projects.find((project) => project.id === state.activeProjectId) || state.projects[0]; }
function activeThread() { return activeProject().threads.find((thread) => thread.id === state.activeThreadId) || activeProject().threads[0]; }
function escapeText(value) { return String(value).replace(/[&<>]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[char])); }
function showToast(message) { toastEl.textContent = message; toastEl.classList.add("visible"); setTimeout(() => toastEl.classList.remove("visible"), 2600); }

async function boot() {
  const [configResponse, workspaceResponse, promptResponse] = await Promise.all([fetch("/api/config"), fetch("/api/workspace"), fetch("/agent_prompt.txt")]);
  if (configResponse.ok) config = await configResponse.json();
  const workspace = workspaceResponse.ok ? await workspaceResponse.json() : { files: [] };
  defaultSystemPrompt = promptResponse.ok ? await promptResponse.text() : "Voce e o Mega Brain, agente local de engenharia de software.";
  renderModels(); renderProjects(); renderThreads(); renderSkills();
  $("#workspaceLabel").textContent = `${workspace.files.length} arquivos indexados`;
  statusEl.textContent = "LM Studio pronto";
  renderConversation(); updateContextMeter(0, selectedModelWindow());
}

function renderModels() {
  const select = $("#modelInput");
  select.replaceChildren(...config.models.map((model) => { const option = new Option(`${model.label} · ${model.description}`, model.id); option.selected = model.id === state.settings.model; return option; }));
}
function renderProjects() {
  $("#projectTree").innerHTML = state.projects.map((project) => `<button class="project-node ${project.id === state.activeProjectId ? "active" : ""}" data-project="${project.id}"><span>▾</span><b>${escapeText(project.name)}</b><small>${project.threads.length}</small></button>`).join("");
  document.querySelectorAll("[data-project]").forEach((node) => node.addEventListener("click", () => { state.activeProjectId = node.dataset.project; state.activeThreadId = activeProject().threads[0].id; saveState(); renderProjects(); renderThreads(); renderConversation(); }));
}
function renderThreads() {
  const project = activeProject(); $("#threadCount").textContent = project.threads.length;
  $("#threadList").innerHTML = project.threads.map((thread) => `<button class="thread-node ${thread.id === state.activeThreadId ? "active" : ""}" data-thread="${thread.id}"><span>◌</span><b>${escapeText(thread.title)}</b></button>`).join("");
  $("#activeProjectLabel").textContent = project.name; $("#activeThreadTitle").textContent = activeThread().title;
  document.querySelectorAll("[data-thread]").forEach((node) => node.addEventListener("click", () => { state.activeThreadId = node.dataset.thread; saveState(); renderThreads(); renderConversation(); }));
}
function renderSkills() {
  $("#skillsList").innerHTML = config.skills.slice(0, 5).map((skill, index) => `<button class="skill-chip ${index === 0 ? "active" : ""}" data-skill="${skill.id}"><span>${index === 0 ? "✦" : "◈"}</span>${escapeText(skill.name)}<small>${escapeText(skill.category)}</small></button>`).join("");
}
function renderConversation() {
  const thread = activeThread();
  messagesEl.querySelectorAll(".user, .assistant:not(.welcome-message)").forEach((node) => node.remove());
  thread.messages.forEach((message) => addMessage(message.role, message.content));
}
function addMessage(role, content) {
  const article = document.createElement("article"); article.className = `message ${role}`;
  const avatar = document.createElement("div"); avatar.className = "message-avatar"; avatar.innerHTML = role === "user" ? "EU" : "<img src='./mega-brain-space.svg' alt='Mega Brain no espaço'><span>✦</span>";
  const body = document.createElement("div"); body.className = "message-body";
  body.innerHTML = `<div class="message-meta"><strong>${role === "user" ? "Você" : "Mega Brain"}</strong><span>${role === "user" ? "INPUT" : "LOCAL MODEL"}</span></div><div class="bubble">${escapeText(content)}</div>`;
  article.append(avatar, body); messagesEl.append(article); messagesEl.scrollTop = messagesEl.scrollHeight;
}
function selectedModelWindow() { return config.models.find((model) => model.id === (state.settings.model === "auto" ? "qwen2.5-coder-14b-instruct" : state.settings.model))?.window || config.contextWindow; }
function updateContextMeter(used, window) {
  const percent = Math.min(100, Math.round((used / Math.max(1, window)) * 100)); $("#contextPercent").textContent = `${percent}%`; $("#contextTokens").textContent = `${used.toLocaleString("pt-BR")} / ${(window / 1000).toFixed(1)}k`; $("#contextRing").style.setProperty("--percent", `${percent * 3.6}deg`);
}
function compactMessages() { const thread = activeThread(); return thread.messages.slice(-state.settings.contextLimit); }
function cleanAgentAnswer(answer) { return answer.replace(/<mega-write\s+path="[^"]+">[\s\S]*?<\/mega-write>/g, "").trim(); }
async function applyAgentWrites(answer) {
  const writes = [...answer.matchAll(/<mega-write\s+path="([^"]+)">([\s\S]*?)<\/mega-write>/g)]; const saved = [];
  for (const [, path, content] of writes) { const response = await fetch("/api/workspace/write", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, content }) }); if (!response.ok) throw new Error(`Falha ao salvar ${path}: ${await response.text()}`); saved.push(path); }
  return saved;
}
async function requestCompletion(prompt) {
  const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: state.settings.model, taskMode: state.settings.taskMode, messages: [{ role: "system", content: defaultSystemPrompt }, ...compactMessages().map((message) => ({ role: message.role, content: message.content })), { role: "user", content: `${prompt}\n\nArquivos anexados ao contexto: ${pendingFiles.map((file) => file.name).join(", ") || "nenhum"}` }], temperature: 0.35, stream: false, baseUrl: state.settings.endpoint }) });
  const text = await response.text(); if (!response.ok) throw new Error(text || `HTTP ${response.status}`); const data = JSON.parse(text); const answer = data.choices?.[0]?.message?.content?.trim() || "Sem conteúdo na resposta."; const saved = await applyAgentWrites(answer); if (data.mega) updateContextMeter(data.mega.estimatedTokens, data.mega.contextWindow); return `${cleanAgentAnswer(answer)}${saved.length ? `\n\nArquivos salvos: ${saved.join(", ")}` : ""}`.trim();
}
async function sendPrompt() {
  const prompt = promptInput.value.trim(); if (!prompt || sendButton.disabled) return; promptInput.value = ""; const thread = activeThread(); thread.messages.push({ role: "user", content: prompt }); addMessage("user", prompt); sendButton.disabled = true; statusEl.textContent = "Mega Brain pensando";
  try { const answer = await requestCompletion(prompt); thread.messages.push({ role: "assistant", content: answer }); addMessage("assistant", answer); saveState(); statusEl.textContent = "LM Studio pronto"; } catch (error) { addMessage("assistant", `Falha na execução: ${error.message}`); statusEl.textContent = "Verifique LM Studio"; } finally { sendButton.disabled = false; promptInput.focus(); pendingFiles = []; $("#attachmentLabel").textContent = "Contexto compacto ativo"; }
}

composer.addEventListener("submit", (event) => { event.preventDefault(); sendPrompt(); });
promptInput.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); composer.requestSubmit(); } });
promptInput.addEventListener("input", () => { promptInput.style.height = "auto"; promptInput.style.height = `${Math.min(promptInput.scrollHeight, 180)}px`; });
$("#newChatButton").addEventListener("click", () => { const thread = { id: crypto.randomUUID(), title: "Nova conversa", messages: [] }; activeProject().threads.unshift(thread); state.activeThreadId = thread.id; saveState(); renderThreads(); renderConversation(); promptInput.focus(); });
$("#newProjectButton").addEventListener("click", () => { const name = prompt("Nome do projeto:", "Novo projeto"); if (!name?.trim()) return; const project = { id: crypto.randomUUID(), name: name.trim(), threads: [{ id: crypto.randomUUID(), title: "Agente de código", messages: [] }] }; state.projects.unshift(project); state.activeProjectId = project.id; state.activeThreadId = project.threads[0].id; saveState(); renderProjects(); renderThreads(); renderConversation(); });
$("#taskModeInput").addEventListener("change", (event) => { state.settings.taskMode = event.target.value; saveState(); }); $("#modelInput").addEventListener("change", (event) => { state.settings.model = event.target.value; saveState(); updateContextMeter(0, selectedModelWindow()); });
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => { promptInput.value = button.dataset.prompt; promptInput.focus(); }));
$("#attachButton").addEventListener("click", () => $("#fileInput").click()); $("#fileInput").addEventListener("change", (event) => { pendingFiles = [...event.target.files]; $("#attachmentLabel").textContent = `${pendingFiles.length} arquivo(s) pronto(s) para leitura`; });
$("#githubButton").addEventListener("click", async () => { const repository = prompt("Repositório (usuario/repositorio):"); const token = prompt("Token GitHub (usado somente nesta sessão):"); if (!repository || !token) return; try { const response = await fetch("/api/integrations/github", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repository, token }) }); if (!response.ok) throw new Error(await response.text()); const data = await response.json(); $("#githubLabel").textContent = `${data.repository} conectado`; showToast("GitHub conectado sem salvar o token"); } catch (error) { showToast(`GitHub: ${error.message}`); } });
$("#vaultButton").addEventListener("click", async () => { const path = prompt("Caminho da pasta do Obsidian:"); if (!path) return; try { const response = await fetch(`/api/obsidian/scan?path=${encodeURIComponent(path)}`); if (!response.ok) throw new Error(await response.text()); const data = await response.json(); $("#vaultLabel").textContent = `${data.notes.length} notas indexadas`; showToast("Vault Obsidian conectado"); } catch (error) { showToast(`Obsidian: ${error.message}`); } }); $("#scanVaultButton").addEventListener("click", () => $("#vaultButton").click());
boot();
