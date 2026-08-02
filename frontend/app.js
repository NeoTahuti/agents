const $ = (selector) => document.querySelector(selector);
const messagesEl = $("#messages");
const composer = $("#composer");
const promptInput = $("#promptInput");
const sendButton = $("#sendButton");
const statusEl = $("#connectionLabel");
const toastEl = $("#toast");
const STORAGE_KEY = "mega-brain-state-v4";
const defaultState = {
  projects: [{ id: "workspace", name: "Local workspace", path: "", threads: [{ id: "welcome", title: "Coding agent", messages: [] }] }],
  activeProjectId: "workspace",
  activeThreadId: "welcome",
  integrations: { vaultPath: "C:\\mega_brain_agent\\mega_brain_vault", githubRepository: "NeoTahuti/agents" },
  settings: { endpoint: "http://localhost:1234/v1", model: "auto", taskMode: "code", contextLimit: 8 },
};
let state = loadState();
let config = { models: [], skills: [], contextWindow: 8192, lm: { connected: false } };
let defaultSystemPrompt = "";
let pendingFiles = [];
let recorder;

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (!saved) return structuredClone(defaultState);
    return { ...structuredClone(defaultState), ...saved, integrations: { ...defaultState.integrations, ...saved.integrations }, settings: { ...defaultState.settings, ...saved.settings } };
  } catch { return structuredClone(defaultState); }
}
function saveState() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
function activeProject() { return state.projects.find((project) => project.id === state.activeProjectId) || state.projects[0]; }
function activeThread() { return activeProject().threads.find((thread) => thread.id === state.activeThreadId) || activeProject().threads[0]; }
function escapeText(value) { return String(value).replace(/[&<>]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[char])); }
function showToast(message) { toastEl.textContent = message; toastEl.classList.add("visible"); setTimeout(() => toastEl.classList.remove("visible"), 3200); }
function openDialog(id) { $(id).showModal(); }
function closeDialog(id) { $(id).close(); }
function sourceConnected(sourceId, connected) { $(sourceId).classList.toggle("muted-source", !connected); }

