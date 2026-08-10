let currentResults = null;
let isProcessing = false;
let abortController = null;
let streamedResults = [];
let checkFinished = false;
let currentTheme = localStorage.getItem('theme') || 'light';
let currentFilter = 'all';

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  currentTheme = theme;
  localStorage.setItem('theme', theme);
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19';
}
function toggleTheme() { applyTheme(currentTheme === 'light' ? 'dark' : 'light'); }

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
  document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
  document.querySelector('[data-tab="' + tab + '"]').classList.add('active');
  document.getElementById('tab-' + tab).classList.add('active');
  if (tab === 'history') loadHistory();
  if (tab === 'dashboard') loadDashboard();
}

function parseCards(raw) {
  var lines = raw.split('\n');
  var cards = [];
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].trim();
    if (!line) continue;
    var cleaned = line
      .replace(/[⭐✨🔹➡➜➜️●•➡️➤»★☆●]/g, '')
      .replace(/𝐂𝐂|CC|cc/gi, '')
      .replace(/[^\d|A-Za-z\s\-/:.@+()]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    var parts = cleaned.split('|');
    var num = '', mm = '', yy = '', cvv = '';
    for (var j = 0; j < parts.length; j++) {
      var p = parts[j].trim();
      if (p.length >= 13 && p.length <= 19 && /^\d+$/.test(p)) { num = p; }
      else if (!mm && /^\d{1,2}$/.test(p) && parseInt(p) >= 1 && parseInt(p) <= 12) { mm = p; }
      else if (!yy && /^\d{2,4}$/.test(p)) { yy = p; }
      else if (num && mm && yy && !cvv && /^\d{3,4}$/.test(p)) { cvv = p; }
    }
    if (num && mm && yy && cvv) {
      cards.push(num + '|' + mm + '|' + yy + '|' + cvv);
    }
  }
  return cards;
}

function startCheck() {
  if (isProcessing) { showToast('Already processing...', 'warning'); return; }
  var input = document.getElementById('cardInput');
  var raw = input.value;
  var cards = parseCards(raw);
  if (cards.length === 0) { showToast('No valid cards found! Format: number|mm|yy|cvv', 'error'); return; }
  input.value = cards.join('\n');
  showToast('Parsed ' + cards.length + ' cards from input', 'success');
  isProcessing = true;
  abortController = new AbortController();
  streamedResults = [];
  checkFinished = false;
  currentFilter = 'all';
  document.querySelectorAll('.filter-btn').forEach(function(btn) {
    btn.classList.remove('active');
    if (btn.getAttribute('data-filter') === 'all') btn.classList.add('active');
  });
  document.getElementById('checkingBar').classList.add('active');
  document.getElementById('checkBtn').style.display = 'none';
  document.getElementById('statsContainer').style.display = 'block';
  document.getElementById('resultsContainer').style.display = 'block';
  document.getElementById('resultsBody').innerHTML = '';
  document.getElementById('resultMeta').textContent = 'Checking...';
  updateProgress(0, cards.length);
  var gateway = document.getElementById('gatewaySelect').value;
  var amount = parseFloat(document.getElementById('amountInput').value) || 1;
  var stripeVersion = parseInt(document.getElementById('stripeVersionSelect').value) || 1;
  var proxy = document.getElementById('proxyInput').value.trim() || null;
  var shopifySite = document.getElementById('shopifySiteInput').value.trim() || null;
  var autoRetry = document.getElementById('autoRetryCheckbox').checked;
  var parallel = document.getElementById('parallelCheckbox').checked;

  fetch('/api/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      cards: cards, gateway: gateway, amount: amount, stripe_version: stripeVersion,
      proxy: proxy, shopify_site: shopifySite, auto_retry: autoRetry, parallel: parallel
    }),
    signal: abortController.signal
  }).then(function(response) {
    if (!response.ok) { showToast('Server error: ' + response.status, 'error'); finishCheck(); return; }
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    function read() {
      reader.read().then(function(result) {
        if (result.done) { finishCheck(); return; }
        buffer += decoder.decode(result.value, { stream: true });
        var lines = buffer.split('\n');
        buffer = lines.pop();
        for (var i = 0; i < lines.length; i++) {
          if (lines[i].startsWith('data: ')) {
            try {
              var data = JSON.parse(lines[i].substring(6));
              if (data.type === 'done') { finishCheck(data); }
              else {
                streamedResults.push(data);
                appendResultRow(data, streamedResults.length);
                updateProgress(streamedResults.length, cards.length);
                updateLiveStats();
              }
            } catch(e) {}
          }
        }
        read();
      }).catch(function(err) {
        if (err.name === 'AbortError') { showToast('Check cancelled', 'warning'); }
        else { showToast('Error: ' + err.message, 'error'); }
        finishCheck();
      });
    }
    read();
  }).catch(function(error) {
    if (error.name === 'AbortError') { showToast('Check cancelled', 'warning'); }
    else { showToast('Error: ' + error.message, 'error'); }
    finishCheck();
  });
}

