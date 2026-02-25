async function fetchFunding() {
  const res = await fetch('/api/funding?limit=50000');
  if (!res.ok) throw new Error('Failed to load funding data');
  return await res.json();
}
function setMeta(count) {
  document.getElementById('countLabel').textContent = `${count} rows`;
  document.getElementById('updatedLabel').textContent = `Updated: ${new Date().toLocaleString()}`;
}
function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
function renderTable(rows) {
  const tbody = document.getElementById('fundingTbody');
  tbody.innerHTML = '';
  for (const r of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(r['Company'])}</td>
      <td class="mono">${escapeHtml(r['Funding date'])}</td>
      <td>${escapeHtml(r['Funding round'])}</td>
      <td>${escapeHtml(r['Funding amount'])}</td>
      <td>${escapeHtml(r['Investors'])}</td>
      <td>${escapeHtml(r['Description'])}</td>
      <td>${escapeHtml(r['Therapeutic Area'])}</td>
      <td>${escapeHtml(r['Therapeutic Modality'])}</td>
      <td>${escapeHtml(r['Lead Clinical Stage'])}</td>
      <td>${escapeHtml(r['Small molecule modality?'])}</td>
      <td>${escapeHtml(r['HQ City'])}</td>
      <td>${escapeHtml(r['HQ State/Region'])}</td>
    `;
    tbody.appendChild(tr);
  }
}
async function runChat() {
  const input = document.getElementById('chatInput');
  const answerEl = document.getElementById('chatAnswer');
  const q = input.value.trim();
  if (!q) return;
  answerEl.textContent = 'Thinking…';
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query: q})
  });
  if (!res.ok) {
    answerEl.textContent = 'Error running query.';
    return;
  }
  const data = await res.json();
  answerEl.textContent = data.answer || '';
  renderTable(data.rows || []);
  setMeta(data.count || 0);
}
async function refresh() {
  const data = await fetchFunding();
  renderTable(data.rows || []);
  setMeta(data.count || 0);
  document.getElementById('chatAnswer').textContent = '';
}
window.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('chatSend').addEventListener('click', runChat);
  document.getElementById('refreshBtn').addEventListener('click', refresh);
  document.getElementById('chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runChat();
  });
  await refresh();
});
