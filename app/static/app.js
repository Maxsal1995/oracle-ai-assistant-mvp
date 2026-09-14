const state = { profiles: [], currentResult: null, status: null };
const $ = (selector) => document.querySelector(selector);
const elements = {
  statusButton: $("#statusButton"), statusDot: $("#statusDot"), statusText: $("#statusText"),
  profileSelect: $("#profileSelect"), profileDescription: $("#profileDescription"),
  knowledgeCount: $("#knowledgeCount"), knowledgeText: $("#knowledgeText"),
  knowledgeFiles: $("#knowledgeFiles"), knowledgeRedact: $("#knowledgeRedact"),
  addKnowledgeButton: $("#addKnowledgeButton"), knowledgeList: $("#knowledgeList"),
  historyList: $("#historyList"), refreshHistoryButton: $("#refreshHistoryButton"),
  form: $("#analysisForm"), modelSelect: $("#modelSelect"), redact: $("#redact"),
  caseFiles: $("#caseFiles"), selectedFiles: $("#selectedFiles"), dropZone: $("#caseDropZone"),
  loadSampleButton: $("#loadSampleButton"), clearButton: $("#clearButton"),
  analyseButton: $("#analyseButton"), resultSection: $("#resultSection"),
  resultTitle: $("#resultTitle"), confidenceBadge: $("#confidenceBadge"),
  executiveSummary: $("#executiveSummary"), resultMeta: $("#resultMeta"),
  signalCount: $("#signalCount"), findingCount: $("#findingCount"),
  heuristicResults: $("#heuristicResults"), aiFindings: $("#aiFindings"),
  nextSteps: $("#nextSteps"), missingInformation: $("#missingInformation"),
  disclaimer: $("#disclaimer"), exportButton: $("#exportButton"),
  profileDialog: $("#profileDialog"), profileForm: $("#profileForm"),
  newProfileButton: $("#newProfileButton"), closeProfileDialog: $("#closeProfileDialog"),
  toast: $("#toast")
};

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  let payload = {};
  try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) throw new Error(payload.detail || "Request failed (" + response.status + ")");
  return payload;
}

let toastTimer;
function showToast(message, isError = false) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", isError);
  elements.toast.classList.add("visible");
  toastTimer = setTimeout(() => elements.toast.classList.remove("visible"), 4200);
}

function setLoading(loading) {
  elements.analyseButton.disabled = loading;
  elements.analyseButton.classList.toggle("loading", loading);
}

async function loadStatus() {
  elements.statusText.textContent = "Checking Ollama…";
  try {
    const status = await request("/api/status");
    state.status = status;
    const online = status.ollama === "online";
    elements.statusDot.className = "status-dot " + (online ? "online" : "offline");
    elements.statusText.textContent = online
      ? "Ollama · " + status.models.length + " model" + (status.models.length === 1 ? "" : "s")
      : "Ollama offline";
    const previous = elements.modelSelect.value;
    elements.modelSelect.innerHTML = "";
    if (!status.models.length) {
      elements.modelSelect.innerHTML = '<option value="">No model detected</option>';
      return;
    }
    for (const model of status.models) {
      const option = document.createElement("option");
      option.value = model; option.textContent = model; elements.modelSelect.append(option);
    }
    if (status.models.includes(previous)) elements.modelSelect.value = previous;
    else if (status.models.includes(status.preferred_model)) elements.modelSelect.value = status.preferred_model;
  } catch (error) {
    elements.statusDot.className = "status-dot offline";
    elements.statusText.textContent = "Status unavailable";
    showToast(error.message, true);
  }
}

async function loadProfiles(selectedId = elements.profileSelect.value) {
  try {
    state.profiles = await request("/api/profiles");
    elements.profileSelect.innerHTML = '<option value="">No profile</option>';
    for (const profile of state.profiles) {
      const option = document.createElement("option");
      option.value = profile.id; option.textContent = profile.name; elements.profileSelect.append(option);
    }
    if (selectedId && state.profiles.some((item) => String(item.id) === String(selectedId))) {
      elements.profileSelect.value = String(selectedId);
    }
    updateProfileDescription();
    await loadKnowledge();
  } catch (error) { showToast(error.message, true); }
}