function finishCheck(summary) {
  if (checkFinished) return;
  checkFinished = true;
  isProcessing = false;
  abortController = null;
  document.getElementById('checkingBar').classList.remove('active');
  document.getElementById('checkBtn').style.display = 'inline-flex';
  if (summary) {
    document.getElementById('resultMeta').textContent = 'Done in ' + summary.time_taken + 's';
    currentResults = { results: streamedResults };
    for (var k in summary) currentResults[k] = summary[k];
  } else {
    document.getElementById('resultMeta').textContent = 'Cancelled';
    currentResults = { results: streamedResults };
  }
}

function getFlagEmoji(cc) {
  if (!cc || cc.length !== 2) return '';
  return String.fromCodePoint.apply(null, cc.toUpperCase().split('').map(function(c) { return 127397 + c.charCodeAt(0); }));
}

function copyCard(el, fullCard) {
  navigator.clipboard.writeText(fullCard).then(function() {
    showToast('Copied: ' + fullCard, 'success');
  }).catch(function() {
    var ta = document.createElement('textarea');
    ta.value = fullCard;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('Copied: ' + fullCard, 'success');
  });
}

function filterResults(filter) {
  currentFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(function(btn) {
    btn.classList.remove('active');
    if (btn.getAttribute('data-filter') === filter) btn.classList.add('active');
  });
  var rows = document.querySelectorAll('#resultsBody tr');
  var shown = 0;
  for (var i = 0; i < rows.length; i++) {
    var rowStatus = rows[i].getAttribute('data-status');
    if (filter === 'all' || rowStatus === filter) {
      rows[i].style.display = '';
      shown++;
    } else {
      rows[i].style.display = 'none';
    }
  }
  document.getElementById('filterCount').textContent = shown + ' / ' + rows.length;
}

