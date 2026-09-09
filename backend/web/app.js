const $ = (id) => document.getElementById(id);

const ui = {
  url: $("video-url"), intent: $("intent"), paste: $("paste-button"), search: $("search-button"),
  clueGroup: $("social-clue-group"), clue: $("social-clue"),
  label: document.querySelector(".button-label"), note: $("search-note"), result: $("result"),
  resultTitle: $("result-title"), resultMessage: $("result-message"), kicker: $("result-kicker"),
  confidenceRow: $("confidence-row"), confidenceNumber: $("confidence-number"),
  confidenceFill: $("confidence-fill"), best: $("best-match"), matchTitle: $("match-title"),
  matchDetail: $("match-detail"), matchLink: $("match-link"), others: $("other-matches"),
  again: $("new-search"), dot: $("status-dot"), status: $("server-status")
};

const intentNames = {
  continue_story: "Continuation search",
  full_original: "Full-original search",
  original_source: "Source search",
  other_copies: "Copy search",
  identify_shown: "Identification search"
};

function validPublicURL(raw) {
  try {
    const url = new URL(raw.trim());
    return ["http:", "https:"].includes(url.protocol) ? url.toString() : null;
  } catch { return null; }
}

function needsSocialClue(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host.includes("instagram.com") || host.includes("facebook.com") || host === "fb.watch";
  } catch { return false; }
}

function updateClueVisibility() {
  const show = needsSocialClue(ui.url.value);
  ui.clueGroup.hidden = !show;
}

async function checkService() {
  try {
    const [health, capabilities] = await Promise.all([
      fetch("/health", { cache: "no-store" }),
      fetch("/v1/capabilities", { cache: "no-store" })
    ]);
    if (!health.ok) throw new Error();
    const caps = capabilities.ok ? await capabilities.json() : {};
    ui.dot.className = "status-dot online";
    ui.status.textContent = caps.youtube_search ? "Service live • YouTube connected" : "Service live";
  } catch {
    ui.dot.className = "status-dot offline";
    ui.status.textContent = "Service is waking—try again shortly";
  }
}

function setBusy(busy) {
  ui.search.disabled = busy;
  ui.url.disabled = busy;
  ui.intent.disabled = busy;
  ui.clue.disabled = busy;
  ui.label.textContent = busy ? "Searching public sources…" : "Find the Rest";
  ui.note.textContent = busy
    ? "The free service may need up to a minute to wake. Keep this page open."
    : "Public sources only. Private content is never bypassed.";
}

function addCandidate(candidate) {
  const link = document.createElement("a");
  link.className = "candidate";
  link.href = candidate.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  const title = document.createElement("strong");
  title.textContent = candidate.title || "Public match";
  const score = document.createElement("span");
  score.textContent = `${Math.round((candidate.score || 0) * 100)}% ↗`;
  link.append(title, score);
  ui.others.append(link);
}

function showResult(data) {
  const confidence = Math.max(0, Math.min(1, Number(data.confidence) || 0));
  ui.kicker.textContent = intentNames[data.search_intent] || "SEARCH RESULT";
  ui.resultTitle.textContent = data.best_match ? "A likely match" : "Search complete";
  ui.resultMessage.textContent = data.result_message || (data.best_match
    ? "This public result has the strongest available evidence."
    : "No credible public match was verified yet.");
  ui.confidenceRow.hidden = confidence <= 0;
  ui.confidenceNumber.textContent = `${Math.round(confidence * 100)}%`;
  requestAnimationFrame(() => { ui.confidenceFill.style.width = `${Math.round(confidence * 100)}%`; });

  ui.best.hidden = !data.best_match;
  ui.others.replaceChildren();
  if (data.best_match) {
    const best = data.best_match;
    ui.matchTitle.textContent = best.title || "Best public match";
    ui.matchDetail.textContent = [best.creator, best.platform, best.reason].filter(Boolean).join(" • ");
    ui.matchLink.href = best.url;
    (data.candidates || []).filter((c) => c.url !== best.url).slice(0, 3).forEach(addCandidate);
  }
  ui.result.hidden = false;
  ui.result.scrollIntoView({ behavior: "smooth", block: "start" });
}

function showError(message) {
  ui.kicker.textContent = "COULDN’T COMPLETE SEARCH";
  ui.resultTitle.textContent = "Let’s try that again";
  ui.resultMessage.textContent = message;
  ui.confidenceRow.hidden = true;
  ui.best.hidden = true;
  ui.others.replaceChildren();
  ui.result.hidden = false;
  ui.result.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function search() {
  const url = validPublicURL(ui.url.value);
  if (!url) {
    ui.url.focus();
    ui.note.textContent = "Paste a complete public link beginning with https://";
    return;
  }
  const social = needsSocialClue(url);
  const clue = ui.clue.value.trim();
  if (social && clue.length < 8) {
    ui.clueGroup.hidden = false;
    ui.clue.focus();
    ui.note.textContent = "Paste the post caption or briefly describe the video so I know what to search for.";
    return;
  }
  setBusy(true);
  ui.result.hidden = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120000);
  try {
    const endpoint = social ? "/v1/analyze-clues" : "/v1/analyze";
    const requestBody = { url, scope: "web", intent: ui.intent.value };
    if (social) requestBody.visible_text = clue;
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
      signal: controller.signal
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `The service returned error ${response.status}.`);
    showResult(data);
  } catch (error) {
    const message = error.name === "AbortError"
      ? "The search took too long. The free server may still be waking—wait a moment and try again."
      : (error.message || "The service could not be reached. Try again in a moment.");
    showError(message);
  } finally {
    clearTimeout(timeout);
    setBusy(false);
  }
}

ui.search.addEventListener("click", search);
ui.url.addEventListener("keydown", (event) => { if (event.key === "Enter") search(); });
ui.url.addEventListener("input", updateClueVisibility);
ui.paste.addEventListener("click", async () => {
  try {
    ui.url.value = await navigator.clipboard.readText();
    updateClueVisibility();
    ui.url.focus();
  } catch {
    ui.url.focus();
    ui.note.textContent = "Touch and hold in the link box, then choose Paste.";
  }
});
ui.again.addEventListener("click", () => {
  ui.result.hidden = true;
  ui.url.value = "";
  ui.clue.value = "";
  updateClueVisibility();
  ui.url.focus();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

checkService();