function updateProfileDescription() {
  const id = Number(elements.profileSelect.value);
  const profile = state.profiles.find((item) => item.id === id);
  if (!profile) {
    elements.profileDescription.textContent = "Analyse evidence without saved database context.";
    elements.knowledgeCount.textContent = "0";
    return;
  }
  const details = [profile.oracle_version, profile.environment, profile.architecture].filter(Boolean);
  elements.profileDescription.textContent = details.join(" · ") || "Profile selected. Add useful database context below.";
  elements.knowledgeCount.textContent = String(profile.knowledge_documents || 0);
}

async function loadKnowledge() {
  const profileId = elements.profileSelect.value;
  elements.knowledgeList.innerHTML = "";
  if (!profileId) {
    elements.knowledgeList.innerHTML = '<p class="muted compact">Select a profile to manage its knowledge.</p>';
    return;
  }
  try {
    const documents = await request("/api/profiles/" + profileId + "/knowledge");
    elements.knowledgeCount.textContent = String(documents.length);
    if (!documents.length) {
      elements.knowledgeList.innerHTML = '<p class="muted compact">No knowledge documents yet.</p>';
      return;
    }
    for (const doc of documents) {
      const item = document.createElement("div");
      item.className = "knowledge-item";
      item.innerHTML = "<div><strong>" + escapeHtml(doc.title) + "</strong><small>" +
        doc.chunks + " chunks · " + Number(doc.characters).toLocaleString() +
        ' chars</small></div><button class="delete-mini" type="button" aria-label="Delete knowledge document">×</button>';
      item.querySelector("button").addEventListener("click", async () => {
        try {
          await request("/api/profiles/" + profileId + "/knowledge/" + doc.document_id, { method: "DELETE" });
          showToast("Knowledge document removed."); await loadProfiles(profileId);
        } catch (error) { showToast(error.message, true); }
      });
      elements.knowledgeList.append(item);
    }
  } catch (error) { showToast(error.message, true); }
}

async function addKnowledge() {
  const profileId = elements.profileSelect.value;
  if (!profileId) { showToast("Create or select a database profile first.", true); return; }
  const formData = new FormData();
  formData.append("title", "Manual profile notes");
  formData.append("text", elements.knowledgeText.value);
  formData.append("redact", String(elements.knowledgeRedact.checked));
  for (const file of elements.knowledgeFiles.files) formData.append("files", file);
  elements.addKnowledgeButton.disabled = true;
  try {
    const payload = await request("/api/profiles/" + profileId + "/knowledge", { method: "POST", body: formData });
    elements.knowledgeText.value = ""; elements.knowledgeFiles.value = "";
    showToast(payload.documents.length + " knowledge document(s) added locally.");
    await loadProfiles(profileId);
  } catch (error) { showToast(error.message, true); }
  finally { elements.addKnowledgeButton.disabled = false; }
}

async function loadHistory() {
  try {
    const cases = await request("/api/history?limit=25");
    elements.historyList.innerHTML = "";
    if (!cases.length) {
      elements.historyList.innerHTML = '<p class="muted compact">No saved cases yet.</p>'; return;
    }
    for (const item of cases) {
      const button = document.createElement("button");
      button.className = "history-item"; button.type = "button";
      button.innerHTML = "<strong>" + escapeHtml(item.title) + "</strong><small>" +
        escapeHtml(item.category) + " · " + escapeHtml(item.confidence) + " confidence</small>";
      button.addEventListener("click", () => openHistory(item.id));
      elements.historyList.append(button);
    }
  } catch (error) { showToast(error.message, true); }
}

async function openHistory(caseId) {
  try {
    const item = await request("/api/history/" + caseId);
    renderResult({
      case_id: item.id, title: item.title, analysis: item.result,
      heuristics: { signals: [], inventory: {} },
      meta: { model: item.model, profile: item.profile_name, history: true, database_connection: false }
    });
  } catch (error) { showToast(error.message, true); }
}