function appendResultRow(r, i) {
  var tbody = document.getElementById('resultsBody');
  var gatewayHtml = '';
  if (r.results && Object.keys(r.results).length > 0) {
    gatewayHtml = '<div class="gateway-grid">';
    var gateways = Object.keys(r.results).sort();
    for (var g = 0; g < gateways.length; g++) {
      var gw = gateways[g];
      var res = r.results[gw];
      var status = res.status || 'error';
      var isBest = gw === r.best_gateway;
      var sd = status === 'charged' ? 'V' : status === 'live' ? 'O' : status === 'ccn' ? '!' : 'X';
      var vi = res.stripe_version ? ' v' + res.stripe_version : '';
      gatewayHtml += '<div class="gateway-result ' + status + (isBest ? ' best' : '') + '">' +
        '<div class="gw-name">' + gw.substring(0, 6) + vi + (isBest ? ' BEST' : '') + '</div>' +
        '<div class="gw-status">' + sd + '</div></div>';
    }
    gatewayHtml += '</div>';
  }
  var sh = '<div class="gateway-summary"><span class="gw-summary-badge charged">V ' + (r.charged_count || 0) + '</span>' +
    '<span class="gw-summary-badge live">O ' + (r.live_count || 0) + '</span></div>';
  var sc = 'status-' + (r.best_status || 'unknown');
  var sl = r.best_status ? r.best_status.toUpperCase() : 'UNKNOWN';
  var nc = (r.card_type || '').toLowerCase().replace(/[^a-z]/g, '');
  var bi = r.bin_info || {};
  var cf = bi.country_code ? getFlagEmoji(bi.country_code) : '';
  var binHtml = '<div class="bin-info"><div class="bin-country">' + cf + ' ' + (bi.country || 'Unknown') + '</div>' +
    '<div class="bin-bank">' + (bi.bank || '') + '</div></div>';
  var rowStatus = r.best_status || 'error';
  var fullCard = r.full_card || '';
  var exp = (r.exp_month || '') + '/' + (r.exp_year || '');
  var cvv = r.cvv || '';
  var displayCard = fullCard || r.card_number || '';
  var tr = document.createElement('tr');
  tr.setAttribute('data-status', rowStatus);
  tr.innerHTML = '<td>' + i + '</td>' +
    '<td><div class="card-info"><span class="card-number" title="Click to copy" onclick="copyCard(this,\'' + displayCard + '|' + exp + '|' + cvv + '\')">' + displayCard + '</span>' +
    '<span class="card-type-badge ' + nc + '">' + (r.card_brand || r.card_type || 'N/A') + '</span>' +
    '<div class="card-detail"><span class="card-exp">Exp: ' + exp + '</span> <span class="card-cvv">CVV: ' + cvv + '</span></div></div></td>' +
    '<td>' + binHtml + '</td>' +
    '<td>' + gatewayHtml + '</td>' +
    '<td>' + sh + '</td>' +
    '<td><span class="status-badge ' + sc + '">' + sl + '</span></td>' +
    '<td><span class="best-gateway-badge">' + (r.best_gateway || 'N/A') + '</span></td>';
  tbody.appendChild(tr);
  if (currentFilter !== 'all' && rowStatus !== currentFilter) {
    tr.style.display = 'none';
  }
}

function updateLiveStats() {
  var charged = 0, live = 0, dead = 0, ccn = 0, err = 0, totalAmount = 0;
  for (var i = 0; i < streamedResults.length; i++) {
    var s = streamedResults[i].best_status || 'error';
    if (s === 'charged') { charged++; totalAmount += streamedResults[i].amount || 0; }
    else if (s === 'live') live++;
    else if (s === 'dead') dead++;
    else if (s === 'ccn') ccn++;
    else err++;
  }
  document.getElementById('totalCount').textContent = streamedResults.length;
  document.getElementById('chargedCount').textContent = charged;
  document.getElementById('liveCount').textContent = live;
  document.getElementById('deadCount').textContent = dead;
  document.getElementById('ccnCount').textContent = ccn;
  document.getElementById('chargedAmount').textContent = '$' + totalAmount.toFixed(2);
  var statsEl = document.getElementById('checkingStats');
  if (statsEl) statsEl.textContent = 'V:' + charged + ' O:' + live + ' X:' + dead + ' !:' + ccn;
  updateCharts();
  var rows = document.querySelectorAll('#resultsBody tr');
  var visibleCount = 0;
  for (var j = 0; j < rows.length; j++) {
    if (rows[j].style.display !== 'none') visibleCount++;
  }
  var fc = document.getElementById('filterCount');
  if (fc) fc.textContent = visibleCount + ' / ' + rows.length;
}