async function boot() {
  try {
    const [configResponse, promptResponse] = await Promise.all([fetch("/api/config"), fetch("/agent_prompt.txt")]);
    if (!configResponse.ok) throw new Error(`Mega Brain API returned ${configResponse.status}`);
    config = await configResponse.json();
    defaultSystemPrompt = promptResponse.ok ? await promptResponse.text() : "You are Mega Brain, a local software engineering agent.";
    renderModels(); renderProjects(); renderThreads(); renderSkills(); renderConversation();
    $("#endpointInput").value = state.settings.endpoint;
    $("#contextLimitInput").value = state.settings.contextLimit;
    $("#systemPromptInput").value = defaultSystemPrompt;
    $("#vaultPathInput").value = state.integrations.vaultPath;
    $("#githubRepoInput").value = state.integrations.githubRepository;
    applyLmStatus(config.lm);
    await loadWorkspace();
    await scanVault(true);
  } catch (error) {
    statusEl.textContent = "Mega Brain server unavailable";
    $("#connectionDot").classList.add("offline");
    showToast(error.message);
  }
}
function applyLmStatus(lm) {
  const connected = Boolean(lm?.connected);
  statusEl.textContent = connected ? `LM Studio ready (${lm.loadedModelIds.length} loaded)` : "LM Studio unavailable";
  $("#connectionDot").classList.toggle("offline", !connected);
  if (!connected && lm?.error) showToast(`LM Studio: ${lm.error}`);
  updateContextMeter(0, selectedModelWindow());
}
async function loadWorkspace() {
  const root = activeProject().path || "";
  const response = await fetch(`/api/workspace?root=${encodeURIComponent(root)}`);
  if (!response.ok) throw new Error(await response.text());
  const workspace = await response.json();
  $("#workspaceLabel").textContent = `${workspace.files.length} files indexed`;
}
function renderModels() {
  const select = $("#modelInput");
  select.replaceChildren(...config.models.map((model) => {
    const option = new Option(`${model.label} - ${model.description}`, model.id);
    option.selected = model.id === state.settings.model;
    return option;
  }));
  if (!select.value && config.models.length) select.value = "auto";
}
function renderProjects() {
  $("#projectTree").innerHTML = state.projects.map((project) => `<button class="project-node ${project.id === state.activeProjectId ? "active" : ""}" data-project="${project.id}"><span>&gt;</span><b>${escapeText(project.name)}</b><small>${project.threads.length}</small></button>`).join("");
  document.querySelectorAll("[data-project]").forEach((node) => node.addEventListener("click", async () => {
    state.activeProjectId = node.dataset.project;
    state.activeThreadId = activeProject().threads[0].id;
    saveState(); renderProjects(); renderThreads(); renderConversation();
    try { await loadWorkspace(); } catch (error) { showToast(`Workspace: ${error.message}`); }
  }));
}
function renderThreads() {
  const project = activeProject();
  $("#threadCount").textContent = project.threads.length;
  $("#threadList").innerHTML = project.threads.map((thread) => `<button class="thread-node ${thread.id === state.activeThreadId ? "active" : ""}" data-thread="${thread.id}"><span>o</span><b>${escapeText(thread.title)}</b></button>`).join("");
  $("#activeProjectLabel").textContent = project.name;
  $("#activeThreadTitle").textContent = activeThread().title;
  document.querySelectorAll("[data-thread]").forEach((node) => node.addEventListener("click", () => {
    state.activeThreadId = node.dataset.thread; saveState(); renderThreads(); renderConversation();
  }));
}
function renderSkills() {
  $("#skillsList").innerHTML = config.skills.slice(0, 5).map((skill, index) => `<button class="skill-chip ${index === 0 ? "active" : ""}" data-skill="${skill.id}"><span>${index === 0 ? "*" : "+"}</span>${escapeText(skill.name)}<small>${escapeText(skill.category)}</small></button>`).join("");
  document.querySelectorAll("[data-skill]").forEach((node) => node.addEventListener("click", () => {
    node.classList.toggle("active"); showToast(`${node.classList.contains("active") ? "Enabled" : "Disabled"}: ${node.textContent.trim()}`);
  }));
}
function renderConversation() {
  const thread = activeThread();
  messagesEl.querySelectorAll(".user, .assistant:not(.welcome-message)").forEach((node) => node.remove());
  thread.messages.forEach((message) => addMessage(message.role, message.content));
}
function addMessage(role, content) {
  const article = document.createElement("article"); article.className = `message ${role}`;
  const avatar = document.createElement("div"); avatar.className = "message-avatar";
  avatar.innerHTML = role === "user" ? "<img src='./gray-alien.svg' alt='Gray alien avatar'>" : "<img src='./mega-brain-space.svg' alt='Dystopian Mega Brain in space'><span>MB</span>";
  const body = document.createElement("div"); body.className = "message-body";
  body.innerHTML = `<div class="message-meta"><strong>${role === "user" ? "You" : "Mega Brain"}</strong><span>${role === "user" ? "INPUT" : "LOCAL MODEL"}</span></div><div class="bubble">${escapeText(content)}</div>`;
  article.append(avatar, body); messagesEl.append(article); messagesEl.scrollTop = messagesEl.scrollHeight;
}
function selectedModelWindow() { return config.models.find((model) => model.id === state.settings.model)?.window || config.contextWindow || 8192; }
function updateContextMeter(used, window) {
  const percent = Math.min(100, Math.round((used / Math.max(1, window)) * 100));
  $("#contextPercent").textContent = `${percent}%`;
  $("#contextTokens").textContent = `${used.toLocaleString("en-US")} / ${(window / 1000).toFixed(1)}k`;
  $("#contextRing").style.setProperty("--percent", `${percent * 3.6}deg`);
}
function compactMessages() { return activeThread().messages.slice(-state.settings.contextLimit); }
function cleanAnswer(answer) { return answer.replace(/<mega-write\s+path="[^"]+">[\s\S]*?<\/mega-write>/g, "").replace(/<mega-edit\s+path="[^"]+">[\s\S]*?<\/mega-edit>/g, "").trim(); }
async function applyAgentWrites(answer) {
  const writes = [...answer.matchAll(/<mega-write\s+path="([^"]+)">([\s\S]*?)<\/mega-write>/g)];
  const edits = [...answer.matchAll(/<mega-edit\s+path="([^"]+)">\s*SEARCH:\s*\n([\s\S]*?)\nREPLACE:\s*\n([\s\S]*?)<\/mega-edit>/g)];
  const saved = [];
  for (const [, path, content] of writes) {
    const response = await fetch("/api/workspace/write", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, content, workspaceRoot: activeProject().path || "" }) });
    if (!response.ok) throw new Error(`Failed to save ${path}: ${await response.text()}`);
    const result = await response.json();
    saved.push({ path, validation: result.validation?.message || "File written" });
  }
  for (const [, path, search, replace] of edits) {
    const response = await fetch("/api/workspace/edit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, search, replace, workspaceRoot: activeProject().path || "" }) });
    if (!response.ok) throw new Error(`Failed to edit ${path}: ${await response.text()}`);
    const result = await response.json();
    saved.push({ path, validation: result.validation?.message || "Exact edit applied" });
  }
  return saved;
}
async function requestCompletion() {
  const response = await fetch("/api/chat", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: state.settings.model, taskMode: state.settings.taskMode, workspaceRoot: activeProject().path || "", messages: [{ role: "system", content: defaultSystemPrompt }, ...compactMessages()], temperature: 0.35, stream: false, baseUrl: state.settings.endpoint }),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
  const data = JSON.parse(text);
  const answer = data.choices?.[0]?.message?.content?.trim() || "No content returned.";
  const saved = await applyAgentWrites(answer);
  if (data.mega) updateContextMeter(data.mega.estimatedTokens, data.mega.contextWindow);
  const verification = saved.map((item) => `${item.path}: ${item.validation}`).join("; ");
  return `${cleanAnswer(answer)}${saved.length ? `\n\nFiles saved: ${verification}` : ""}`.trim();
}
async function sendPrompt() {
  const prompt = promptInput.value.trim();
  if (!prompt || sendButton.disabled) return;
  promptInput.value = "";
  const thread = activeThread(); thread.messages.push({ role: "user", content: `${prompt}\n\nFiles attached to context: ${pendingFiles.map((file) => file.name).join(", ") || "none"}` });
  addMessage("user", prompt); sendButton.disabled = true; statusEl.textContent = "Mega Brain thinking";
  try {
    const answer = await requestCompletion(); thread.messages.push({ role: "assistant", content: answer }); addMessage("assistant", answer); saveState(); applyLmStatus(config.lm);
  } catch (error) {
    addMessage("assistant", `Execution failed: ${error.message}`); statusEl.textContent = "Check LM Studio";
  } finally {
    sendButton.disabled = false; promptInput.focus(); pendingFiles = []; $("#attachmentLabel").textContent = "Compact context active";
  }
}
async function refreshModels() {
  const response = await fetch("/api/lm/status");
  if (!response.ok) throw new Error(await response.text());
  const lm = await response.json(); config.models = lm.models; config.contextWindow = lm.contextWindow; config.lm = lm; renderModels(); applyLmStatus(lm); return lm;
}
async function scanVault(silent = false) {
  const path = state.integrations.vaultPath;
  const response = await fetch(`/api/obsidian/scan?path=${encodeURIComponent(path)}`);
  if (!response.ok) { if (!silent) throw new Error(await response.text()); return; }
  const data = await response.json();
  $("#vaultLabel").textContent = `${data.notes.length} notes indexed`; sourceConnected("#vaultSource", true);
  if (!silent) showToast("Obsidian vault connected");
}

