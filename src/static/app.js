const messagesEl = document.getElementById('messages');
const form = document.getElementById('chat-form');
const input = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const resetBtn = document.getElementById('reset-btn');
const providerBadge = document.getElementById('provider-badge');
const runBadge = document.getElementById('run-badge');
const caseSearch = document.getElementById('case-search');
const platformFilter = document.getElementById('platform-filter');
const statusFilter = document.getElementById('status-filter');
const severityFilter = document.getElementById('severity-filter');
const ticketFilter = document.getElementById('ticket-filter');
const caseResults = document.getElementById('case-results');
const resultsCount = document.getElementById('results-count');
const scenarioList = document.getElementById('scenario-list');
const contextEmpty = document.getElementById('context-empty');
const contextChip = document.getElementById('context-chip');
const clearContextBtn = document.getElementById('clear-context');
const quickActions = document.getElementById('quick-actions');
const runSummary = document.getElementById('run-summary');
const agentMap = document.getElementById('agent-map');

let selectedCase = null;
let isBusy = false;
let searchTimer = null;

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatText(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

function prettyJson(value) {
  return JSON.stringify(value ?? {}, null, 2);
}

function truncate(value, length = 120) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setBusy(value) {
  isBusy = value;
  sendBtn.disabled = value;
  document.querySelectorAll('[data-prompt], .scenario-btn').forEach((button) => {
    button.disabled = value;
  });
}

function addSystemMessage(text, tone = 'info') {
  const div = document.createElement('div');
  div.className = `system-message ${tone}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function setSelectedCase(testCase) {
  selectedCase = testCase;
  contextEmpty.hidden = Boolean(testCase);
  contextChip.hidden = !testCase;
  clearContextBtn.hidden = !testCase;
  quickActions.hidden = !testCase;

  document.querySelectorAll('.case-card').forEach((card) => {
    card.classList.toggle('selected', Boolean(testCase) && card.dataset.testId === testCase.test_id);
  });

  if (testCase) {
    contextChip.textContent = `${testCase.test_id} · ${testCase.platform} · ${testCase.severity}`;
    input.placeholder = `Hỏi về ${testCase.test_id}…`;
    input.focus();
  } else {
    contextChip.textContent = '';
    input.placeholder = 'Hỏi về test case đang chọn hoặc mô tả lỗi bạn cần tìm…';
  }
}

function buildQueryParams() {
  const params = new URLSearchParams();
  if (caseSearch.value.trim()) params.set('q', caseSearch.value.trim());
  if (platformFilter.value) params.set('platform', platformFilter.value);
  if (statusFilter.value) params.set('run_status', statusFilter.value);
  if (severityFilter.value) params.set('severity', severityFilter.value);
  if (ticketFilter.value) params.set('has_ticket', ticketFilter.value);
  return params;
}

function renderCaseResults(cases) {
  caseResults.replaceChildren();
  resultsCount.textContent = String(cases.length);

  if (!cases.length) {
    const empty = document.createElement('div');
    empty.className = 'catalog-empty';
    empty.textContent = 'Không tìm thấy test case phù hợp.';
    caseResults.appendChild(empty);
    return;
  }

  cases.forEach((testCase) => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'case-card';
    card.dataset.testId = testCase.test_id;
    const ticketLabel = testCase.existing_retest_ticket || 'Chưa có ticket';
    card.innerHTML = `
      <span class="case-topline"><strong>${escapeHtml(testCase.test_id)}</strong><span class="severity severity-${escapeHtml(testCase.severity)}">${escapeHtml(testCase.severity)}</span></span>
      <span class="case-title">${escapeHtml(testCase.title || testCase.failure_category)}</span>
      <span class="case-summary">${escapeHtml(truncate(testCase.failure_summary, 105))}</span>
      <span class="case-meta"><span>${escapeHtml(testCase.platform)}</span><span>${escapeHtml(testCase.run_status)}</span><span>${escapeHtml(ticketLabel)}</span></span>
    `;
    card.addEventListener('click', () => setSelectedCase(testCase));
    caseResults.appendChild(card);
  });

  if (selectedCase) setSelectedCase(selectedCase);
}

async function loadCaseCatalog() {
  caseResults.innerHTML = '<div class="catalog-loading">Đang tìm test case…</div>';
  try {
    const response = await fetch(`/api/qa/test-cases?${buildQueryParams().toString()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderCaseResults(data.results || []);
  } catch (error) {
    caseResults.innerHTML = `<div class="catalog-empty">Không tải được dữ liệu: ${escapeHtml(error.message)}</div>`;
  }
}

function scheduleCatalogReload() {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(loadCaseCatalog, 220);
}

async function loadScenarios() {
  try {
    const response = await fetch('/api/scenarios');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const scenarios = await response.json();
    scenarioList.replaceChildren();
    scenarios.forEach((scenario) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'scenario-btn';
      button.textContent = `${scenario.id} · ${scenario.question}`;
      button.addEventListener('click', () => {
        if (!isBusy) sendMessage(scenario.question, false);
      });
      scenarioList.appendChild(button);
    });
  } catch (error) {
    scenarioList.textContent = 'Không tải được kịch bản demo.';
  }
}