function updateCharts() {
  var counts = { charged: 0, live: 0, dead: 0, ccn: 0, error: 0 };
  var total = streamedResults.length || 1;
  for (var i = 0; i < streamedResults.length; i++) {
    var s = streamedResults[i].best_status || 'error';
    if (counts[s] !== undefined) counts[s]++;
  }
  var keys = ['charged', 'live', 'dead', 'ccn', 'error'];
  for (var k = 0; k < keys.length; k++) {
    var pct = Math.round((counts[keys[k]] / total) * 100);
    var bar = document.getElementById('chart-' + keys[k]);
    if (bar) { bar.style.width = pct + '%'; bar.textContent = pct > 5 ? pct + '%' : ''; }
    var label = document.getElementById('chart-' + keys[k] + '-count');
    if (label) label.textContent = counts[keys[k]];
  }
}

function stopCheck() { if (abortController) abortController.abort(); }
function updateProgress(current, total) {
  document.getElementById('checkingProgress').textContent = current + ' / ' + total;
  document.getElementById('checkingBarFill').style.width = (current / total * 100) + '%';
}

function loadSample() {
  document.getElementById('cardInput').value = '4111111111111111|12|26|123\n5555555555554444|06|27|456\n378282246310005|09|25|789\n6011111111111117|11|28|234\n3530111333300000|10|27|567';
  showToast('Sample cards loaded!', 'success');
}
function clearAll() {
  document.getElementById('cardInput').value = '';
  document.getElementById('statsContainer').style.display = 'none';
  document.getElementById('resultsContainer').style.display = 'none';
  document.getElementById('resultsBody').innerHTML = '';
  document.getElementById('chargedAmount').textContent = '$0.00';
  document.getElementById('filterCount').textContent = '';
  currentResults = null;
  streamedResults = [];
  currentFilter = 'all';
  document.querySelectorAll('.filter-btn').forEach(function(btn) {
    btn.classList.remove('active');
    if (btn.getAttribute('data-filter') === 'all') btn.classList.add('active');
  });
  showToast('Cleared', 'info');
}

function exportResults(format) {
  if (!currentResults) { showToast('No results to export!', 'error'); return; }
  var content = '', type = '', ext = '';
  if (format === 'json') {
    content = JSON.stringify(currentResults, null, 2);
    type = 'application/json'; ext = 'json';
  } else {
    var rows = currentResults.results || [];
    var csv = 'Card Number,Expiry,CVV,Type,Brand,Country,Bank,Best Gateway,Best Status,Stripe,Razorpay,Adyen,PayPal,Shopify\n';
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var bi = r.bin_info || {};
      csv += (r.full_card||'') + ',' + (r.exp_month||'') + '/' + (r.exp_year||'') + ',' + (r.cvv||'') + ',' +
        (r.card_type||'') + ',' + (r.card_brand||'') + ',' + (bi.country||'') + ',' + (bi.bank||'') + ',' +
        (r.best_gateway||'') + ',' + (r.best_status||'') + ',' +
        ((r.results&&r.results.stripe)?r.results.stripe.status:'') + ',' +
        ((r.results&&r.results.razorpay)?r.results.razorpay.status:'') + ',' +
        ((r.results&&r.results.adyen)?r.results.adyen.status:'') + ',' +
        ((r.results&&r.results.paypal)?r.results.paypal.status:'') + ',' +
        ((r.results&&r.results.shopify)?r.results.shopify.status:'') + '\n';
    }
    content = csv; type = 'text/csv'; ext = 'csv';
  }
  var blob = new Blob([content], { type: type + ';charset=utf-8;' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'cc_check_' + new Date().toISOString().slice(0,10) + '.' + ext;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(ext.toUpperCase() + ' exported!', 'success');
}

function showToast(message, type) {
  var container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(function() {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(function() { toast.remove(); }, 300);
  }, 4000);
}

function generateCards() {
  var count = parseInt(document.getElementById('genCount').value) || 10;
  var network = document.getElementById('genNetwork').value;
  fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ count: count, network: network })
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.cards) {
      var grid = document.getElementById('genGrid');
      grid.innerHTML = '';
      var textLines = [];
      for (var i = 0; i < data.cards.length; i++) {
        var card = data.cards[i];
        var div = document.createElement('div');
        div.className = 'gen-card';
        div.textContent = card.card;
        div.onclick = function() {
          var ta = document.getElementById('cardInput');
          ta.value += (ta.value ? '\n' : '') + this.textContent;
          showToast('Card added to input!', 'success');
        };
        grid.appendChild(div);
        textLines.push(card.card);
      }
      document.getElementById('genOutput').value = textLines.join('\n');
      showToast('Generated ' + data.cards.length + ' cards!', 'success');
    }
  }).catch(function(e) { showToast('Error: ' + e.message, 'error'); });
}

