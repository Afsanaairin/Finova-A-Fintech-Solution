'use strict';
let DATA = null;
let selectedAnomaly = null;
let anomalyFilter = 'all';
let clientSessionVersion = 0;
let initialLayoutHTML = null;
const pendingRequests = new Set();
const SESSION_ENDED_MESSAGE = 'This session has ended.';
const LOGOUT_EVENT_KEY = 'finova_logout';
const $ = id => document.getElementById(id);
const fmt = x => '$' + Math.abs(Number(x||0)).toLocaleString('en-US',{minimumFractionDigits:0,maximumFractionDigits:0});
const signed = x => (Number(x)<0 ? '−' : '') + fmt(x);
const text = (id,value) => {$(id).textContent = String(value)};
const friendlyMonth = iso => new Date(iso+'-01T00:00:00').toLocaleString('en-US',{month:'short',year:'numeric'});
const escapeHTML = value => String(value??'').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
function notify(message, bad=false) { if(message===SESSION_ENDED_MESSAGE)return;const box=$('alert');box.textContent=message;box.classList.remove('hidden');box.classList.toggle('error',bad);setTimeout(()=>box.classList.add('hidden'),7000);}
const pageInfo = {anomalies:['Anomaly Explorer','Find what changed. Understand why it matters.','Evidence-backed cost and invoice investigations.'],overview:['Overview','A clearer picture of your business.','From transactions to foresight. Understand what changed, what matters, and what comes next.'],forecast:['Forecast & Scenarios','Plan for what comes next.','Explore the cash implications of tomorrow’s decisions.'],subscriptions:['Subscriptions','Make every recurring dollar count.','Understand recurring expenses and price changes.'],transactions:['Transactions','Your money, line by line.','Transparent transaction analysis with an audit trail.'],wrapped:['Business Wrapped','Your financial story, reimagined.','FINOVA turns numbers into a meaningful business recap.']};
function switchPage(id){
 document.querySelectorAll('.page').forEach(el=>el.classList.toggle('hidden',el.id!==id));
 document.querySelectorAll('.nav-link').forEach(el=>el.classList.toggle('active',el.dataset.view===id));
 const [name,title,sub] = pageInfo[id];text('page-crumb',name);text('page-title',title);text('page-subtitle',sub);
 if(id==='overview'||id==='forecast') requestAnimationFrame(drawCharts);
 window.scrollTo({top:0,behavior:'smooth'});
}
async function getJSON(url, options) {
  const controller = new AbortController();
  const version = clientSessionVersion;
  pendingRequests.add(controller);
  try {
    const response = await fetch(url, {...options, cache: 'no-store', signal: controller.signal});
    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error('Server returned a non-JSON response.');
    }
    if (version !== clientSessionVersion) throw new Error(SESSION_ENDED_MESSAGE);
    if (!response.ok) {
      const error = new Error(payload.error || 'Request failed');
      error.status = response.status;
      error.retryAfter = Number(payload.retry_after || response.headers.get('Retry-After') || 0);
      throw error;
    }
    return payload;
  } catch (error) {
    if (controller.signal.aborted || version !== clientSessionVersion) {
      const cancelled = new Error(SESSION_ENDED_MESSAGE);
      cancelled.name = 'AbortError';
      throw cancelled;
    }
    throw error;
  } finally {
    pendingRequests.delete(controller);
  }
}

let authBusy = false;
let loginEmail = '';
const resendAvailableByEmail = new Map();
let resendTimer = null;

function emailCooldownKey(email) {
  const value = email.trim();
  const at = value.lastIndexOf('@');
  if (at < 0) return value;
  return value.slice(0, at + 1) + value.slice(at + 1).toLowerCase();
}

function getResendAvailableAt(email) {
  return resendAvailableByEmail.get(emailCooldownKey(email)) || 0;
}

