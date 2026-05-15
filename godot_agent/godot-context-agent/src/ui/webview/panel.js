// Webview client. Plain JS — no framework, no build step. Communicates with
// the extension via vscode.postMessage. Stays small on purpose.

(function () {
  const vscode = acquireVsCodeApi();

  const $ = (id) => document.getElementById(id);
  const els = {
    scripts:    $("stat-scripts"),
    scenes:     $("stat-scenes"),
    autoloads:  $("stat-autoloads"),
    version:    $("engine-version"),
    query:      $("query"),
    tokenCount: $("token-count"),
    budgetFill: $("budget-fill"),
    out:        $("preview-out"),
    list:       $("autoloads-list"),
    reindex:    $("reindex"),
    apiQuery:   $("api-query"),
    apiResults: $("api-results"),
  };

  // Bootstrap
  vscode.postMessage({ type: "ready" });
  vscode.postMessage({ type: "apiSearch", query: "" });

  // Reindex button
  els.reindex.addEventListener("click", () => {
    els.reindex.disabled = true;
    els.reindex.textContent = "…";
    vscode.postMessage({ type: "reindex" });
    setTimeout(() => {
      els.reindex.disabled = false;
      els.reindex.textContent = "↻";
    }, 1200);
  });

  // Debounced preview
  let debounce = 0;
  els.query.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      vscode.postMessage({ type: "preview", query: els.query.value });
    }, 220);
  });

  // Debounced API search
  let apiDebounce = 0;
  els.apiQuery.addEventListener("input", () => {
    clearTimeout(apiDebounce);
    apiDebounce = setTimeout(() => {
      vscode.postMessage({ type: "apiSearch", query: els.apiQuery.value });
    }, 180);
  });

  // Incoming
  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (!msg || typeof msg.type !== "string") return;

    if (msg.type === "index") {
      els.scripts.textContent   = msg.data.scripts;
      els.scenes.textContent    = msg.data.scenes;
      els.autoloads.textContent = msg.data.autoloads.length;
      els.version.textContent   = msg.data.projectGodotVersion ?? "unknown";

      els.list.innerHTML = "";
      for (const a of msg.data.autoloads) {
        const li = document.createElement("li");
        const star = a.singleton ? "★ " : "";
        li.innerHTML =
          `<span>${star}${escapeHtml(a.name)}</span>` +
          `<span class="path">${escapeHtml(a.path)}</span>`;
        els.list.appendChild(li);
      }
    } else if (msg.type === "preview") {
      els.out.textContent = msg.markdown;
      els.tokenCount.textContent = `${msg.tokens} tokens`;
      // Pull budget from a CSS-var-able source — for now hardcode 2000 default
      const ratio = Math.min(1, msg.tokens / 2000);
      els.budgetFill.style.width = (ratio * 100).toFixed(0) + "%";
    } else if (msg.type === "apiResults") {
      els.apiResults.innerHTML = "";
      for (const r of msg.results) {
        const li = document.createElement("li");
        li.title = "Open Godot docs";
        const inh = r.inherits ? `<span class="api-inherits">: ${escapeHtml(r.inherits)}</span>` : "";
        li.innerHTML =
          `<div><span class="api-name">${escapeHtml(r.name)}</span>${inh}</div>` +
          `<div class="api-brief">${escapeHtml(r.brief)}</div>`;
        li.addEventListener("click", () => {
          vscode.postMessage({ type: "openDocs", url: r.url });
        });
        els.apiResults.appendChild(li);
      }
    }
  });

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
})();