function copyGenerated() {
  var output = document.getElementById('genOutput');
  output.select();
  document.execCommand('copy');
  showToast('Copied to clipboard!', 'success');
}

function loadHistory() {
  fetch('/api/history').then(function(r) { return r.json(); }).then(function(data) {
    var container = document.getElementById('historyList');
    if (!data.sessions || data.sessions.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No check history yet</p></div>';
      return;
    }
    var html = '';
    for (var i = 0; i < data.sessions.length; i++) {
      var s = data.sessions[i];
      var date = new Date(s.started_at).toLocaleString();
      html += '<div class="history-item" onclick="viewHistory(' + s.id + ')">' +
        '<div class="history-header"><span class="history-date">' + date + '</span>' +
        '<span class="small text-muted">#' + s.id + ' | ' + s.gateway + '</span></div>' +
        '<div class="history-stats">' +
        '<span class="history-stat">Total: ' + s.total_cards + '</span>' +
        '<span class="history-stat charged">V: ' + s.charged + '</span>' +
        '<span class="history-stat live">O: ' + s.live + '</span>' +
        '<span class="history-stat dead">X: ' + s.dead + '</span>' +
        '<span class="history-stat ccn">!: ' + s.ccn + '</span>' +
        '<span class="small text-muted">' + (s.time_taken || 0).toFixed(1) + 's</span>' +
        '</div></div>';
    }
    container.innerHTML = html;
  }).catch(function(e) { showToast('Error loading history', 'error'); });
}

function viewHistory(id) {
  fetch('/api/history/' + id).then(function(r) { return r.json(); }).then(function(data) {
    if (data.results) {
      switchTab('check');
      streamedResults = [];
      document.getElementById('statsContainer').style.display = 'block';
      document.getElementById('resultsContainer').style.display = 'block';
      document.getElementById('resultsBody').innerHTML = '';
      for (var i = 0; i < data.results.length; i++) {
        var r = data.results[i];
        var fakeResult = {
          card_number: r.card_number, full_card: r.full_card,
          exp_month: r.exp_month, exp_year: r.exp_year, cvv: r.cvv,
          card_type: r.card_type, card_brand: r.card_brand,
          best_gateway: r.best_gateway, best_status: r.best_status,
          charged_count: r.charged_count, live_count: r.live_count, amount: r.amount,
          results: r.gateway_results || {},
          bin_info: { country: r.bin_country, bank: r.bin_bank, network: r.bin_network, country_code: '' }
        };
        streamedResults.push(fakeResult);
        appendResultRow(fakeResult, i + 1);
      }
      updateLiveStats();
      showToast('Loaded session #' + id, 'info');
    }
  }).catch(function(e) { showToast('Error loading session', 'error'); });
}