function renderAuth(user) {
  $('login-btn').classList.toggle('hidden', Boolean(user));
  $('logout-btn').classList.toggle('hidden', !user);
  $('user-email').classList.toggle('hidden', !user);
  $('user-email').textContent = user ? user.email : '';
  $('user-email').title = user ? user.email : '';
}

function loginMessage(message, bad = false) {
  $('login-message').textContent = message;
  $('login-message').classList.toggle('error', bad);
}

function updateAuthControls() {
  const availableAt = getResendAvailableAt($('login-email').value);
  const seconds = Math.max(0, Math.ceil((availableAt - Date.now()) / 1000));
  $('send-code-btn').disabled = authBusy || seconds > 0;
  $('send-code-btn').textContent = authBusy ? 'Please wait...' : seconds > 0
    ? `Resend in ${seconds}s` : loginEmail ? 'Resend login code' : 'Send login code';
  $('verify-code-btn').disabled = authBusy;
  $('verify-code-btn').textContent = authBusy ? 'Please wait...' : 'Log in';
  $('login-email').disabled = authBusy;
  $('login-code').disabled = authBusy;
  if (seconds > 0 && resendTimer === null) {
    resendTimer = setInterval(updateAuthControls, 1000);
  }
  if (!seconds && resendTimer !== null) {
    clearInterval(resendTimer);
    resendTimer = null;
  }
}

function startResendCooldown(email, seconds) {
  const duration = Number(seconds);
  if (!Number.isFinite(duration) || duration <= 0) return;
  resendAvailableByEmail.set(emailCooldownKey(email), Date.now() + duration * 1000);
  updateAuthControls();
}

function returnToInitialState(broadcast = false) {
  // Discard late responses before clearing any user-specific state.
  clientSessionVersion += 1;
  pendingRequests.forEach(controller => controller.abort());
  pendingRequests.clear();
  DATA = null;
  selectedAnomaly = null;
  anomalyFilter = 'all';
  loginEmail = '';
  authBusy = false;
  resendAvailableByEmail.clear();
  if (resendTimer !== null) clearInterval(resendTimer);
  resendTimer = null;
  window.FINOVAStory.reset();
  const layout = document.querySelector('.layout');
  if (layout && initialLayoutHTML !== null) layout.innerHTML = initialLayoutHTML;
  $('login-dialog').close();
  $('login-email').value = '';
  $('login-code').value = '';
  $('verify-code-form').classList.add('hidden');
  loginMessage('');
  renderAuth(null);
  updateAuthControls();
  if (broadcast) {
    try {
      // Share only an event timestamp, never the user's email or financial data.
      window.localStorage.setItem(LOGOUT_EVENT_KEY, String(Date.now()));
    } catch {
      // Logout still succeeds when browser storage is unavailable.
    }
  }
  window.location.replace('/');
}

async function refreshAuth() {
  try {
    const result = await getJSON('/api/auth/me');
    renderAuth(result.user);
  } catch (error) {
    notify(error.message, true);
  }
}