function selectedFilesChanged() {
  elements.selectedFiles.innerHTML = "";
  for (const file of elements.caseFiles.files) {
    const chip = document.createElement("span"); chip.className = "file-chip";
    chip.textContent = file.name + " · " + Math.ceil(file.size / 1024).toLocaleString() + " KB";
    elements.selectedFiles.append(chip);
  }
}

function loadSample() {
  $("#caseTitle").value = "Synthetic partition pruning review";
  $("#category").value = "SQL tuning";
  $("#question").value = "Why does this query read far more data than expected, and what should I validate before changing the index strategy?";
  $("#caseContext").value = "Oracle 19c test database. The table is range-partitioned by VV_TIMESTAMP. Exact query results must be preserved and no new index should be proposed without evidence.";
  $("#sqlText").value = "SELECT /* synthetic example */\n       vv_ce_id, vv_timestamp, vv_value\nFROM   demo_variable_value\nWHERE  TRUNC(vv_timestamp) = DATE '2026-09-01'\nAND    vv_ce_id = :ce_id\nORDER BY vv_timestamp;";
  $("#executionPlan").value = "SQL_ID  abc123xyz7890, child number 0\nPlan hash value: 3285471001\n\n| Id | Operation             | Name                | Starts | E-Rows | A-Rows | Buffers |\n|  0 | SELECT STATEMENT      |                     |      1 |        |  86400 | 2184000 |\n|  1 |  SORT ORDER BY        |                     |      1 |    100 |  86400 | 2184000 |\n|* 2 |   FILTER              |                     |      1 |        |  86400 | 2184000 |\n|  3 |    PARTITION RANGE ALL|                     |      1 |    100 |  86400 | 2184000 |\n|* 4 |     TABLE ACCESS FULL | DEMO_VARIABLE_VALUE |    365 |    100 |  86400 | 2184000 |\n\nPredicate Information:\n2 - filter(TRUNC(VV_TIMESTAMP)=DATE '2026-09-01')\n4 - filter(VV_CE_ID=:CE_ID)";
  $("#ddlStatistics").value = "CREATE TABLE demo_variable_value (\n  vv_ce_id NUMBER NOT NULL,\n  vv_timestamp TIMESTAMP NOT NULL,\n  vv_value NUMBER\n)\nPARTITION BY RANGE (vv_timestamp) INTERVAL (NUMTODSINTERVAL(1,'DAY'))\n(PARTITION p0 VALUES LESS THAN (TIMESTAMP '2026-01-01 00:00:00'));\n\nCREATE INDEX demo_vv_ix1 ON demo_variable_value (vv_ce_id, vv_timestamp) LOCAL;\n\n-- Synthetic rows: 180,000,000; daily rows: about 500,000";
  $("#logsErrors").value = "";
  showToast("Synthetic evidence loaded. No production data is included.");
}

function clearEvidence() {
  ["#question", "#caseContext", "#sqlText", "#executionPlan", "#ddlStatistics", "#logsErrors"]
    .forEach((selector) => { $(selector).value = ""; });
  elements.caseFiles.value = ""; selectedFilesChanged();
}

function listHtml(items, ordered = false) {
  if (!items || !items.length) return '<p class="muted compact">None supplied.</p>';
  const tag = ordered ? "ol" : "ul";
  return "<" + tag + ">" + items.map((item) => "<li>" + escapeHtml(item) + "</li>").join("") + "</" + tag + ">";
}

function severityClass(value) {
  const severity = ["critical", "high", "medium", "low", "info"].includes(value) ? value : "info";
  return "severity severity-" + severity;
}

function renderSignal(signal) {
  return '<article class="signal-card"><div class="card-title"><span class="' +
    severityClass(signal.severity) + '">' + escapeHtml(signal.severity) + "</span><h4>" +
    escapeHtml(signal.title) + '</h4></div><div class="card-body"><span class="card-label">Observed</span><p>' +
    escapeHtml(signal.evidence) + '</p><span class="card-label">Validation direction</span><p>' +
    escapeHtml(signal.guidance) + "</p></div></article>";
}