async function loadProviderMeta() {
  try {
    const response = await fetch('/api/meta');
    const meta = await response.json();
    const mode = String(meta.execution_mode || 'unknown').toUpperCase();
    providerBadge.textContent = `${mode} · ${meta.provider} · ${meta.model}`;
    providerBadge.className = `status-badge ${mode === 'LIVE' ? 'status-live' : 'status-mock'}`;
    providerBadge.title = meta.configured_fallback
      ? `Yêu cầu ${meta.requested_provider}, hiện đang chạy ${meta.provider}`
      : `Provider hiện tại: ${meta.provider_class}`;
  } catch (_error) {
    providerBadge.textContent = 'Không đọc được provider';
    providerBadge.className = 'status-badge status-error';
  }
}

function renderObservableResponse(entry) {
  const response = entry.model_response || {};
  const reasoning = entry.model_reasoning;
  const reasoningNote = reasoning
    ? `<div class="public-reasoning"><span>Reasoning công khai từ response</span><p>${formatText(reasoning)}</p></div>`
    : `<div class="reasoning-unavailable">Provider không trả public reasoning ở bước này. Không suy diễn chain-of-thought nội bộ.</div>`;

  return `
    ${reasoningNote}
    <details class="raw-response">
      <summary>Model response quan sát được</summary>
      <pre>${escapeHtml(prettyJson(response))}</pre>
    </details>
    <div class="decision-summary"><span>Decision summary</span><p>${formatText(entry.decision_summary || entry.thought || '')}</p></div>
  `;
}

function renderStepCard(entry, container) {
  const card = document.createElement('article');
  const isFinal = entry.action_type === 'FINAL_ANSWER';
  card.className = `step-card ${isFinal ? 'final' : 'action'}`;
  const totalLatency = entry.total_step_latency_ms ?? entry.latency_ms ?? 0;
  const header = `
    <div class="step-header">
      <span class="step-number">STEP ${escapeHtml(entry.step)}</span>
      <span class="phase-badge ${isFinal ? 'phase-final' : 'phase-action'}">${isFinal ? 'FINAL' : 'TOOL EXECUTION'}</span>
      <span class="latency">${escapeHtml(totalLatency)} ms</span>
    </div>`;

  let execution = '';
  if (isFinal) {
    execution = `<div class="final-answer"><span>Final answer</span><div>${formatText(entry.output || '')}</div></div>`;
  } else {
    execution = `
      <div class="execution-grid">
        <div><span class="block-label action-label">Action</span><pre>${escapeHtml(entry.tool_name)}(${escapeHtml(prettyJson(entry.arguments || {}))})</pre></div>
        <div><span class="block-label observation-label">Observation</span><pre>${escapeHtml(prettyJson(entry.observation || {}))}</pre></div>
      </div>
      <div class="latency-row"><span>LLM ${escapeHtml(entry.llm_latency_ms ?? entry.latency_ms ?? 0)} ms</span><span>Tool ${escapeHtml(entry.tool_latency_ms ?? 0)} ms</span></div>`;
  }

  card.innerHTML = `${header}${renderObservableResponse(entry)}${execution}`;
  container.appendChild(card);
}

function mapNode(kind, title, content, meta = '') {
  const node = document.createElement('div');
  node.className = `map-node map-${kind}`;
  node.innerHTML = `<div class="map-node-head"><span>${escapeHtml(title)}</span>${meta ? `<small>${escapeHtml(meta)}</small>` : ''}</div><p>${formatText(content)}</p>`;
  return node;
}

function mapArrow() {
  const arrow = document.createElement('div');
  arrow.className = 'map-arrow';
  arrow.textContent = '↓';
  return arrow;
}

function appendMapNode(node) {
  if (agentMap.children.length) agentMap.appendChild(mapArrow());
  agentMap.appendChild(node);
}

