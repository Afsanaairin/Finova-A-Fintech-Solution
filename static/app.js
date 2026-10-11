'use strict';
let DATA = null;
let currentUser = null;
let selectedAnomaly = null;
let anomalyFilter = 'all';
let clientSessionVersion = 0;
let initialLayoutHTML = null;
const pendingRequests = new Set();
const SESSION_ENDED_MESSAGE = 'This session has ended.';
const LOGOUT_EVENT_KEY = 'finova_logout';
let activeCardInfo = null;
let pinnedCardInfo = null;
let cardInfoCloseTimer;
let serverHasPDF = null;
const askRequestVersions = {overview:0,dialog:0};
let askData = null;
const $ = id => document.getElementById(id);
const fmt = x => x === null || x === undefined ? 'Not provided' : '$' + Math.abs(Number(x)).toLocaleString('en-US',{minimumFractionDigits:0,maximumFractionDigits:0});
const signed = x => (Number(x)<0 ? '−' : '') + fmt(x);
const text = (id,value) => {$(id).textContent = String(value)};
const friendlyMonth = iso => new Date(iso+'-01T00:00:00').toLocaleString('en-US',{month:'short',year:'numeric'});
const escapeHTML = value => String(value??'').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
function notify(message, bad=false) { if(message===SESSION_ENDED_MESSAGE)return;const box=$('alert');box.textContent=message;box.classList.remove('hidden');box.classList.toggle('error',bad);setTimeout(()=>box.classList.add('hidden'),7000);}
const pageInfo = {anomalies:['Anomaly Explorer','Find what changed. Understand why it matters.','Evidence-backed cost and invoice investigations.'],overview:['Overview','A clearer picture of your finance.','From transactions to foresight. Understand what changed, what matters, and what comes next.'],forecast:['Forecast & Scenarios','Plan for what comes next.','Explore the cash implications of tomorrow’s decisions.'],subscriptions:['Subscriptions','Make every recurring dollar count.','Understand recurring expenses and price changes.'],transactions:['Transactions','Your money, line by line.','Transparent transaction analysis with an audit trail.'],wrapped:['Business Wrapped','Your financial story, reimagined.','FINOVA turns numbers into a meaningful business recap.']};
function switchPage(id){
 if(!currentUser)return;
 if($('ask-dialog')?.open)$('ask-dialog').close();
 hideCardInfo();
 document.querySelectorAll('.page').forEach(el=>el.classList.toggle('hidden',el.id!==id));
 document.querySelectorAll('.nav-link').forEach(el=>el.classList.toggle('active',el.dataset.view===id));
 const [name,title,sub] = pageInfo[id];text('page-crumb',name);text('page-title',title);text('page-subtitle',sub);
 if(id==='overview'||id==='forecast') requestAnimationFrame(drawCharts);
 window.scrollTo({top:0,behavior:'smooth'});
}
async function getJSON(url, options = {}) {
  const {responseType = 'json', timeoutMs = 45000, timeoutMessage = 'The request timed out. Check that FINOVA is running and try again.', ...requestOptions} = options;
  const headers = new Headers(requestOptions.headers);
  if ((requestOptions.method || 'GET').toUpperCase() === 'POST') headers.set('X-Finova-Request', '1');
  let timedOut = false;
  const controller = new AbortController();
  const version = clientSessionVersion;
  pendingRequests.add(controller);
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetch(url, {...requestOptions, headers, cache: 'no-store', signal: controller.signal});
    let payload;
    try {
      if(responseType==='pdf'&&response.ok){
        if(!response.headers.get('Content-Type')?.startsWith('application/pdf'))throw new Error('Expected a PDF report.');
        payload={blob:await response.blob(),filename:response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||'finova-report.pdf'};
      }else payload = await response.json();
    } catch {
      throw new Error('Server returned a non-JSON response.');
    }
    if (version !== clientSessionVersion) throw new Error(SESSION_ENDED_MESSAGE);
    if (response.status === 401 && !url.startsWith('/api/auth/')) {
      returnToInitialState();
      throw new Error(SESSION_ENDED_MESSAGE);
    }
    if (!response.ok) {
      const error = new Error(payload.error || 'Request failed');
      error.status = response.status;
      error.retryAfter = Number(payload.retry_after || response.headers.get('Retry-After') || 0);
      throw error;
    }
    return payload;
  } catch (error) {
    if (version === clientSessionVersion && timedOut) throw new Error(timeoutMessage);
    if (controller.signal.aborted || version !== clientSessionVersion) {
      const cancelled = new Error(SESSION_ENDED_MESSAGE);
      cancelled.name = 'AbortError';
      throw cancelled;
    }
    throw error;
  } finally {
    clearTimeout(timer);
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
  currentUser = user;
  $('dashboard').classList.toggle('hidden', !user);
  $('login-page').classList.toggle('hidden', Boolean(user));
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
  renderAuth(null);
  clientSessionVersion += 1;
  pendingRequests.forEach(controller => controller.abort());
  pendingRequests.clear();
  DATA = null;
  resetAskState();
  askData = null;
  selectedAnomaly = null;
  anomalyFilter = 'all';
  loginEmail = '';
  authBusy = false;
  resendAvailableByEmail.clear();
  if (resendTimer !== null) clearInterval(resendTimer);
  resendTimer = null;
  hideCardInfo();
  window.FINOVAPdf?.clear();
  window.FINOVAReports?.reset();
  window.FINOVAStory.reset();
  const layout = document.querySelector('.layout');
  if (layout && initialLayoutHTML !== null) layout.innerHTML = initialLayoutHTML;
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
  authBusy = true;
  updateAuthControls();
  try {
    const result = await getJSON('/api/auth/me');
    renderAuth(result.user);
    loginMessage('');
    if (result.user) await boot();
  } catch (error) {
    if(error.message!==SESSION_ENDED_MESSAGE)loginMessage(error.message, true);
  } finally {
    authBusy = false;
    updateAuthControls();
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
      if (loginEmail && !currentUser) $('login-code').focus();
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
      await boot();
      if(!currentUser)return;
      switchPage('overview');
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
function drawCharts(){if(!DATA)return;lineChart('cash-chart',DATA.monthly.slice(-12));lineChart('forecast-chart',DATA.forecast.length?[...DATA.monthly.slice(-6),...DATA.forecast]:[],true)}
function render(){if(!DATA)return;
 const filename=DATA.import_source?.demo?'':(DATA.import_source?.filename||'');
 text('loaded-file',filename);
 $('loaded-file').classList.toggle('hidden',!filename);
 if(askData!==DATA){resetAskState();askData=DATA;}
 document.querySelectorAll('.financial-card').forEach(card=>toggleCardBreakdown(card,false));
 const d=DATA,t=d.totals,invoiceOnly=d.analysis_kind==='invoices'; text('company-title',d.company);text('report-date',invoiceOnly?`${d.invoice_count} customer invoices · evaluated as of ${d.as_of}`:`${d.reporting_period} · ${d.transaction_count.toLocaleString()} transactions · ${d.months_count} months`);
 $('invoice-overview').classList.toggle('hidden',!invoiceOnly);
 ['cash-metrics','cash-panels','revenue-note'].forEach(id=>$(id).classList.toggle('hidden',invoiceOnly));
 document.querySelectorAll('.nav-link').forEach(button=>{
   const unavailable=(invoiceOnly&&['forecast','transactions','wrapped'].includes(button.dataset.view))||(!d.forecast.length&&button.dataset.view==='forecast');
   button.disabled=unavailable;button.title=unavailable?'Provide a complete cash ledger with sufficient history to use this view.':'';
 });
 const scoped=d.data_scope&&d.data_scope!=='complete';
 $('data-scope-note').classList.toggle('hidden',!scoped);
 text('data-scope-note',invoiceOnly?'Customer invoice report. Invoice amounts do not establish cash received; cash balances and forecasts need transaction records.':'This report covers the uploaded records only. It does not establish your business’s complete cash flow or closing cash balance.');
 if(invoiceOnly){
   text('invoice-total',fmt(t.invoice_amount));text('invoice-outstanding',fmt(t.outstanding_invoices));text('invoice-overdue',t.overdue_invoices);
   text('invoice-unknown',`${t.unknown_invoice_balances} unknown payment balance(s); excluded from the subtotal.`);
   text('invoice-as-of',`As of ${d.as_of} · ${t.missing_invoice_due_dates} missing due date(s)`);
   $('invoice-table').innerHTML=d.invoices.map(i=>`<tr><td>${escapeHTML(i.customer)}<small>${escapeHTML(i.invoice)}</small></td><td>${escapeHTML(i.due||'Not provided')}</td><td>${escapeHTML(i.status)}</td><td class="right">${fmt(i.amount)}</td><td class="right">${fmt(i.outstanding)}</td></tr>`).join('');
 }
 text('billed-revenue',t.last_month_invoiced_revenue===null?'Not provided':fmt(t.last_month_invoiced_revenue));text('metric-income',fmt(t.last_month_cash_in));text('metric-expenses',fmt(t.last_month_cash_out));text('metric-net',signed(t.last_month_net));text('metric-balance',signed(t.closing_cash));
 text('income-trend',t.cash_in_change_pct===null?'Cash receipts, not sales revenue':`${t.cash_in_change_pct>0?'+':''}${t.cash_in_change_pct}% vs previous month`);
 text('expense-trend',t.expense_change_pct===null?'Uploaded outgoing payments':`${t.expense_change_pct>0?'+':''}${t.expense_change_pct}% vs previous month`);
 text('balance-note',d.has_opening_cash?'From supplied opening cash + ledger entries':'Provide opening cash and a complete cash ledger');
 const biggest=Math.max(...d.categories.map(c=>c.amount),1);
 $('category-bars').innerHTML=d.categories.slice(0,6).map(c=>`<div><div class="bar-label"><span>${escapeHTML(c.category)}</span><b>${fmt(c.amount)}</b></div><div class="bar-bg"><div class="bar-fill" style="width:${Math.max(1,100*c.amount/biggest)}%"></div></div></div>`).join('')||'<p>No expense categories found.</p>';
 $('insight-list').innerHTML=d.anomalies.slice(0,4).map(a=>`<button class="insight insight-link" type="button" data-anomaly="${escapeHTML(a.id)}"><div class="insight-icon">!</div><div><strong>${escapeHTML(a.type)} · ${escapeHTML(a.category)}</strong><p>${escapeHTML(a.message)}</p><small>Investigate evidence →</small></div></button>`).join('')||'<p>No notable anomalies detected.</p>';
 $('insight-list').querySelectorAll('[data-anomaly]').forEach(button=>button.addEventListener('click',()=>openAnomaly(button.dataset.anomaly)));
 renderAnomalies();
 const future=d.forecast[0];text('predicted-sales',fmt(future?.invoiced_revenue));text('future-in',fmt(future?.cash_in));text('future-out',fmt(future?.cash_out));text('future-net',signed(future?.net));text('future-ar',fmt(d.has_invoice_data?t.outstanding_invoices:null));
 $('invoice-list').innerHTML=d.overdue_invoices.slice(0,8).map(i=>`<div class="invoice"><div><strong>${escapeHTML(i.customer)}</strong> <span>· ${escapeHTML(i.invoice)} · due ${escapeHTML(i.due)}</span></div><b>${fmt(i.amount)} · ${i.overdue_days} days overdue</b></div>`).join('')||(d.has_invoice_data?'<p>No overdue invoices with known balances in this dataset.</p>':'<p>Customer invoice records were not provided.</p>');
 text('sub-count',d.has_subscription_data?d.subscriptions.length:'Not provided');text('sub-monthly',fmt(d.has_subscription_data?t.subscription_monthly:null));text('sub-annual',fmt(d.has_subscription_data?t.subscription_annual:null));
 $('subscription-list').innerHTML=d.subscriptions.map(s=>`<div class="subscription-row"><div class="service-icon">${escapeHTML((s.name||'?').slice(0,1))}</div><div class="service-name">${escapeHTML(s.name)}<small>Recurring monthly · Usage not known</small></div><div class="service-amount">${fmt(s.monthly_cost)}<small>per month</small></div><div class="review-tag ${s.price_increase===0?'ok':''}">${s.price_increase>0?`↑ ${fmt(s.price_increase)} price rise`:'No price change detected'}</div></div>`).join('')||'<div class="callout">No subscription sheet present in this upload.</div>';
 if(d.wrapped){text('wrap-income',fmt(d.wrapped.cash_in));text('wrap-expense',fmt(d.wrapped.cash_out));text('wrap-month',friendlyMonth(d.wrapped.biggest_expense_month));text('wrap-category',d.wrapped.largest_category);text('wrap-subs',fmt(d.has_subscription_data?d.wrapped.subscription_annual:null));}
 renderTransactions();updateScenario();window.FINOVAStory.setData(d.wrapped?d:null);window.FINOVAReports?.setData(d);requestAnimationFrame(drawCharts);
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
  text('spike-count',DATA.analysis_kind==='invoices'?'Not provided':all.filter(a=>a.type==='Spending spike').length);
 text('price-count',DATA.has_subscription_data?all.filter(a=>a.type==='Subscription increase').length:'Not provided');
 text('overdue-count',DATA.has_invoice_data?DATA.totals.overdue_invoices:'Not provided');
  text('anomaly-group-note',DATA.has_invoice_data?`${DATA.totals.overdue_invoices} overdue invoice(s) are grouped into ${all.filter(a=>a.type==='Overdue invoices').length} flagged pattern(s). Patterns and individual invoice counts are different totals.`:'Patterns count only the checks supported by the uploaded records.');
  renderFinancialCards();
  const visible=all.filter(a=>anomalyFilter==='all'||a.type===anomalyFilter);
  if(!visible.some(a=>a.id===selectedAnomaly))selectedAnomaly=visible.length?visible[0].id:null;
  $('anomaly-list').innerHTML=visible.map(a=>`<button class="anomaly-item ${a.id===selectedAnomaly?'selected':''}" type="button" data-anomaly="${escapeHTML(a.id)}">
    <span class="anomaly-type">${escapeHTML(a.type)}</span><strong>${escapeHTML(a.category)} <span>›</span></strong>
    <small>${escapeHTML(a.month)} · ${escapeHTML(a.message)}</small></button>`).join('') || '<p class="anomaly-empty">No flagged patterns in this category.</p>';
  $('anomaly-list').querySelectorAll('[data-anomaly]').forEach(b=>b.addEventListener('click',()=>{selectedAnomaly=b.dataset.anomaly;renderAnomalies();}));
  renderAnomalyDetail(visible.find(a=>a.id===selectedAnomaly));
}
function hideCardInfo(){
  clearTimeout(cardInfoCloseTimer);
  document.querySelectorAll('.financial-card-info').forEach(button=>button.setAttribute('aria-expanded','false'));
  document.querySelectorAll('.financial-card-tooltip').forEach(tip=>tip.classList.add('hidden'));
  activeCardInfo=null;pinnedCardInfo=null;
}
function positionCardInfo(card){
  const tip=card.querySelector('.financial-card-tooltip'),anchor=card.getBoundingClientRect();
  const bounds=tip.getBoundingClientRect(),below=anchor.bottom+8,above=anchor.top-bounds.height-8;
  tip.style.left=`${Math.max(16,Math.min(anchor.left,window.innerWidth-bounds.width-16))}px`;
  tip.style.top=`${Math.max(16,Math.min(below+bounds.height<=window.innerHeight-16?below:above,window.innerHeight-bounds.height-16))}px`;
}
function showCardInfo(card,pin=false){
  if(activeCardInfo!==card){hideCardInfo();activeCardInfo=card;}
  clearTimeout(cardInfoCloseTimer);
  if(pin)pinnedCardInfo=card;
  card.querySelector('.financial-card-tooltip').classList.remove('hidden');
  card.querySelector('.financial-card-info').setAttribute('aria-expanded','true');
  positionCardInfo(card);
}
function toggleCardBreakdown(card,expanded){
  const button=card.querySelector('.financial-card-toggle');
  const show=expanded??button.getAttribute('aria-expanded')!=='true';
  hideCardInfo();
  button.setAttribute('aria-expanded',String(show));
  button.setAttribute('aria-label',`${show?'Hide':'Show'} breakdown for ${card.querySelector('.financial-card-heading>span').textContent}`);
  button.querySelector('span').textContent=show?'Hide breakdown':'Show breakdown';
  button.querySelector('b').textContent=show?'⌃':'⌄';
  card.querySelector('.financial-card-breakdown').classList.toggle('hidden',!show);
}
function renderFinancialCards(){
  hideCardInfo();
  const d=DATA,t=d.totals,latest=d.monthly.at(-1),previous=d.monthly.at(-2),all=d.anomalies||[];
  const hasTransactions=d.analysis_kind!=='invoices';
  const spikes=all.filter(a=>a.type==='Spending spike'),prices=all.filter(a=>a.type==='Subscription increase');
  const invoiceFlags=all.filter(a=>a.type==='Overdue invoices'),invoiceFlag=invoiceFlags[0];
  const subscriptionIncrease=prices.reduce((sum,a)=>sum+(a.amount-a.baseline),0);
  const overdueBalance=invoiceFlag?.amount??0;
  const count=(value,label)=>`${value} ${label}${value===1?'':'s'}`;
  const patternTypes=[];
  if(hasTransactions)patternTypes.push(count(spikes.length,'spending spike'));
  if(d.has_subscription_data)patternTypes.push(count(prices.length,'subscription increase'));
  if(d.has_invoice_data)patternTypes.push(count(invoiceFlags.length,'overdue-invoice flag'));
  const period=latest?`${friendlyMonth(d.monthly[0].month)} – ${friendlyMonth(latest.month)}`:`Invoice records · as of ${d.as_of}`;
  const amount=value=>value===null||value===undefined?'Not provided':Number(value).toLocaleString('en-US',{style:'currency',currency:'USD'});
  const row=(label,value,total=false)=>`<div class="financial-breakdown-row${total?' financial-breakdown-total':''}"><span>${escapeHTML(label)}</span><b${total&&String(value).startsWith('-')?' class="financial-value-negative"':''}>${escapeHTML(value)}</b></div>`;
  const note=message=>`<p class="financial-breakdown-note">${escapeHTML(message)}</p>`;
  const explanations={
    'cash-received':'Money actually received during the latest reporting month. Customer invoices show billed amounts separately.',
    'cash-paid':'Money paid during the latest reporting month, including recorded payroll, supplier and operating payments.',
    'net-cash':'Cash received minus cash paid. This measures cash flow, not accounting profit.',
    'closing-cash':'Opening cash plus receipts minus payments across the reporting period. Complete transaction coverage is required.',
    patterns:all.length?`${count(all.length,'pattern')} flagged: ${patternTypes.join(', ')}. One invoice flag can cover several invoices.`:'No patterns flagged in the provided records. Checks are limited to the data uploaded.',
    spikes:hasTransactions?`${count(spikes.length,'category-month spending spike')} exceeded the recent median by more than 40% and at least $100.`:'Transaction records were not provided. Upload categorized expenses to check spending spikes.',
    subscriptions:d.has_subscription_data?`${count(prices.length,'subscription price increase')} added ${amount(subscriptionIncrease)}/month compared with the first recorded charges.`:'Subscription records were not provided in this upload.',
    overdue:d.has_invoice_data?`${count(t.overdue_invoices,'customer invoice')} overdue as of ${d.as_of}, with ${amount(overdueBalance)} in known outstanding balances.`:'Customer invoice records were not provided in this upload.'
  };
  const cashComparison=(key,change)=>row('Reporting month',latest?friendlyMonth(latest.month):'Not provided')+row('This month',amount(latest?.[key]))+row('Previous month',amount(previous?.[key]))+row('Change',change===null||change===undefined?'Not available':`${change>0?'+':''}${change}%`);
  const breakdowns={
    'cash-received':cashComparison('cash_in',t.cash_in_change_pct)+note('Calculated from posted Income transactions. Billed revenue is tracked separately.'),
    'cash-paid':cashComparison('cash_out',t.expense_change_pct)+note('Calculated from posted Expense transactions. Payroll and supplier payments already in the ledger are counted once.'),
    'net-cash':row('Cash received',amount(t.last_month_cash_in))+row('Cash paid',amount(t.last_month_cash_out))+row('Net cash movement',amount(t.last_month_net),true)+note('Cash received − cash paid. This is a cash-flow measure, not the company’s accounting profit.'),
    'closing-cash':row('Opening cash',d.has_opening_cash?amount(t.closing_cash-t.net):'Not provided')+row('Cash received · whole period',amount(t.cash_in))+row('Cash paid · whole period',amount(t.cash_out))+row('Closing cash',amount(t.closing_cash),true)+note(d.has_opening_cash?'Opening cash + recorded receipts − recorded payments, across the uploaded reporting period.':'Provide an opening balance and a complete cash ledger to calculate closing cash.'),
    patterns:row('Spending spikes',hasTransactions?spikes.length:'Not provided')+row('Subscription changes',d.has_subscription_data?prices.length:'Not provided')+row('Flags for overdue invoices',d.has_invoice_data?invoiceFlags.length:'Not provided'),
    spikes:row('Spending spikes',hasTransactions?spikes.length:'Not provided'),
    subscriptions:row('Subscription changes',d.has_subscription_data?prices.length:'Not provided')+(d.has_subscription_data?row('Added monthly cost',amount(subscriptionIncrease),true):''),
    overdue:row('Overdue invoices',d.has_invoice_data?t.overdue_invoices:'Not provided')+(d.has_invoice_data?row('Reporting date',d.as_of)+row('Known overdue balance',amount(overdueBalance),true):'')
  };
  text('patterns-context',period);
  text('spikes-context',hasTransactions?'Category spending across the uploaded period':'Transaction records not provided');
  text('subscriptions-context',d.has_subscription_data?`${amount(subscriptionIncrease)} more per month`:'Subscription records not provided');
  text('overdue-context',d.has_invoice_data?`${amount(overdueBalance)} known overdue · as of ${d.as_of}`:'Customer invoice records not provided');
  document.querySelectorAll('.financial-card').forEach(card=>{
    const kind=card.dataset.card;
    card.querySelector('.financial-card-tooltip').textContent=explanations[kind];
    card.querySelector('.financial-card-breakdown').innerHTML=breakdowns[kind];
  });
  const net=t.last_month_net;
  text('net-cash-period',latest?`${friendlyMonth(latest.month)} · ${net>0?'Positive':net<0?'Negative':'No'} net cash movement`:'Cash transactions not provided');
  $('metric-net').classList.toggle('metric-positive',net!==null&&net>0);
  $('metric-net').classList.toggle('metric-negative',net!==null&&net<0);
}
function initFinancialCards(){
  document.querySelectorAll('.financial-card').forEach(card=>{
    const kind=card.dataset.card,label=card.querySelector('span'),title=label.textContent;
    label.outerHTML=`<div class="financial-card-heading"><span id="card-${kind}-label">${escapeHTML(title)}</span><button type="button" class="financial-card-info" aria-label="About ${escapeHTML(title)}" aria-expanded="false" aria-controls="card-${kind}-tip" aria-describedby="card-${kind}-tip">ⓘ</button></div>`;
    card.insertAdjacentHTML('beforeend',`<p id="card-${kind}-tip" class="financial-card-tooltip hidden" role="tooltip"></p><button type="button" class="financial-card-toggle" aria-label="Show breakdown for ${escapeHTML(title)}" aria-expanded="false" aria-controls="card-${kind}-breakdown"><span>Show breakdown</span><b aria-hidden="true">⌄</b></button><div id="card-${kind}-breakdown" class="financial-card-breakdown hidden" role="region" aria-labelledby="card-${kind}-label"></div>`);
    const info=card.querySelector('.financial-card-info');
    card.addEventListener('pointerenter',event=>{if(event.pointerType!=='touch')showCardInfo(card)});
    card.addEventListener('pointerleave',()=>{
      cardInfoCloseTimer=setTimeout(()=>{if(activeCardInfo===card&&pinnedCardInfo!==card&&document.activeElement!==info)hideCardInfo()},160);
    });
    info.addEventListener('focus',()=>showCardInfo(card));
    info.addEventListener('blur',()=>{if(pinnedCardInfo!==card&&!card.matches(':hover'))hideCardInfo()});
    info.addEventListener('click',()=>{if(pinnedCardInfo===card)hideCardInfo();else showCardInfo(card,true)});
    card.querySelector('.financial-card-toggle').addEventListener('click',()=>toggleCardBreakdown(card));
  });
  document.addEventListener('keydown',event=>{if(event.key==='Escape')hideCardInfo()});
  document.addEventListener('pointerdown',event=>{if(activeCardInfo&&!activeCardInfo.contains(event.target))hideCardInfo()});
  document.addEventListener('scroll',event=>{
    if(activeCardInfo){
      const bounds=activeCardInfo.getBoundingClientRect();
      if(bounds.bottom<0||bounds.top>window.innerHeight)hideCardInfo();else positionCardInfo(activeCardInfo);
    }
  },{capture:true,passive:true});
  window.addEventListener('resize',()=>{if(activeCardInfo)positionCardInfo(activeCardInfo)});
}
function renderAnomalyDetail(a){
  const el=$('anomaly-detail');
  if(!a){el.innerHTML='<p>Choose a financial signal to inspect its evidence.</p>';return;}
  const info=a.investigation;
  if(!info){el.innerHTML='<p>Restart FINOVA and reload the page to load the updated investigations and reports.</p>';return;}
  const precise=value=>Number(value).toLocaleString('en-US',{style:'currency',currency:'USD'});
  const stats=`<div class="anomaly-stats">${info.metrics.map(m=>`<div><small>${escapeHTML(m.label)}</small><strong>${escapeHTML(precise(m.value))}</strong></div>`).join('')}</div>`;
  const transactions=(a.evidence||[]).length?`<h4>Supporting transactions <span>(${a.evidence_count||a.evidence.length} matching records; showing up to ${a.evidence.length})</span></h4>
    <div class="table-scroll"><table class="evidence-table"><thead><tr><th>Date</th><th>Counterparty / description</th><th class="right">Amount</th></tr></thead><tbody>${a.evidence.map(t=>`<tr><td>${escapeHTML(t.date)}</td><td>${escapeHTML(t.vendor)}<small>${escapeHTML(t.description)}</small></td><td class="right">${precise(t.amount)}</td></tr>`).join('')}</tbody></table></div>`:'';
  const invoices=(a.invoices||[]).length?`<h4>Overdue customer invoices <span>(at reporting date)</span></h4><div class="table-scroll"><table class="evidence-table"><thead><tr><th>Customer / invoice</th><th>Due</th><th class="right">Outstanding</th></tr></thead><tbody>${a.invoices.map(i=>`<tr><td>${escapeHTML(i.customer)}<small>${escapeHTML(i.invoice)}</small></td><td>${escapeHTML(i.due)}<small>${i.overdue_days} days late</small></td><td class="right">${precise(i.amount)}</td></tr>`).join('')}</tbody></table></div>`:'';
  const hist=a.history?.length?`<h4>Recorded monthly amounts</h4><div class="anomaly-history">${a.history.map(h=>`<div><small>${escapeHTML(h.month)}</small><strong>${precise(h.amount)}</strong><i style="width:${Math.max(3,Math.min(100,100*h.amount/Math.max(1,...a.history.map(z=>z.amount))))}%"></i></div>`).join('')}</div>`:'';
  el.innerHTML=`<div class="anomaly-detail-heading"><span class="eyebrow">FINOVA RISK INVESTIGATION</span><h3>${escapeHTML(info.title)}</h3><span class="pill amber">${escapeHTML(info.status)}</span></div>
    ${stats}<div class="investigation-questions">${info.questions.map((q,index)=>`<article class="investigation-question investigation-question-${index}"><span class="investigation-label">${escapeHTML(q.label)}</span><h4>${index+1}. ${escapeHTML(q.question)}</h4><p>${escapeHTML(q.text)}</p></article>`).join('')}</div>
    <details class="investigation-evidence"><summary>Supporting records and historical amounts</summary>${hist}${transactions}${invoices}</details>
    <p class="investigation-source">Source: ${escapeHTML(info.source)} · Reporting date: ${escapeHTML(info.as_of)}<br>${DATA.import_source?.demo?'Illustrative investigation · Demo workbook':escapeHTML(info.note)}</p>
    <div class="investigation-actions"><button id="download-investigation" type="button" class="button button-primary">↓ Download report (PDF)</button><button id="explain-anomaly" type="button" class="button button-muted">✦ Ask FINOVA about this</button></div>`;
  $('download-investigation').addEventListener('click',()=>window.FINOVAReports?.downloadAnomaly(a.id,$('download-investigation')));
  $('explain-anomaly').addEventListener('click',()=>{
    const q=`Explain the ${a.type.toLowerCase()} for ${a.category} in ${a.month} and what we should check.`;
    openAskDialog('anomalies',q,true);
  });
}
function renderTransactions(){if(!DATA)return;const q=$('transaction-search').value.trim().toLowerCase();const trs=DATA.recent_transactions.filter(t=>[t.description,t.category,t.vendor,t.date].some(x=>String(x).toLowerCase().includes(q)));
 $('transaction-table').innerHTML=trs.map(t=>`<tr><td>${escapeHTML(t.date)}</td><td><strong>${escapeHTML(t.description)}</strong></td><td>${escapeHTML(t.category)}</td><td>${escapeHTML(t.type)}</td><td class="right ${t.signed<0?'negative':'positive'}">${signed(t.signed)}</td></tr>`).join('')||'<tr><td colspan="5">No matching transactions found.</td></tr>';
}
function updateScenario(){if(!DATA)return;let r=Number($('rev-slider').value),e=Number($('exp-slider').value);text('rev-label',`${r>0?'+':''}${r}%`);text('exp-label',`${e>0?'+':''}${e}%`);let f=DATA.forecast[0];['rev-slider','exp-slider'].forEach(id=>$(id).disabled=!f);text('scenario-net',f?signed(f.cash_in*(1+r/100)-f.cash_out*(1+e/100)):'Not available')}
async function boot(){try { const status=await getJSON('/api/health');serverHasPDF=Boolean(status.pdf_support);window.FINOVAPdf?.setCapabilities(status.pdf_support);text('pdf-support-note',!serverHasPDF?'Restart the FINOVA server and reload this page to enable PDF uploads.':!window.FINOVAPdf?'Reload this page to load the PDF upload interface.':status.pdf_support.text?'PDF extraction is available on this server.':'PDF extraction needs server setup; CSV and Excel are ready.');text('ai-connection',status.akamai_key_loaded?'Akamai key loaded (verify connection)':'Offline financial analysis ready');DATA=await getJSON('/api/dashboard');render();} catch(e){notify(e.message,true)}}
function applyImport(summary){DATA=summary;window.FINOVAStory.resetArt();render();switchPage('overview');notify(DATA.analysis_kind==='invoices'?`Analyzed ${DATA.invoice_count} reviewed customer invoices.`:`Analyzed ${DATA.transaction_count.toLocaleString()} financial transactions successfully.`)}
async function uploadFile(file,forceOCR=false){if(!file)return;if(!/\.(csv|xlsx|pdf)$/i.test(file.name)){notify('Choose a .xlsx, .csv or .pdf file.',true);return}if(file.size>12*1024*1024){notify('File too large for this demo.',true);return}
 const isPDF=/\.pdf$/i.test(file.name);let progressTimer;
 $('upload-error')?.classList.add('hidden');
 try{
  if(isPDF&&(serverHasPDF===false||!window.FINOVAPdf))throw new Error('PDF uploads need the updated FINOVA server. Stop the server with Ctrl+C, run python3 run.py again, then reload this page.');
  $('loading').style.display='block';text('loading',isPDF?'Extracting PDF records for review…':'Reading your financial records…');
  window.FINOVAPdf?.setBusy(true);$('file-input').disabled=true;
  if(isPDF){const started=Date.now();progressTimer=setInterval(()=>{const elapsed=Math.floor((Date.now()-started)/1000);text('loading',`Extracting PDF records for review… ${elapsed}s elapsed. Scanned pages can take longer.`)},1000);}
  const fd=new FormData();fd.append('file',file);if(forceOCR)fd.append('ocr','true');
  const response=await getJSON('/api/upload',{method:'POST',body:fd,timeoutMs:isPDF?75000:45000,timeoutMessage:isPDF?'PDF extraction timed out. Restart FINOVA and try a smaller PDF.':'Upload timed out. Check that FINOVA is running and try again.'});
  if(response.review_required){window.FINOVAPdf.show(response,file);notify('PDF extracted. Check the records and confirm before analysis.')}
  else{window.FINOVAPdf?.clear();applyImport(response.summary,file.name)}
 }catch(e){if($('upload-error')){text('upload-error',e.message);$('upload-error').classList.remove('hidden')}notify(e.message,true)}
 finally{clearInterval(progressTimer);$('loading').style.display='none';$('file-input').value='';window.FINOVAPdf?.setBusy(false);$('file-input').disabled=false;}
}
function askElements(surface){
 const dialog=surface==='dialog';
 return {output:$(dialog?'ask-dialog-answer':'ai-answer'),mode:$(dialog?'ask-dialog-mode':'ai-mode'),
   source:$(dialog?'ask-dialog-source':'ai-source'),input:$(dialog?'ask-dialog-question':'question'),
   submit:$(dialog?'ask-dialog-submit':'ask-submit')};
}
function resetAskSurface(surface){
 askRequestVersions[surface]++;
 const ui=askElements(surface);
 ui.input.value='';ui.submit.disabled=false;ui.output.ariaBusy='false';
 ui.output.textContent='Your financial intelligence assistant is ready.';
 ui.source.textContent='Answers use the uploaded data, not invented transactions.';
 ui.mode.textContent='FINOVA can answer using verified local calculations.';ui.mode.classList.remove('is-local');
}
function resetAskState(){
 resetAskSurface('overview');resetAskSurface('dialog');
 if($('ask-dialog').open)$('ask-dialog').close();
}
function openAskDialog(view,prompt='',autoAsk=false){
 const suggestions={
   anomalies:[['Explain this finding',''],['Review spending changes','Why are our expenses changing?'],['Review overdue invoices','Which customer invoices are overdue?']],
   forecast:[['Upcoming cash risks','What are our biggest upcoming cash-flow risks?'],['Next month outlook','What does the forecast show for next month?'],['Invoice collections','Which customer invoices are overdue?']],
   subscriptions:[['Review subscriptions','What subscriptions should we review?'],['Price increases','Which subscriptions have price increases?'],['Recurring costs','What are our monthly subscription costs?']],
   transactions:[['Expense changes','Why are our expenses changing?'],['Spending categories','Which spending categories changed the most?'],['Cash movements','What are our latest cash receipts and payments?']]
 };
 if(!suggestions[view]||!DATA)return;
 resetAskSurface('dialog');
 const finding=view==='anomalies'?DATA.anomalies.find(a=>a.id===selectedAnomaly):null;
 const findingPrompt=finding?`Explain the ${finding.type.toLowerCase()} for ${finding.category} in ${finding.month} and what we should check.`:'What unusual financial patterns should we review?';
 $('ask-dialog-context').textContent=finding?`${pageInfo[view][0]} · ${finding.category} · ${friendlyMonth(finding.month)}`:pageInfo[view][0];
 $('ask-dialog-description').textContent=finding?'Ask about this finding, its evidence and what to check next. Possible causes require verification.':'Ask about the records on this page. Answers use verified FINOVA figures.';
 $('ask-dialog-suggestions').innerHTML=suggestions[view].map(([label,question])=>`<button type="button" data-dialog-prompt="${escapeHTML(question||findingPrompt)}">${escapeHTML(label)}</button>`).join('');
 $('ask-dialog-question').value=prompt;
 const dialog=$('ask-dialog');
 if(!dialog.open){
   const opener=document.activeElement;
   dialog.show();
   opener?.focus({preventScroll:true});
 }
 if(autoAsk&&prompt)ask(prompt,'dialog');
}
function initAskDialog(){
 const dialog=$('ask-dialog');
 document.querySelectorAll('[data-ask-view]').forEach(button=>button.addEventListener('click',()=>openAskDialog(button.dataset.askView)));
 $('close-ask-dialog').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('close',()=>{if(!dialog.open)askRequestVersions.dialog++;});
 document.addEventListener('keydown',event=>{
   if(event.key==='Escape'&&dialog.open&&!event.defaultPrevented)dialog.close();
 });
 $('ask-dialog-form').addEventListener('submit',event=>{event.preventDefault();ask($('ask-dialog-question').value,'dialog')});
 $('ask-dialog-suggestions').addEventListener('click',event=>{
   const button=event.target.closest('[data-dialog-prompt]');
   if(button){$('ask-dialog-question').value=button.dataset.dialogPrompt;ask(button.dataset.dialogPrompt,'dialog');}
 });
}
async function ask(question,surface='overview'){
 question=String(question).trim().slice(0,500);if(!question||!DATA)return;
 const ui=askElements(surface),version=++askRequestVersions[surface],sourceData=DATA,session=clientSessionVersion;
 const current=()=>version===askRequestVersions[surface]&&sourceData===DATA&&session===clientSessionVersion;
 ui.output.textContent='FINOVA is analyzing the figures…';ui.output.ariaBusy='true';ui.submit.disabled=true;ui.source.textContent='';
 try{
  const res=await getJSON('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});
  if(!current())return;
  ui.output.textContent=res.answer;ui.source.textContent=res.source;
  const mode=ui.mode;
  if(res.mode==='local'){
    mode.textContent=(res.warning?`Akamai unavailable: ${res.warning} `:'')+'Showing evidence-based local analysis.';
    mode.classList.add('is-local');text('ai-connection','FINOVA local analysis active');
  } else {mode.textContent='Akamai AI connected · Answer grounded in verified FINOVA calculations.';mode.classList.remove('is-local');text('ai-connection','Akamai AI connected');}
 }catch(e){if(current())ui.output.textContent='FINOVA could not answer: '+e.message;}
 finally{if(current()){ui.output.ariaBusy='false';ui.submit.disabled=false;}}
}
window.addEventListener('DOMContentLoaded',()=>{
 initAuth();
 initFinancialCards();
 initAskDialog();
 document.querySelectorAll('.nav-link').forEach(b=>b.addEventListener('click',()=>switchPage(b.dataset.view)));
 $('file-input').addEventListener('change',e=>uploadFile(e.target.files[0]));
 window.FINOVAPdf?.init({getJSON,notify,reupload:uploadFile,onImport:applyImport});
 window.FINOVAReports?.init({getJSON,notify});
 $('transaction-search').addEventListener('input',renderTransactions);
 $('view-all-anomalies').addEventListener('click',()=>openAnomaly(null));
 document.querySelectorAll('.anomaly-filter').forEach(b=>b.addEventListener('click',()=>{
  anomalyFilter=b.dataset.filter;selectedAnomaly=null;
  document.querySelectorAll('.anomaly-filter').forEach(x=>x.classList.toggle('active',x===b));renderAnomalies();
 }));
 ['rev-slider','exp-slider'].forEach(id=>$(id).addEventListener('input',updateScenario));
 document.querySelectorAll('#overview [data-prompt]').forEach(b=>b.addEventListener('click',()=>{$('question').value=b.dataset.prompt;ask(b.dataset.prompt)}));
 $('ask-form').addEventListener('submit',e=>{e.preventDefault();let q=$('question').value.trim();if(q)ask(q)});
 window.FINOVAStory.init();
 refreshAuth();
});
