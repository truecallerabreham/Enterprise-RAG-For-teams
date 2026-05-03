const state = {
  repositories: [],
};

const els = {
  health: document.querySelector("#health"),
  repoForm: document.querySelector("#repoForm"),
  repoList: document.querySelector("#repoList"),
  repoSelect: document.querySelector("#repoSelect"),
  events: document.querySelector("#events"),
  answer: document.querySelector("#answer"),
  citations: document.querySelector("#citations"),
  retrieved: document.querySelector("#retrieved"),
  graphOutput: document.querySelector("#graphOutput"),
};

document.querySelector("#refreshRepos").addEventListener("click", loadRepositories);
document.querySelector("#requestIngest").addEventListener("click", () => ingestSelected(false));
document.querySelector("#confirmIngest").addEventListener("click", () => ingestSelected(true));
document.querySelector("#inspectGraph").addEventListener("click", inspectGraph);
document.querySelector("#clearEvents").addEventListener("click", () => {
  els.events.innerHTML = "";
});

els.repoForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    name: form.get("name"),
    git_url: form.get("git_url"),
    default_branch: form.get("default_branch") || "main",
    visibility: form.get("visibility"),
    credential_env_var: form.get("credential_env_var") || null,
  };
  const repo = await request("/repositories", { method: "POST", body: payload });
  addEvent("completed", `Registered ${repo.name}. It is not searchable until ingestion is confirmed.`);
  event.currentTarget.reset();
  await loadRepositories();
  selectRepo(repo.id);
  const permissionJob = await request(`/repositories/${repo.id}/ingest`, {
    method: "POST",
    body: { confirm: false },
  });
  renderEvents(permissionJob.assistant_events);
  await loadRepositories();
  selectRepo(repo.id);
});

document.querySelector("#queryForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const repoId = selectedRepoId();
  const response = await request("/query", {
    method: "POST",
    body: {
      question: form.get("question"),
      repo_ids: repoId ? [repoId] : [],
      top_k: 8,
    },
  });
  renderEvents(response.assistant_events);
  renderAnswer(response);
});

async function boot() {
  const health = await request("/health");
  els.health.textContent = `Service ${health.status} | vectors: ${health.vector_store} | graph: ${health.graph_store}`;
  await loadRepositories();
}

async function loadRepositories() {
  const selected = selectedRepoId();
  state.repositories = await request("/repositories");
  els.repoList.innerHTML = "";
  els.repoSelect.innerHTML = "";
  for (const repo of state.repositories) {
    const item = document.createElement("div");
    item.className = "item";
    item.innerHTML = `<div class="item-title">${escapeHtml(repo.name)}</div>
      <div class="meta">${escapeHtml(repo.git_url)}</div>
      <div class="meta">${escapeHtml(repo.default_branch)} | ${escapeHtml(repo.visibility)}</div>
      <div class="meta">Status: ${escapeHtml(repo.indexing_status)} | chunks: ${repo.chunk_count}</div>
      ${repo.last_error ? `<div class="meta error-text">${escapeHtml(repo.last_error)}</div>` : ""}`;
    els.repoList.appendChild(item);

    const option = document.createElement("option");
    option.value = repo.id;
    option.textContent = `${repo.name} (${repo.indexing_status}, ${repo.chunk_count} chunks)`;
    els.repoSelect.appendChild(option);
  }
  if (!state.repositories.length) {
    els.repoList.innerHTML = `<div class="item"><div class="meta">No repositories registered yet.</div></div>`;
  }
  selectRepo(selected);
}

async function ingestSelected(confirm) {
  const repoId = selectedRepoId();
  if (!repoId) {
    addEvent("failed", "Register or select a repository first.");
    return;
  }
  const action = confirm ? "confirmed ingestion" : "permission request";
  addEvent("planning", `Starting ${action} for the selected repository.`);
  const job = await request(`/repositories/${repoId}/ingest`, {
    method: "POST",
    body: { confirm },
  });
  renderEvents(job.assistant_events);
  if (job.errors?.length) {
    for (const error of job.errors) {
      addEvent("failed", error);
    }
  }
  await loadRepositories();
  selectRepo(repoId);
}

async function inspectGraph() {
  const repoId = selectedRepoId();
  if (!repoId) {
    addEvent("failed", "Register or select a repository first.");
    return;
  }
  const graph = await request(`/repositories/${repoId}/graph`);
  if (!graph.symbols.length) {
    const repo = state.repositories.find((item) => item.id === repoId);
    els.graphOutput.textContent =
      `No graph symbols have been indexed for this repository yet.\n\n` +
      `Current status: ${repo?.indexing_status || "unknown"}\n` +
      `Next step: click "Confirm Ingest" so the backend can clone/fetch, parse, and index the code.`;
    addEvent("needs_permission", "Graph is empty because this repository has not been indexed yet.");
    return;
  }
  els.graphOutput.textContent = JSON.stringify(graph, null, 2);
}

function renderAnswer(response) {
  els.answer.textContent = response.answer;
  els.citations.innerHTML = response.citations
    .map(
      (citation) => `<div class="item">
        <div class="item-title">${escapeHtml(citation.repo)} | ${escapeHtml(citation.file)}</div>
        <div class="meta">Lines ${citation.start_line}-${citation.end_line}</div>
      </div>`,
    )
    .join("");
  els.retrieved.innerHTML = response.retrieved_chunks
    .map(
      (chunk) => `<div class="item">
        <div class="item-title">${escapeHtml(chunk.repo_name)} | ${escapeHtml(chunk.file_path)}</div>
        <div class="meta">Lines ${chunk.start_line}-${chunk.end_line} | score ${chunk.score.toFixed(3)} | ${escapeHtml(chunk.retrieval_sources.join(", "))}</div>
        <div class="meta">${escapeHtml(chunk.summary)}</div>
      </div>`,
    )
    .join("");
}

function renderEvents(events) {
  for (const event of events || []) {
    addEvent(event.type, event.message);
  }
}

function addEvent(type, message) {
  const event = document.createElement("div");
  event.className = `event ${type}`;
  event.innerHTML = `<div class="item-title">${escapeHtml(type)}</div><div class="meta">${escapeHtml(message)}</div>`;
  els.events.prepend(event);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail || "Request failed";
    addEvent("failed", typeof detail === "string" ? detail : JSON.stringify(detail));
    throw new Error(detail);
  }
  return data;
}

function selectedRepoId() {
  return els.repoSelect.value || null;
}

function selectRepo(repoId) {
  if (repoId) {
    els.repoSelect.value = repoId;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

boot().catch((error) => addEvent("failed", error.message));