function renderAgentMap(query, trace, run) {
  agentMap.replaceChildren();
  appendMapNode(mapNode('query', 'User Query', truncate(query, 180), run.run_id));

  trace.forEach((entry) => {
    const publicReasoning = entry.model_reasoning
      ? `Response reasoning: ${truncate(entry.model_reasoning, 110)}\nDecision: ${entry.decision_summary || entry.thought || ''}`
      : `Public reasoning: không được provider cung cấp.\nDecision: ${entry.decision_summary || entry.thought || ''}`;
    appendMapNode(mapNode('decision', `Decision · Step ${entry.step}`, publicReasoning, `${entry.llm_latency_ms ?? entry.latency_ms ?? 0} ms`));

    if (entry.action_type === 'TOOL_EXECUTION') {
      appendMapNode(mapNode('action', 'Action', `${entry.tool_name}(${truncate(prettyJson(entry.arguments || {}), 120)})`));
      const observation = entry.observation || {};
      appendMapNode(mapNode('observation', `Observation · ${observation.status || 'UNKNOWN'}`, truncate(observation.message || prettyJson(observation), 165), `${entry.tool_latency_ms ?? 0} ms`));
    } else {
      appendMapNode(mapNode('final', 'Final Answer', truncate(entry.output, 190)));
    }
  });
}

function renderRunSummary(run) {
  const fallback = run.fallback_used ? '<span class="warning-chip">fallback used</span>' : '';
  runSummary.innerHTML = `
    <div class="run-title"><strong>Run ${escapeHtml(run.run_id)}</strong><span class="run-status">${escapeHtml(run.status)}</span></div>
    <div class="run-metrics"><span>${escapeHtml(run.step_count)} steps</span><span>${escapeHtml(run.duration_ms)} ms</span><span>${escapeHtml(run.execution_mode)}</span>${fallback}</div>
  `;
  runBadge.textContent = `${run.status} · ${run.step_count} steps`;
  runBadge.className = `status-badge ${run.status === 'SUCCESS' ? 'status-success' : 'status-error'}`;
}

async function sendMessage(query, useContext = true) {
  if (isBusy || !query.trim()) return;
  setBusy(true);
  input.value = '';

  const runBlock = document.createElement('section');
  runBlock.className = 'run-block';
  const contextLabel = useContext && selectedCase ? `<span>Context: ${escapeHtml(selectedCase.test_id)}</span>` : '';
  runBlock.innerHTML = `<div class="user-message"><div>${formatText(query)}</div>${contextLabel}</div>`;
  const typing = document.createElement('div');
  typing.className = 'typing';
  typing.innerHTML = '<span></span><span></span><span></span> Agent đang chạy ReAct loop…';
  runBlock.appendChild(typing);
  messagesEl.appendChild(runBlock);
  scrollToBottom();

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        query,
        context: useContext && selectedCase ? {test_id: selectedCase.test_id} : null
      })
    });
    const data = await response.json().catch(() => ({}));
    typing.remove();
    if (!response.ok || data.error) {
      const detail = data.detail ? ` ${data.detail}` : '';
      throw new Error(`${data.error || `HTTP ${response.status}`}${detail}`);
    }

    renderRunSummary(data.run || {});
    (data.trace || []).forEach((entry) => renderStepCard(entry, runBlock));
    renderAgentMap(data.display_query || query, data.trace || [], data.run || {});
    document.querySelector('[data-tab="map-panel"]').click();
    await loadCaseCatalog();
  } catch (error) {
    typing.remove();
    addSystemMessage(`Agent run thất bại: ${error.message}`, 'error');
    runBadge.textContent = 'ERROR';
    runBadge.className = 'status-badge status-error';
  } finally {
    setBusy(false);
    input.focus();
    scrollToBottom();
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  sendMessage(input.value, true);
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    form.requestSubmit();
  }
});

[caseSearch, platformFilter, statusFilter, severityFilter, ticketFilter].forEach((control) => {
  control.addEventListener(control === caseSearch ? 'input' : 'change', scheduleCatalogReload);
});

clearContextBtn.addEventListener('click', () => setSelectedCase(null));

quickActions.addEventListener('click', (event) => {
  const button = event.target.closest('[data-prompt]');
  if (button && !isBusy) sendMessage(button.dataset.prompt, true);
});

document.querySelectorAll('.tab-btn').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach((item) => item.classList.toggle('active', item === button));
    document.querySelectorAll('.tab-panel').forEach((panel) => {
      const active = panel.id === button.dataset.tab;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    });
  });
});

resetBtn.addEventListener('click', async () => {
  if (!window.confirm('Reset toàn bộ test case và ticket mock về trạng thái ban đầu?')) return;
  resetBtn.disabled = true;
  try {
    const response = await fetch('/api/reset', {method: 'POST'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    setSelectedCase(null);
    await loadCaseCatalog();
    addSystemMessage('Đã reset dữ liệu mock về trạng thái ban đầu.', 'success');
  } catch (error) {
    addSystemMessage(`Reset thất bại: ${error.message}`, 'error');
  } finally {
    resetBtn.disabled = false;
  }
});

Promise.all([loadProviderMeta(), loadCaseCatalog(), loadScenarios()]);