function renderFinding(finding) {
  const sql = (finding.validation_sql || []).map((statement) =>
    "<pre><code>" + escapeHtml(statement) + "</code></pre>").join("");
  return '<article class="finding-card"><div class="card-title"><span class="' +
    severityClass(finding.severity) + '">' + escapeHtml(finding.severity) + "</span><h4>" +
    escapeHtml(finding.title) + '</h4></div><div class="card-body"><span class="card-label">Observations</span>' +
    listHtml(finding.observations) + '<span class="card-label">Analysis</span><p>' +
    escapeHtml(finding.analysis) + '</p><span class="card-label">Recommendations</span>' +
    listHtml(finding.recommendations, true) +
    (sql ? '<span class="card-label">Read-only validation SQL</span>' + sql : "") +
    '<span class="card-label">Risk</span><p>' + escapeHtml(finding.risk || "No risk note returned.") +
    "</p></div></article>";
}

function renderResult(payload) {
  state.currentResult = payload;
  const analysis = payload.analysis || {};
  const signals = payload.heuristics?.signals || [];
  const findings = analysis.findings || [];
  elements.resultTitle.textContent = payload.title || "Analysis result";
  elements.confidenceBadge.textContent = "Confidence · " + (analysis.confidence || "unknown");
  elements.executiveSummary.textContent = analysis.executive_summary || "No summary returned.";
  elements.signalCount.textContent = String(signals.length);
  elements.findingCount.textContent = String(findings.length);
  elements.heuristicResults.innerHTML = signals.length ? signals.map(renderSignal).join("") :
    '<div class="empty-card">No deterministic signals are available for this view.</div>';
  elements.aiFindings.innerHTML = findings.length ? findings.map(renderFinding).join("") :
    '<div class="empty-card">The model returned no structured findings.</div>';
  elements.nextSteps.innerHTML = (analysis.next_steps || []).map((item) => "<li>" + escapeHtml(item) + "</li>").join("") ||
    "<li>No next steps returned.</li>";
  elements.missingInformation.innerHTML = (analysis.missing_information || []).map((item) => "<li>" + escapeHtml(item) + "</li>").join("") ||
    "<li>No missing information identified.</li>";
  elements.disclaimer.textContent = analysis.disclaimer || "Validate every recommendation before applying it.";
  const meta = payload.meta || {};
  const chips = [
    meta.model && "Model: " + meta.model,
    meta.profile && "Profile: " + meta.profile,
    Number.isInteger(meta.knowledge_chunks_used) && "Knowledge chunks: " + meta.knowledge_chunks_used,
    meta.evidence_truncated && "Evidence truncated to configured limit",
    meta.history && "Saved local case", "Database connection: disabled"
  ].filter(Boolean);
  elements.resultMeta.innerHTML = chips.map((chip) => '<span class="meta-chip">' + escapeHtml(chip) + "</span>").join("");
  elements.resultSection.classList.remove("hidden");
  elements.resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resultAsMarkdown(payload) {
  const analysis = payload.analysis || {};
  const lines = ["# " + (payload.title || "Oracle AI analysis"), "",
    "**Confidence:** " + (analysis.confidence || "unknown"),
    "**Model:** " + (payload.meta?.model || "unknown"), "**Database connection:** disabled", "",
    "## Executive summary", "", analysis.executive_summary || "", "", "## Deterministic signals", ""];
  for (const signal of payload.heuristics?.signals || []) {
    lines.push("### [" + String(signal.severity).toUpperCase() + "] " + signal.title, "",
      "- Evidence: " + signal.evidence, "- Validation direction: " + signal.guidance, "");
  }
  if (!(payload.heuristics?.signals || []).length) lines.push("No stored signals.", "");
  lines.push("## AI findings", "");
  for (const finding of analysis.findings || []) {
    lines.push("### [" + String(finding.severity).toUpperCase() + "] " + finding.title, "",
      "Observations:", ...(finding.observations || []).map((item) => "- " + item), "",
      finding.analysis || "", "", "Recommendations:",
      ...(finding.recommendations || []).map((item, index) => (index + 1) + ". " + item), "");
    if ((finding.validation_sql || []).length) {
      lines.push("Validation SQL:", "");
      for (const sql of finding.validation_sql) lines.push("~~~sql", sql, "~~~", "");
    }
    lines.push("Risk: " + (finding.risk || "Not specified."), "");
  }
  lines.push("## Next steps", "", ...(analysis.next_steps || []).map((item, index) => (index + 1) + ". " + item),
    "", "## Missing information", "", ...(analysis.missing_information || []).map((item) => "- " + item),
    "", "---", analysis.disclaimer || "Human validation required.");
  return lines.join("\n");
}

function exportResult() {
  if (!state.currentResult) return;
  const blob = new Blob([resultAsMarkdown(state.currentResult)], { type: "text/markdown;charset=utf-8" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
  const safeName = (state.currentResult.title || "oracle-ai-analysis").replace(/[^a-z0-9_-]+/gi, "-")
    .replace(/^-|-$/g, "").toLowerCase();
  link.download = (safeName || "oracle-ai-analysis") + ".md"; link.click(); URL.revokeObjectURL(link.href);
}

async function submitAnalysis(event) {
  event.preventDefault();
  const formData = new FormData(elements.form);
  const profileId = elements.profileSelect.value;
  if (profileId) formData.append("profile_id", profileId);
  if (!elements.redact.checked) formData.set("redact", "false");
  setLoading(true);
  try {
    const payload = await request("/api/analyse", { method: "POST", body: formData });
    renderResult(payload); await loadHistory();
    const redactions = Object.values(payload.meta?.redaction_counts || {}).reduce((sum, value) => sum + Number(value), 0);
    showToast(redactions ? "Analysis completed. " + redactions + " sensitive value(s) redacted." :
      "Analysis completed and saved locally.");
  } catch (error) { showToast(error.message, true); }
  finally { setLoading(false); }
}

async function createProfile(event) {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(elements.profileForm).entries());
  try {
    const profile = await request("/api/profiles", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values)
    });
    elements.profileDialog.close(); elements.profileForm.reset();
    await loadProfiles(profile.id); showToast("Database profile created locally.");
  } catch (error) { showToast(error.message, true); }
}