composer.addEventListener("submit", (event) => { event.preventDefault(); sendPrompt(); });
promptInput.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); composer.requestSubmit(); } });
promptInput.addEventListener("input", () => { promptInput.style.height = "auto"; promptInput.style.height = `${Math.min(promptInput.scrollHeight, 180)}px`; });
$("#newChatButton").addEventListener("click", () => { const thread = { id: crypto.randomUUID(), title: "New conversation", messages: [] }; activeProject().threads.unshift(thread); state.activeThreadId = thread.id; saveState(); renderThreads(); renderConversation(); promptInput.focus(); });
$("#newProjectButton").addEventListener("click", () => { $("#projectNameInput").value = ""; openDialog("#projectDialog"); $("#projectNameInput").focus(); });
$("#createProjectButton").addEventListener("click", async (event) => {
  event.preventDefault(); const name = $("#projectNameInput").value.trim(); if (!name) return showToast("Enter a project name");
  try {
    const response = await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
    if (!response.ok) throw new Error(await response.text());
    const created = await response.json(); const project = { id: created.id, name: created.name, path: created.path, threads: [{ id: crypto.randomUUID(), title: "Coding agent", messages: [] }] };
    state.projects.unshift(project); state.activeProjectId = project.id; state.activeThreadId = project.threads[0].id; saveState(); closeDialog("#projectDialog"); renderProjects(); renderThreads(); renderConversation(); await loadWorkspace(); showToast(`Created projects/${created.id}`);
  } catch (error) { showToast(`Project creation failed: ${error.message}`); }
});
$("#taskModeInput").addEventListener("change", (event) => { state.settings.taskMode = event.target.value; saveState(); });
$("#modelInput").addEventListener("change", (event) => { state.settings.model = event.target.value; saveState(); updateContextMeter(0, selectedModelWindow()); showToast(`Requests will use ${event.target.options[event.target.selectedIndex].text}`); });
$("#refreshModelsButton").addEventListener("click", async () => { try { const lm = await refreshModels(); showToast(`${lm.loadedModelIds.length} loaded LLM(s) detected`); } catch (error) { showToast(`LM Studio models: ${error.message}`); } });
$("#openSettingsButton").addEventListener("click", () => openDialog("#settingsDialog"));
$("#saveSettingsButton").addEventListener("click", async (event) => { event.preventDefault(); state.settings.endpoint = $("#endpointInput").value.trim() || state.settings.endpoint; state.settings.contextLimit = Math.max(2, Number($("#contextLimitInput").value) || 8); defaultSystemPrompt = $("#systemPromptInput").value.trim() || defaultSystemPrompt; saveState(); closeDialog("#settingsDialog"); try { await refreshModels(); showToast("Settings saved"); } catch (error) { showToast(`Settings saved. LM Studio: ${error.message}`); } });
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => { promptInput.value = button.dataset.prompt; promptInput.focus(); }));
$("#attachButton").addEventListener("click", () => $("#fileInput").click());
$("#fileInput").addEventListener("change", (event) => { pendingFiles = [...event.target.files]; $("#attachmentLabel").textContent = `${pendingFiles.length} file(s) ready for context`; });
$("#voiceButton").addEventListener("click", async () => {
  if (recorder?.state === "recording") return recorder.stop();
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) return showToast("Voice recording is not supported by this browser");
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true }); recorder = new MediaRecorder(stream); const chunks = [];
    recorder.ondataavailable = (event) => chunks.push(event.data);
    recorder.onstop = async () => { stream.getTracks().forEach((track) => track.stop()); $("#attachmentLabel").textContent = "Transcribing locally..."; try { const response = await fetch("/api/transcribe", { method: "POST", headers: { "Content-Type": recorder.mimeType || "audio/webm" }, body: new Blob(chunks, { type: recorder.mimeType || "audio/webm" }) }); if (!response.ok) throw new Error(await response.text()); const data = await response.json(); promptInput.value = `${promptInput.value}${promptInput.value ? " " : ""}${data.text}`; $("#attachmentLabel").textContent = `Detected ${data.language || "speech"}`; } catch (error) { showToast(`Voice input: ${error.message}`); $("#attachmentLabel").textContent = "Compact context active"; } };
    recorder.start(); $("#attachmentLabel").textContent = "Recording... click to stop";
  } catch (error) { showToast(`Microphone: ${error.message}`); }
});
$("#speakButton").addEventListener("click", async () => { const latest = [...activeThread().messages].reverse().find((message) => message.role === "assistant"); if (!latest) return showToast("There is no answer to read yet"); try { const response = await fetch("/api/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: latest.content, language: /[\u00e0-\u00ff]/i.test(latest.content) ? "pt_BR" : "en_US" }) }); if (!response.ok) throw new Error(await response.text()); await new Audio(URL.createObjectURL(await response.blob())).play(); } catch (error) { showToast(`Voice output: ${error.message}`); } });
function openIntegration(type) { $("#integrationTitle").textContent = type === "github" ? "Connect GitHub" : "Connect Obsidian"; $("#githubFields").hidden = type !== "github"; $("#vaultFields").hidden = type !== "vault"; $("#integrationDialog").dataset.type = type; openDialog("#integrationDialog"); }
$("#githubButton").addEventListener("click", () => openIntegration("github")); $("#vaultButton").addEventListener("click", () => openIntegration("vault"));
$("#scanVaultButton").addEventListener("click", async () => { try { await scanVault(); } catch (error) { showToast(`Obsidian: ${error.message}`); } });
$("#connectSourceButton").addEventListener("click", async (event) => {
  event.preventDefault(); const type = $("#integrationDialog").dataset.type;
  try {
    if (type === "github") {
      const repository = $("#githubRepoInput").value.trim();
      const response = await fetch("/api/integrations/github", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repository, token: $("#githubTokenInput").value }) });
      if (!response.ok) throw new Error(await response.text()); const data = await response.json(); state.integrations.githubRepository = repository; $("#githubLabel").textContent = `${data.repository} connected`; sourceConnected("#githubSource", true);
    } else { state.integrations.vaultPath = $("#vaultPathInput").value.trim(); await scanVault(); }
    saveState(); closeDialog("#integrationDialog"); showToast(`${type === "github" ? "GitHub" : "Obsidian"} connected`);
  } catch (error) { showToast(`Connection failed: ${error.message}`); }
});
boot();