function loadDashboard() {
  fetch('/api/stats').then(function(r) { return r.json(); }).then(function(data) {
    var el = document.getElementById('dashboardContent');
    var html = '<div class="stats-grid">' +
      '<div class="stat-card total"><div class="stat-number">' + data.total_sessions + '</div><div class="stat-label">Sessions</div></div>' +
      '<div class="stat-card"><div class="stat-number">' + data.total_cards_checked + '</div><div class="stat-label">Cards Checked</div></div>' +
      '<div class="stat-card charged"><div class="stat-number">' + data.total_charged + '</div><div class="stat-label">Total Charged</div></div>' +
      '<div class="stat-card live"><div class="stat-number">' + data.total_live + '</div><div class="stat-label">Total Live</div></div>' +
      '<div class="stat-card dead"><div class="stat-number">' + data.total_dead + '</div><div class="stat-label">Total Dead</div></div>' +
      '</div>';
    if (data.recent_sessions && data.recent_sessions.length > 0) {
      html += '<h6 style="margin:15px 0 10px;color:var(--text-secondary);">Recent Sessions</h6>';
      for (var i = 0; i < data.recent_sessions.length; i++) {
        var s = data.recent_sessions[i];
        html += '<div class="history-item"><div class="history-header"><span class="history-date">' +
          new Date(s.started_at).toLocaleString() + '</span></div><div class="history-stats">' +
          '<span class="history-stat">Total: ' + (s.total_cards||0) + '</span>' +
          '<span class="history-stat charged">V: ' + s.charged + '</span>' +
          '<span class="history-stat dead">X: ' + s.dead + '</span></div></div>';
      }
    }
    el.innerHTML = html;
  }).catch(function(e) { document.getElementById('dashboardContent').innerHTML = '<p>Error loading dashboard</p>'; });
}

function loadProxies() {
  fetch('/api/proxies').then(function(r) { return r.json(); }).then(function(data) {
    var el = document.getElementById('proxyList');
    if (!data.proxies || data.proxies.length === 0) {
      el.innerHTML = '<div class="empty-state"><p>No proxies loaded</p></div>';
      return;
    }
    var html = '';
    for (var i = 0; i < data.proxies.length; i++) {
      html += '<div class="proxy-item"><span class="proxy-text">' + data.proxies[i] + '</span>' +
        '<button class="btn btn-danger btn-sm" onclick="removeProxy(\'' + data.proxies[i] + '\')">X</button></div>';
    }
    el.innerHTML = html;
  });
}

function addProxies() {
  var input = document.getElementById('proxyInputArea');
  var proxies = input.value.split('\n').filter(function(p) { return p.trim(); });
  if (proxies.length === 0) { showToast('Enter proxies first', 'warning'); return; }
  fetch('/api/proxies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ proxies: proxies })
  }).then(function(r) { return r.json(); }).then(function(data) {
    showToast('Added ' + (data.added || 0) + ' proxies', 'success');
    input.value = '';
    loadProxies();
  });
}

function removeProxy(proxy) {
  fetch('/api/proxies/' + encodeURIComponent(proxy), { method: 'DELETE' })
    .then(function() { loadProxies(); showToast('Proxy removed', 'info'); });
}

document.addEventListener('DOMContentLoaded', function() {
  applyTheme(currentTheme);
  var dropZone = document.getElementById('dropZone');
  if (dropZone) {
    dropZone.addEventListener('dragover', function(e) { e.preventDefault(); dropZone.classList.add('dragover'); });
    dropZone.addEventListener('dragleave', function() { dropZone.classList.remove('dragover'); });
    dropZone.addEventListener('drop', function(e) {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      var file = e.dataTransfer.files[0];
      if (file) {
        var reader = new FileReader();
        reader.onload = function(ev) {
          var raw = ev.target.result;
          var cards = parseCards(raw);
          document.getElementById('cardInput').value = cards.join('\n');
          showToast('File ' + file.name + ' loaded! Parsed ' + cards.length + ' cards', 'success');
        };
        reader.readAsText(file);
      }
    });
    dropZone.addEventListener('click', function() {
      var input = document.createElement('input');
      input.type = 'file'; input.accept = '.txt,.csv';
      input.onchange = function(e) {
        if (e.target.files.length > 0) {
          var reader = new FileReader();
          reader.onload = function(ev) {
            var raw = ev.target.result;
            var cards = parseCards(raw);
            document.getElementById('cardInput').value = cards.join('\n');
            showToast('File loaded! Parsed ' + cards.length + ' cards', 'success');
          };
          reader.readAsText(e.target.files[0]);
        }
      };
      input.click();
    });
  }
});

document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); startCheck(); }
});