function initAuth() {
  if (initialLayoutHTML === null) {
    initialLayoutHTML = document.querySelector('.layout').innerHTML;
  }
  window.addEventListener('storage', event => {
    if (event.key === LOGOUT_EVENT_KEY && event.newValue !== null) returnToInitialState();
  });
  window.addEventListener('pageshow', event => {
    if (event.persisted) returnToInitialState();
  });
  const dialog = $('login-dialog');
  $('login-btn').addEventListener('click', () => {
    updateAuthControls();
    dialog.showModal();
    (loginEmail ? $('login-code') : $('login-email')).focus();
  });
  $('close-login-btn').addEventListener('click', () => dialog.close());
  $('login-email').addEventListener('input', () => {
    if ($('login-email').value.trim() !== loginEmail) {
      loginEmail = '';
      $('verify-code-form').classList.add('hidden');
      $('login-code').value = '';
      loginMessage('');
    }
    updateAuthControls();
  });
  $('send-code-form').addEventListener('submit', async event => {
    event.preventDefault();
    const email = $('login-email').value.trim();
    if (authBusy || Date.now() < getResendAvailableAt(email)) return;
    authBusy = true;
    updateAuthControls();
    loginMessage('Sending your login code...');
    try {
      const result = await getJSON('/api/auth/send-code', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email})
      });
      loginEmail = email;
      $('login-code').value = '';
      $('verify-code-form').classList.remove('hidden');
      loginMessage(result.message || 'Code sent. Check your inbox and spam folder.');
      startResendCooldown(email, result.retry_after || 60);
    } catch (error) {
      loginMessage(error.message, true);
      startResendCooldown(email, error.retryAfter);
    } finally {
      authBusy = false;
      updateAuthControls();
      if (loginEmail && dialog.open) $('login-code').focus();
    }
  });
  $('verify-code-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (authBusy || !loginEmail) return;
    authBusy = true;
    updateAuthControls();
    loginMessage('Verifying your code...');
    try {
      const result = await getJSON('/api/auth/verify-code', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email: loginEmail, code: $('login-code').value.trim()})
      });
      renderAuth(result.user);
      dialog.close();
      $('login-code').value = '';
      $('verify-code-form').classList.add('hidden');
      loginEmail = '';
      loginMessage('');
      notify('You are now logged in.');
    } catch (error) {
      loginMessage(error.message, true);
    } finally {
      authBusy = false;
      updateAuthControls();
    }
  });
  $('logout-btn').addEventListener('click', async () => {
    const button = $('logout-btn');
    button.disabled = true;
    try {
      await getJSON('/api/auth/logout', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
      });
      returnToInitialState(true);
    } catch (error) {
      notify(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
  refreshAuth();
}
function lineChart(host,rows, includeForecast=false){
 const el=$(host);if(!rows.length){el.textContent='Not enough data for this chart.';return;}
 const W=760,H=295,pL=65,pT=17,pR=16,pB=43,chartW=W-pL-pR,chartH=H-pT-pB;
 const vals=rows.flatMap(r=>[r.cash_in,r.cash_out]);const max=Math.max(...vals,1)*1.13;
 const x=i=>pL+chartW*i/Math.max(1,rows.length-1),y=v=>pT+chartH*(1-v/max);
 const labels=rows.map((r,i)=>i%Math.max(1,Math.ceil(rows.length/6))===0||i===rows.length-1?`<text x="${x(i)}" y="${H-11}" fill="#8794a6" font-size="11" text-anchor="middle">${escapeHTML(friendlyMonth(r.month))}</text>`:'').join('');
 const grid=Array.from({length:5},(_,i)=>{const v=max*i/4;const yy=y(v);return `<line x1="${pL}" y1="${yy}" x2="${W-pR}" y2="${yy}" stroke="#edf0f7" stroke-width="1"/><text x="${pL-10}" y="${yy+4}" fill="#91a0b2" font-size="10" text-anchor="end">${fmt(v)}</text>`}).join('');
 const pointPath=(key,kind)=>rows.map((r,i)=>`${i?'L':'M'} ${x(i)} ${y(r[key])}`).join(' ');
 const series=[['cash_in','#16b6a2'],['cash_out','#8a7bf4']].map(([key,col])=>`<path d="${pointPath(key)}" fill="none" stroke="${col}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>`+rows.map((r,i)=>`<circle cx="${x(i)}" cy="${y(r[key])}" r="3" fill="${col}"><title>${escapeHTML(r.month)} ${key==='cash_in'?'Cash receipts':'Cash payments'} ${fmt(r[key])}</title></circle>`).join('')).join('');
 const boundary=includeForecast?`<line x1="${x(Math.max(0,rows.length-4))}" y1="${pT}" x2="${x(Math.max(0,rows.length-4))}" y2="${H-pB}" stroke="#a5aec0" stroke-dasharray="5 5"/><text x="${x(Math.max(0,rows.length-4))+6}" y="14" fill="#8b95a6" font-size="10">Forecast →</text>`:'';
 el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Financial cash-flow trend chart">${grid}${labels}${boundary}${series}</svg>`;
}
function drawCharts(){if(!DATA)return;lineChart('cash-chart',DATA.monthly.slice(-12));lineChart('forecast-chart',[...DATA.monthly.slice(-6),...DATA.forecast],true)}
function render(){if(!DATA)return;
 const d=DATA,t=d.totals; text('company-title',d.company);text('report-date',`${d.reporting_period} · ${d.transaction_count.toLocaleString()} transactions · ${d.months_count} months`);
 text('billed-revenue',t.last_month_invoiced_revenue===null?'Not provided':fmt(t.last_month_invoiced_revenue));text('metric-income',fmt(t.last_month_cash_in));text('metric-expenses',fmt(t.last_month_cash_out));text('metric-net',signed(t.last_month_net));text('metric-balance',signed(t.closing_cash));
 text('income-trend',t.cash_in_change_pct===null?'Cash receipts, not sales revenue':`${t.cash_in_change_pct>0?'+':''}${t.cash_in_change_pct}% vs previous month`);
 text('expense-trend',t.expense_change_pct===null?'Includes payroll & subscriptions':`${t.expense_change_pct>0?'+':''}${t.expense_change_pct}% vs previous month`);
 const biggest=Math.max(...d.categories.map(c=>c.amount),1);
 $('category-bars').innerHTML=d.categories.slice(0,6).map(c=>`<div><div class="bar-label"><span>${escapeHTML(c.category)}</span><b>${fmt(c.amount)}</b></div><div class="bar-bg"><div class="bar-fill" style="width:${Math.max(1,100*c.amount/biggest)}%"></div></div></div>`).join('')||'<p>No expense categories found.</p>';
 $('insight-list').innerHTML=d.anomalies.slice(0,4).map(a=>`<button class="insight insight-link" type="button" data-anomaly="${escapeHTML(a.id)}"><div class="insight-icon">!</div><div><strong>${escapeHTML(a.type)} · ${escapeHTML(a.category)}</strong><p>${escapeHTML(a.message)}</p><small>Investigate evidence →</small></div></button>`).join('')||'<p>No notable anomalies detected.</p>';
 $('insight-list').querySelectorAll('[data-anomaly]').forEach(button=>button.addEventListener('click',()=>openAnomaly(button.dataset.anomaly)));
 renderAnomalies();
 const future=d.forecast[0];text('predicted-sales',future.invoiced_revenue===null?'Not provided':fmt(future.invoiced_revenue));text('future-in',fmt(future.cash_in));text('future-out',fmt(future.cash_out));text('future-net',signed(future.net));text('future-ar',fmt(t.outstanding_invoices));
 $('invoice-list').innerHTML=d.overdue_invoices.slice(0,8).map(i=>`<div class="invoice"><div><strong>${escapeHTML(i.customer)}</strong> <span>· ${escapeHTML(i.invoice)} · due ${escapeHTML(i.due)}</span></div><b>${fmt(i.amount)} · ${i.overdue_days} days overdue</b></div>`).join('')||'<p>No overdue invoices in this dataset.</p>';
 text('sub-count',d.subscriptions.length);text('sub-monthly',fmt(t.subscription_monthly));text('sub-annual',fmt(t.subscription_annual));
 $('subscription-list').innerHTML=d.subscriptions.map(s=>`<div class="subscription-row"><div class="service-icon">${escapeHTML((s.name||'?').slice(0,1))}</div><div class="service-name">${escapeHTML(s.name)}<small>Recurring monthly · Usage not known</small></div><div class="service-amount">${fmt(s.monthly_cost)}<small>per month</small></div><div class="review-tag ${s.price_increase===0?'ok':''}">${s.price_increase>0?`↑ ${fmt(s.price_increase)} price rise`:'No price change detected'}</div></div>`).join('')||'<div class="callout">No subscription sheet present in this upload.</div>';
 text('wrap-income',fmt(d.wrapped.cash_in));text('wrap-expense',fmt(d.wrapped.cash_out));text('wrap-month',friendlyMonth(d.wrapped.biggest_expense_month));text('wrap-category',d.wrapped.largest_category);text('wrap-subs',fmt(d.wrapped.subscription_annual));
 renderTransactions();updateScenario();window.FINOVAStory.setData(d);requestAnimationFrame(drawCharts);
}
function openAnomaly(id){
  selectedAnomaly=id;
  anomalyFilter='all';
  document.querySelectorAll('.anomaly-filter').forEach(b=>b.classList.toggle('active',b.dataset.filter==='all'));
  switchPage('anomalies');
  renderAnomalies();
}
function renderAnomalies(){
  if(!DATA)return;
  const all=DATA.anomalies||[];
  text('anomaly-count',all.length);
  text('spike-count',all.filter(a=>a.type==='Spending spike').length);
  text('price-count',all.filter(a=>a.type==='Subscription increase').length);
  text('overdue-count',DATA.totals.overdue_invoices);
  const visible=all.filter(a=>anomalyFilter==='all'||a.type===anomalyFilter);
  if(!visible.some(a=>a.id===selectedAnomaly))selectedAnomaly=visible.length?visible[0].id:null;
  $('anomaly-list').innerHTML=visible.map(a=>`<button class="anomaly-item ${a.id===selectedAnomaly?'selected':''}" type="button" data-anomaly="${escapeHTML(a.id)}">
    <span class="anomaly-type">${escapeHTML(a.type)}</span><strong>${escapeHTML(a.category)} <span>›</span></strong>
    <small>${escapeHTML(a.month)} · ${escapeHTML(a.message)}</small></button>`).join('') || '<p class="anomaly-empty">No flagged patterns in this category.</p>';
  $('anomaly-list').querySelectorAll('[data-anomaly]').forEach(b=>b.addEventListener('click',()=>{selectedAnomaly=b.dataset.anomaly;renderAnomalies();}));
  renderAnomalyDetail(visible.find(a=>a.id===selectedAnomaly));
}
function renderAnomalyDetail(a){
  const el=$('anomaly-detail');
  if(!a){el.innerHTML='<p>Choose a financial signal to inspect its evidence.</p>';return;}
  const pct=(a.increase_pct!==null&&a.increase_pct!==undefined)?`<span class="detail-badge">+${escapeHTML(a.increase_pct)}% vs baseline</span>`:'';
  const baseline=a.baseline!==null&&a.baseline!==undefined?`<div><small>Comparison baseline</small><strong>${fmt(a.baseline)}</strong></div>`:'';
  const stats=`<div class="anomaly-stats"><div><small>Flagged amount</small><strong>${fmt(a.amount)}</strong></div>${baseline}<div><small>Period</small><strong>${escapeHTML(a.month)}</strong></div></div>`;
  const transactions=(a.evidence||[]).length?`<h4>Supporting transactions <span>(${a.evidence_count||a.evidence.length} matching records; showing up to ${a.evidence.length})</span></h4>
    <div class="table-scroll"><table class="evidence-table"><thead><tr><th>Date</th><th>Counterparty / description</th><th class="right">Amount</th></tr></thead><tbody>${a.evidence.map(t=>`<tr><td>${escapeHTML(t.date)}</td><td>${escapeHTML(t.vendor)}<small>${escapeHTML(t.description)}</small></td><td class="right">${fmt(t.amount)}</td></tr>`).join('')}</tbody></table></div>`:'';
  const invoices=(a.invoices||[]).length?`<h4>Overdue customer invoices <span>(at reporting date)</span></h4><div class="table-scroll"><table class="evidence-table"><thead><tr><th>Customer / invoice</th><th>Due</th><th class="right">Outstanding</th></tr></thead><tbody>${a.invoices.map(i=>`<tr><td>${escapeHTML(i.customer)}<small>${escapeHTML(i.invoice)}</small></td><td>${escapeHTML(i.due)}<small>${i.overdue_days} days late</small></td><td class="right">${fmt(i.amount)}</td></tr>`).join('')}</tbody></table></div>`:'';
  const hist=a.history?.length?`<h4>Recorded monthly amounts</h4><div class="anomaly-history">${a.history.map(h=>`<div><small>${escapeHTML(h.month)}</small><strong>${fmt(h.amount)}</strong><i style="width:${Math.max(3,Math.min(100,100*h.amount/Math.max(1,...a.history.map(z=>z.amount))))}%"></i></div>`).join('')}</div>`:'';
  el.innerHTML=`<div class="anomaly-detail-heading"><span class="eyebrow">${escapeHTML(a.type)} · ${escapeHTML(a.category)}</span><h3>${escapeHTML(a.message)}</h3>${pct}</div>
    ${stats}<h4>How FINOVA flagged it</h4><p>${escapeHTML(a.method||'FINOVA compared historical records.')}</p>
    ${hist}${transactions}${invoices}<div class="anomaly-action"><strong>Recommended next step</strong><p>${escapeHTML(a.action||'Review the original source records.')}</p></div>
    <button id="explain-anomaly" type="button" class="button button-primary">✦ Ask FINOVA about this</button>`;
  $('explain-anomaly').addEventListener('click',()=>{
    switchPage('overview');
    const q=`Explain the ${a.type.toLowerCase()} for ${a.category} in ${a.month} and what we should check.`;
    $('question').value=q;ask(q);
    $('ai-answer').scrollIntoView({behavior:'smooth',block:'center'});
  });
}
function renderTransactions(){if(!DATA)return;const q=$('transaction-search').value.trim().toLowerCase();const trs=DATA.recent_transactions.filter(t=>[t.description,t.category,t.vendor,t.date].some(x=>String(x).toLowerCase().includes(q)));
 $('transaction-table').innerHTML=trs.map(t=>`<tr><td>${escapeHTML(t.date)}</td><td><strong>${escapeHTML(t.description)}</strong></td><td>${escapeHTML(t.category)}</td><td>${escapeHTML(t.type)}</td><td class="right ${t.signed<0?'negative':'positive'}">${signed(t.signed)}</td></tr>`).join('')||'<tr><td colspan="5">No matching transactions found.</td></tr>';
}
function updateScenario(){if(!DATA)return;let r=Number($('rev-slider').value),e=Number($('exp-slider').value);text('rev-label',`${r>0?'+':''}${r}%`);text('exp-label',`${e>0?'+':''}${e}%`);let f=DATA.forecast[0];text('scenario-net',signed(f.cash_in*(1+r/100)-f.cash_out*(1+e/100)))}
async function boot(){try { const status=await getJSON('/api/health');text('ai-connection',status.akamai_key_loaded?'Akamai key loaded (verify connection)':'Offline financial analysis ready');text('akamai-status',status.akamai_key_loaded?'Akamai team key loaded. Click Test Akamai connection to verify live access.':'Offline mode: configure your Akamai team key in finova/.env to generate AI artwork. The animated video works without a key.');DATA=await getJSON('/api/dashboard');render();} catch(e){notify(e.message,true)}}
async function uploadFile(file){if(!file)return;if(!/\.(csv|xlsx)$/i.test(file.name)){notify('Choose a .xlsx or .csv file.',true);return}if(file.size>12*1024*1024){notify('File too large for this demo.',true);return}
 $('loading').style.display='block';try{const fd=new FormData();fd.append('file',file);const response=await getJSON('/api/upload',{method:'POST',body:fd});DATA=response.summary;window.FINOVAStory.resetArt();text('loaded-file',file.name);render();switchPage('overview');notify(`Analyzed ${DATA.transaction_count.toLocaleString()} financial transactions successfully.`)}catch(e){notify(e.message,true)}finally{$('loading').style.display='none';$('file-input').value=''}}
async function ask(question){
 const output=$('ai-answer');output.textContent='FINOVA is analyzing the figures…';
 try{
  const res=await getJSON('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});
  output.textContent=res.answer;text('ai-source',res.source);
  const mode=$('ai-mode');
  if(res.mode==='local'){
    mode.textContent=(res.warning?`Akamai unavailable: ${res.warning} `:'')+'Showing evidence-based local analysis.';
    mode.classList.add('is-local');text('ai-connection','FINOVA local analysis active');
  } else {mode.textContent='Akamai AI connected · Answer grounded in verified FINOVA calculations.';mode.classList.remove('is-local');text('ai-connection','Akamai AI connected');}
 }catch(e){output.textContent='FINOVA could not answer: '+e.message;}
}
window.addEventListener('DOMContentLoaded',()=>{
 initAuth();
 document.querySelectorAll('.nav-link').forEach(b=>b.addEventListener('click',()=>switchPage(b.dataset.view)));
 $('file-input').addEventListener('change',e=>uploadFile(e.target.files[0]));
 $('reset-btn').addEventListener('click',async()=>{try{const res=await getJSON('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});DATA=res.summary;text('loaded-file','Demo workbook: finova.xlsx');window.FINOVAStory.resetArt();render();notify('Demo workbook restored.')}catch(e){notify(e.message,true)}});
 $('transaction-search').addEventListener('input',renderTransactions);
 $('view-all-anomalies').addEventListener('click',()=>openAnomaly(null));
 document.querySelectorAll('.anomaly-filter').forEach(b=>b.addEventListener('click',()=>{
  anomalyFilter=b.dataset.filter;selectedAnomaly=null;
  document.querySelectorAll('.anomaly-filter').forEach(x=>x.classList.toggle('active',x===b));renderAnomalies();
 }));
 ['rev-slider','exp-slider'].forEach(id=>$(id).addEventListener('input',updateScenario));
 document.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>{$('question').value=b.dataset.prompt;ask(b.dataset.prompt)}));
 $('ask-form').addEventListener('submit',e=>{e.preventDefault();let q=$('question').value.trim();if(q)ask(q)});
 window.FINOVAStory.init();
 $('akamai-test').addEventListener('click',async()=>{
   const btn=$('akamai-test');btn.disabled=true;text('akamai-status','Testing your live Akamai workshop access…');
   try{const res=await getJSON('/api/akamai-test');text('akamai-status',res.message);$('akamai-status').classList.remove('is-error');text('ai-connection','Akamai API access verified');text('ai-mode','Akamai API verified. Ask FINOVA to generate an AI explanation.');}
   catch(e){text('akamai-status',e.message);$('akamai-status').classList.add('is-error')}
   finally{btn.disabled=false}
 });
 $('cover-btn').addEventListener('click',async()=>{
   const btn=$('cover-btn');btn.disabled=true;btn.textContent='Generating Akamai art…';
   text('akamai-status','Requesting artwork from Akamai. This can take a little time.');
   try{const res=await getJSON('/api/cover',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
     window.FINOVAStory.setArt(res.image);text('akamai-status','Akamai artwork received and added to the story. Play or export it now!');$('akamai-status').classList.remove('is-error');
   }catch(e){text('akamai-status',e.message+' · Your FINOVA Wrapped animation still works without this image.');$('akamai-status').classList.add('is-error')}
   finally{btn.disabled=false;btn.textContent='✦ Generate Akamai artwork'}
 });
 boot();
});