elements.statusButton.addEventListener("click", loadStatus);
elements.profileSelect.addEventListener("change", async () => { updateProfileDescription(); await loadKnowledge(); });
elements.newProfileButton.addEventListener("click", () => elements.profileDialog.showModal());
elements.closeProfileDialog.addEventListener("click", () => elements.profileDialog.close());
elements.profileForm.addEventListener("submit", createProfile);
elements.addKnowledgeButton.addEventListener("click", addKnowledge);
elements.refreshHistoryButton.addEventListener("click", loadHistory);
elements.caseFiles.addEventListener("change", selectedFilesChanged);
elements.form.addEventListener("submit", submitAnalysis);
elements.loadSampleButton.addEventListener("click", loadSample);
elements.clearButton.addEventListener("click", clearEvidence);
elements.exportButton.addEventListener("click", exportResult);

["dragenter", "dragover"].forEach((name) => elements.dropZone.addEventListener(name, (event) => {
  event.preventDefault(); elements.dropZone.classList.add("dragging");
}));
["dragleave", "drop"].forEach((name) => elements.dropZone.addEventListener(name, (event) => {
  event.preventDefault(); elements.dropZone.classList.remove("dragging");
}));
elements.dropZone.addEventListener("drop", (event) => {
  if (event.dataTransfer?.files?.length) {
    const transfer = new DataTransfer();
    for (const file of event.dataTransfer.files) transfer.items.add(file);
    elements.caseFiles.files = transfer.files; selectedFilesChanged();
  }
});
Promise.all([loadStatus(), loadProfiles(), loadHistory()]);
