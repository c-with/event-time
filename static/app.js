(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const state = {
    csrf: '', page: 'home', projectId: '', project: null, projectTab: 'overview',
    calendarDate: new Date(), projectSort: 'priority', projectQuery: '', projectPhase: '',
    resourceKind: 'clients', resources: {}, dashboard: null, calendar: null, changes: [],
    modalSubmit: null, searchTimer: null, searchOpen: false,
  };
  const root = $('#page-content');
  const modalRoot = $('#modal-root');
  const toastRoot = $('#toast-root');
  const phaseOptions = ['新登记','筹备执行','现场执行','收尾','已完成','已取消','搁置','已归档'];
  const sessionStatus = ['待排期','日期窗口','暂定','已确认','存在冲突','已完成','已取消'];
  const packageStatus = ['待指派','待确认','准备中','现场执行','待验收','已完成','取消'];
  const requirementStatus = ['待澄清','待确认','已确认','已交付','已验收'];
  const taskStatus = ['待办','进行中','阻塞','待确认/待验收','已完成','取消'];
  const nodeTypes = ['布场','进场','彩排','活动','撤场','交付','截止'];
  const navTitles = {home:'首页总览', projects:'项目台账', resources:'资源总库', changes:'变更待确认'};

  // 主题三态：auto 跟随系统 → light → dark → auto。localStorage key 'theme'，默认 auto；
  // auto 时移除 html[data-theme] 交给 CSS prefers-color-scheme，light/dark 时显式设置。
  // index.html <head> 内有同一逻辑的 inline bootstrap，在样式表加载前先套用（防闪白）。
  const THEME_ORDER = ['auto', 'light', 'dark'];
  const THEME_ICON = {auto: '◐', light: '☀︎', dark: '☾'}; // ☀︎ 强制文字呈现，避免平台渲染成彩色 emoji
  const THEME_LABEL = {auto: '主题：跟随系统', light: '主题：浅色', dark: '主题：深色'};
  function currentTheme() {
    const stored = localStorage.getItem('theme');
    return THEME_ORDER.includes(stored) ? stored : 'auto';
  }
  function applyTheme() {
    const mode = currentTheme();
    if (mode === 'auto') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = mode;
    const button = $('#theme-toggle');
    if (button) { button.textContent = THEME_ICON[mode]; button.title = THEME_LABEL[mode]; }
  }
  function cycleTheme() {
    localStorage.setItem('theme', THEME_ORDER[(THEME_ORDER.indexOf(currentTheme()) + 1) % THEME_ORDER.length]);
    applyTheme();
  }
  applyTheme();
  $('#theme-toggle').addEventListener('click', cycleTheme);

  function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function fmtDate(value, opts = {}) {
    if (!value) return opts.empty || '待排期';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value).slice(0,10);
    return new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai',month:'numeric',day:'numeric', ...(opts.year?{year:'numeric'}:{}), ...(opts.weekday?{weekday:'short'}:{})}).format(d);
  }
  function fmtDateTime(value) {
    if (!value) return '待确认';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value).replace('T',' ').slice(0,16);
    return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);
  }
  const BUSINESS_TZ = 'Asia/Shanghai';
  function businessTimeParts(value) {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return null;
    return Object.fromEntries(new Intl.DateTimeFormat('en-GB',{
      timeZone:BUSINESS_TZ,year:'numeric',month:'2-digit',day:'2-digit',
      hour:'2-digit',minute:'2-digit',hourCycle:'h23'
    }).formatToParts(d).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));
  }
  function fmtDateTimeInput(value) {
    if (!value) return '';
    // A naive datetime-local is already a wall-clock value (no timezone).
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(String(value))) return String(value);
    const p=businessTimeParts(value);
    return p ? `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}` : String(value).slice(0,16);
  }
  function fmtBytes(n) {
    if (!Number.isFinite(Number(n))) return '';
    const v = Number(n);
    if (v < 1024) return `${v} B`;
    if (v < 1024*1024) return `${(v/1024).toFixed(1)} KB`;
    return `${(v/1024/1024).toFixed(1)} MB`;
  }
  function phaseTag(phase) {
    const cls = ({'新登记':'gray','筹备执行':'blue','现场执行':'green','收尾':'orange','已完成':'green','已取消':'gray','搁置':'orange','已归档':'gray'})[phase] || 'gray';
    return `<span class="tag ${cls}">${esc(phase || '未设阶段')}</span>`;
  }
  function statusTag(status) {
    const cls = /逾期|冲突|阻塞|取消|待确认/.test(status || '') ? (/逾期|冲突|阻塞/.test(status || '') ? 'red':'orange') : (/完成|验收|已确认|已交付/.test(status || '') ? 'green':'gray');
    return `<span class="tag ${cls}">${esc(status || '未设置')}</span>`;
  }
  function toast(message, type = '') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    toastRoot.append(el);
    setTimeout(() => el.remove(), 4200);
  }
  function getOperator(promptAgain = false) {
    let name = localStorage.getItem('event-time-operator') || '';
    if (!name || promptAgain) {
      const next = window.prompt(promptAgain ? '请再次确认本次重要操作的操作人姓名' : '请输入本设备操作人姓名（用于记录操作历史）', name);
      if (next === null) return '';
      name = next.trim();
      if (!name) { toast('操作人姓名不能为空', 'warn'); return ''; }
      localStorage.setItem('event-time-operator', name);
    }
    $('#operator-name').textContent = name;
    $('#operator-avatar').textContent = name.slice(0,1).toUpperCase();
    return name;
  }
  function setOperatorDisplay() {
    const name = localStorage.getItem('event-time-operator') || '';
    $('#operator-name').textContent = name || '选择操作人';
    $('#operator-avatar').textContent = name ? name.slice(0,1).toUpperCase() : '?';
  }
  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const isForm = options.body instanceof FormData;
    if (options.body && !isForm && !headers.has('Content-Type')) headers.set('Content-Type','application/json');
    if (state.csrf && options.method && !['GET','HEAD'].includes(options.method.toUpperCase())) headers.set('X-CSRF-Token', state.csrf);
    const operator = localStorage.getItem('event-time-operator') || '';
    if (operator) headers.set('X-Operator-Name', operator);
    const response = await fetch(path, {...options, headers, credentials:'same-origin'});
    const contentType = response.headers.get('content-type') || '';
    let data;
    if (contentType.includes('application/json')) data = await response.json();
    else data = await response.text();
    if (response.status === 401 && path !== '/api/login') showLogin();
    if (!response.ok) {
      const error = new Error(data?.error || `请求失败 (${response.status})`);
      error.status = response.status; error.data = data; throw error;
    }
    return data;
  }
  const json = (method, body) => ({method, body:JSON.stringify(body)});

  function showLogin() {
    $('#app-shell').classList.add('hidden');
    $('#login-screen').classList.remove('hidden');
  }
  function showApp() {
    $('#login-screen').classList.add('hidden');
    $('#app-shell').classList.remove('hidden');
    setOperatorDisplay();
  }
  async function boot() {
    try {
      const me = await api('/api/me');
      if (me.authenticated) {
        state.csrf = me.csrf_token || '';
        showApp();
        await navigateFromHash();
      } else showLogin();
    } catch (e) {
      showLogin();
      if (e.status !== 401) toast(e.message, 'error');
    }
  }
  $('#login-form').addEventListener('submit', async e => {
    e.preventDefault();
    $('#login-error').textContent = '';
    try {
      const result = await api('/api/login', json('POST', {username:$('#login-username').value.trim(),password:$('#login-password').value}));
      state.csrf = result.csrf_token || '';
      $('#login-password').value = '';
      showApp();
      getOperator(false);
      await navigateFromHash();
    } catch (err) { $('#login-error').textContent = err.message; }
  });
  $('#logout-button').addEventListener('click', async () => {
    try { await api('/api/logout', json('POST', {})); } catch (_) {}
    state.csrf = ''; showLogin();
  });
  $('#operator-button').addEventListener('click', () => getOperator(false));
  $('#refresh-button').addEventListener('click', () => refreshPage().catch(e => toast(e.message,'error')));
  $('#top-create-project').addEventListener('click', () => openProjectForm());
  $$('[data-nav]').forEach(button => button.addEventListener('click', () => navigate(button.dataset.nav)));

  async function navigate(page) {
    state.page = page;
    state.projectId = '';
    state.project = null;
    if (page !== 'project-detail') location.hash = page === 'home' ? '#/' : `#/${page}`;
    updateNav();
    await refreshPage();
  }
  async function navigateFromHash() {
    const hash = location.hash || '#/';
    const m = hash.match(/^#\/projects\/([^?]+)(?:\?tab=([^&]+))?/);
    if (m) {
      state.page = 'project-detail'; state.projectId = decodeURIComponent(m[1]); state.projectTab = m[2] || 'overview';
      updateNav(); await loadProject(); return;
    }
    if (hash.includes('resources')) return navigate('resources');
    if (hash.includes('changes')) return navigate('changes');
    if (hash.includes('projects')) return navigate('projects');
    return navigate('home');
  }
  window.addEventListener('hashchange', () => { if (!state.searchOpen) navigateFromHash().catch(e => toast(e.message,'error')); });
  function updateNav() {
    $$('[data-nav]').forEach(b => b.classList.toggle('active', b.dataset.nav === (state.page === 'project-detail' ? 'projects' : state.page)));
    $('#page-title').textContent = state.page === 'project-detail' ? (state.project?.name || '项目执行中心') : navTitles[state.page] || '项目执行中心';
  }
  async function refreshPage() {
    updateNav();
    if (state.page === 'home') return loadHome();
    if (state.page === 'projects') return loadProjects();
    if (state.page === 'project-detail') return loadProject();
    if (state.page === 'resources') return loadResources();
    if (state.page === 'changes') return loadChanges();
  }

  async function loadHome() {
    root.innerHTML = `<div class="page-heading"><div><p class="eyebrow">OVERVIEW / 今日工作台</p><h1>把今天的执行节奏理清楚。</h1><p>项目、场次、交付与待确认事项都从同一份业务数据汇总。</p></div><div class="heading-actions"><button class="btn btn-secondary" data-action="go-projects">查看全部项目 ↗</button><button class="btn btn-primary" data-action="new-project">＋ 新建项目</button></div></div><div class="stat-grid" id="home-stats"></div><div class="dashboard-grid"><section class="panel"><div class="panel-header"><div><h2>排期日历</h2><p>拖动桌面端场次可预览改期；确认后才会保存。</p></div><div class="calendar-toolbar"><button data-action="calendar-prev" aria-label="上个月">‹</button><strong id="calendar-month"></strong><button data-action="calendar-next" aria-label="下个月">›</button><button data-action="calendar-today">今天</button></div></div><div class="panel-body"><div id="calendar-host"></div><div class="calendar-legend"><span><i class="legend-dot"></i>已排期</span><span><i class="legend-dot warn"></i>存在风险</span><span><i class="legend-dot window"></i>择日窗口</span><span>过去项目灰显，未完成风险仍突出</span></div></div></section><div class="right-column"><section class="panel"><div class="panel-header"><div><h2>今日 / 近期执行</h2><p>优先展示时间节点与现场行动</p></div><button class="text-link" data-action="go-projects">项目台账 →</button></div><div class="panel-body"><div id="agenda-host" class="agenda-list"></div></div></section><section class="panel section-gap"><div class="panel-header"><div><h2>需要处理</h2><p>逾期任务与重要变更</p></div><button class="text-link" data-action="go-changes">全部查看 →</button></div><div class="panel-body"><div id="attention-host" class="agenda-list"></div></div></section></div></div>`;
    const [dashboard] = await Promise.all([api('/api/dashboard')]);
    state.dashboard = dashboard;
    $('#home-stats').innerHTML = [
      {label:'进行中的项目',value:dashboard.counts.projects,foot:'当前未归档项目',icon:'▤',cls:''},
      {label:'今日执行节点',value:dashboard.counts.today_nodes,foot:'布场 / 彩排 / 活动 / 交付',icon:'◷',cls:''},
      {label:'逾期任务',value:dashboard.counts.overdue_tasks,foot:'需要尽快处理',icon:'!',cls:'alert'},
      {label:'待确认变更',value:dashboard.counts.pending_changes,foot:'确认前正式值不变',icon:'↻',cls:'warning'},
    ].map(x => `<div class="stat-card ${x.cls}"><div class="stat-top"><span>${x.label}</span><span class="stat-icon">${x.icon}</span></div><div class="stat-number">${x.value ?? 0}</div><div class="stat-foot">${x.foot}</div></div>`).join('');
    renderCalendar(dashboard);
    renderAgenda(dashboard);
    renderAttention(dashboard);
    updateChangeCount(dashboard.counts.pending_changes);
  }
  async function fetchCalendar() {
    const d = new Date(state.calendarDate.getFullYear(), state.calendarDate.getMonth(), 1);
    const start = new Date(d); start.setDate(start.getDate() - ((start.getDay()+6)%7));
    const end = new Date(start); end.setDate(end.getDate()+41);
    const iso = x => `${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
    state.calendar = await api(`/api/calendar?from=${iso(start)}&to=${iso(end)}`);
  }
  function calendarColorClass(session) {
   const identity = String(session.id || session.project_id || '');
   let hash = 2166136261;
   for (let i=0;i<identity.length;i++) { hash ^= identity.charCodeAt(i); hash=Math.imul(hash,16777619); }
   return 'cal-theme-'+((hash>>>0)%12);
  }

  function calendarDateKey(value) {
    if (!value) return '';
    const parts = businessTimeParts(value);
    return parts ? `${parts.year}-${parts.month}-${parts.day}` : String(value).slice(0,10);
  }
  function calendarSessionsOn(key) {
   return (state.calendar?.sessions||[]).filter(s => {
     const from=(s.date_mode==='window'?s.window_start:s.starts_at)||'';
     const to=(s.date_mode==='window'?s.window_end:s.ends_at)||from;
     return from && calendarDateKey(from)<=key && calendarDateKey(to)>=key;
   }).sort((a,b)=>{
     const af=a.date_mode==='window'?a.window_start:a.starts_at;
     const bf=b.date_mode==='window'?b.window_start:b.starts_at;
     return String(af||'').localeCompare(String(bf||''))||String(a.id).localeCompare(String(b.id));
   });
  }

  function calendarNodesOn(key) {
   return (state.calendar?.time_nodes||[]).filter(n=>n.planned_start&&calendarDateKey(n.planned_start)===key)
   .sort((a,b)=>String(a.planned_start).localeCompare(String(b.planned_start)));
  }

  function openDayModal(key) {
   if(!/^\d{4}-\d{2}-\d{2}$/.test(key))return;
   const sessions=calendarSessionsOn(key), nodes=calendarNodesOn(key);
   const parsed=new Date(key+'T12:00:00');
   const heading=Number.isNaN(parsed.getTime())?key:new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'long',day:'numeric',weekday:'long'}).format(parsed);
   const cards=sessions.map(s=>{
     const isWindow=s.date_mode==='window', name=s.project?.name||s.title||'未命名活动';
     const subtitle=s.title&&s.title!==name?s.title:'';
     const timeText=isWindow?'择日窗口：'+fmtDate(s.window_start)+' — '+fmtDate(s.window_end)+'（非连续举办）':fmtDateTime(s.starts_at)+(s.ends_at?' — '+fmtDateTime(s.ends_at):'');
     const venue=s.venue||s.location_text||'地点待确认';
     return `<article class="day-detail-card ${calendarColorClass(s)} ${s.is_past?'past':''}">
       <div class="day-detail-head"><div><strong>${esc(name)}</strong>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div>
       ${statusTag(s.status||'待确认')}</div>
       <p>◷ ${esc(timeText)}</p><p>⌖ ${esc(venue)}</p>
       ${isWindow?'<p class="day-detail-window">择日待定，尚未确认该日举行。</p>':''}
       ${s.has_risk?'<p class="day-detail-risk">⚠ 该项目存在待处理风险</p>':''}
       ${s.notes?`<p class="day-detail-notes">${esc(s.notes)}</p>`:''}
       <button type="button" class="btn btn-secondary" data-action="open-session" data-project-id="${esc(s.project_id)}" data-session-id="${esc(s.id)}">查看项目详情 →</button>
     </article>`;
   }).join('');
   const timeline=nodes.map(n=>`<div class="day-detail-node"><div><strong>${esc(n.node_type||'执行节点')}${n.label&&n.label!==n.node_type?' · '+esc(n.label):''}</strong>
      <p>${esc(n.project_name||'未命名项目')}${n.session_title?' · '+esc(n.session_title):''}</p>
      <p>${esc(n.responsible||'负责人待确认')} · ${esc(n.date_status||n.status||'待确认')}</p></div>
      <span>${esc(fmtDateTime(n.planned_start))}</span></div>`).join('');
   modalRoot.innerHTML=`<div class="modal-backdrop day-detail-backdrop"><section class="modal wide day-detail-modal" role="dialog" aria-modal="true" aria-labelledby="day-detail-title">
   <header class="modal-header"><div><h2 id="day-detail-title">${esc(heading)}</h2><p>${sessions.length} 项活动 · ${nodes.length} 个执行节点</p></div>
   <button type="button" class="modal-close" data-action="close-modal" aria-label="关闭">×</button></header>
   <div class="modal-body day-detail-body"><h3>当天活动 / 择日候选</h3>${cards||'<p class="day-detail-empty">当天暂无活动</p>'}
   <h3>布场、彩排、撤场及其他执行节点</h3>${timeline||'<p class="day-detail-empty">当天暂无执行节点</p>'}</div>
   <footer class="modal-footer"><button type="button" class="btn btn-secondary" data-action="close-modal">关闭</button></footer></section></div>`;
   const close=$('[data-action="close-modal"]',modalRoot);if(close)close.focus();
  }
  async function renderCalendar(dashboard = null) {
    await fetchCalendar();
    const host = $('#calendar-host'); if (!host) return;
    const d = state.calendarDate;
    $('#calendar-month').textContent = `${d.getFullYear()}年 ${d.getMonth()+1}月`;
    const start = new Date(d.getFullYear(), d.getMonth(), 1); start.setDate(start.getDate()-((start.getDay()+6)%7));
    const days = Array.from({length:42}, (_,i) => { const x = new Date(start); x.setDate(start.getDate()+i); return x; });
    const sessions = state.calendar?.sessions || [];
    const weekdays = ['一','二','三','四','五','六','日'];
    const now = new Date(); now.setHours(0,0,0,0);
    let html = `<div class="calendar-grid">${weekdays.map(w=>`<div class="calendar-weekday">${w}</div>`).join('')}`;
    for (const day of days) {
      const key = dateKey(day);
      const todays = calendarSessionsOn(key);
      const nodes = calendarNodesOn(key);
      const visible = todays.slice(0,3);
      html += `<div class="calendar-day ${day.getMonth()!==d.getMonth()?'outside':''} ${dateKey(day)===dateKey(now)?'today':''}" data-date="${key}"><button type="button" class="day-number" data-action="open-day" data-date="${key}" aria-label="查看 ${key} 的 ${todays.length} 项活动">${day.getDate()}</button><div class="day-events">`;
      html += visible.map(s => {
        const isWindow = s.date_mode === 'window';
        const from = calendarDateKey(isWindow?s.window_start:s.starts_at), to = calendarDateKey((isWindow?s.window_end:s.ends_at)||(isWindow?s.window_start:s.starts_at));
        const pos = from === key ? 'start' : to === key ? 'end' : 'middle';
        const cls = `${calendarColorClass(s)} ${isWindow?'window':(s.is_past?'past':'')} ${s.has_risk?'risk':''} ${pos}`;
        const title = `${isWindow?'择日 · ':''}${s.project?.name || s.title}`;
        return `<button draggable="${isWindow?'false':'true'}" class="event-pill ${cls}" title="${esc(title)}" data-action="open-session" data-session-id="${s.id}" data-project-id="${s.project_id}" data-date="${key}" data-start="${esc(s.starts_at||'')}" data-end="${esc(s.ends_at||'')}" data-revision="${s.revision}">${esc(title)}</button>`;
      }).join('');
      if (todays.length>3) html += `<button type="button" class="more-events" data-action="open-day" data-date="${key}">另有 ${todays.length-3} 项，查看全部 →</button>`;
      if (nodes.length) html += `<button type="button" class="day-node-count" data-action="open-day" data-date="${key}">◷ ${nodes.length} 个执行节点</button>`;
      html += `</div></div>`;
    }
    html += `</div>`;
    host.innerHTML = html;
  }
  function dateKey(d) { return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; }
  function renderAgenda(dashboard) {
    const host = $('#agenda-host'); if (!host) return;
    const nodes = dashboard.upcoming_nodes || [];
    if (!nodes.length) { host.innerHTML = emptyHtml('近期暂无已排期节点','补充项目场次和布场、彩排、活动或交付时间。'); return; }
    host.innerHTML = nodes.slice(0,8).map(n => {
      const dt = n.planned_start ? new Date(n.planned_start) : null;
      const day = dt && !Number.isNaN(dt.getTime()) ? dt.getDate() : '—';
      const month = dt && !Number.isNaN(dt.getTime()) ? `${dt.getMonth()+1}月` : '待定';
      return `<div class="agenda-item"><div class="agenda-date"><strong>${day}</strong><small>${month}</small></div><div class="agenda-content"><strong>${esc(n.label)} ${statusTag(n.date_status)}</strong><p>${esc(n.project_name)}${n.session_title?' · '+esc(n.session_title):''}</p><p>${fmtDateTime(n.planned_start)}${n.responsible?' · '+esc(n.responsible):''}</p></div></div>`;
    }).join('');
  }
  function renderAttention(dashboard) {
    const host = $('#attention-host'); if (!host) return;
    const items = [];
    (dashboard.overdue_tasks || []).slice(0,4).forEach(t => items.push({title:t.name,subtitle:`${t.project_id.slice(0,6)} · ${t.owner||'未指定负责人'}`,date:t.due_at,cls:'red',id:t.project_id}));
    (dashboard.pending_changes || []).slice(0,4).forEach(c => items.push({title:`待确认：${c.field_path}`,subtitle:`${c.entity_label} · ${c.proposed_by}`,date:c.created_at,cls:'orange',id:c.entity_id,change:true}));
    if (!items.length) { host.innerHTML = emptyHtml('当前没有紧急事项','新变更和逾期任务会自动显示在这里。'); return; }
    host.innerHTML = items.slice(0,6).map(x => `<div class="agenda-item"><div class="agenda-date"><strong>${x.change?'↻':'!'}</strong><small>${x.change?'变更':'逾期'}</small></div><div class="agenda-content"><strong>${esc(x.title)} <span class="tag ${x.cls}">${x.change?'待确认':'逾期'}</span></strong><p>${esc(x.subtitle)}</p><p>${fmtDateTime(x.date)}</p></div></div>`).join('');
  }
  function emptyHtml(title, text, button = '') {
    return `<div class="empty-state"><div class="empty-icon">＋</div><h3>${esc(title)}</h3><p>${esc(text)}</p>${button}</div>`;
  }

  async function loadProjects() {
    root.innerHTML = `<div class="page-heading"><div><p class="eyebrow">PROJECT REGISTER / 项目总台账</p><h1>项目台账</h1><p>以项目为主线，场次、工作包、需求、任务和资料都从这里进入。</p></div><div class="heading-actions"><button class="btn btn-primary" data-action="new-project">＋ 新建项目</button></div></div><div class="project-toolbar"><label class="search-field"><span>⌕</span><input id="project-query" value="${esc(state.projectQuery)}" placeholder="搜索项目名称、客户、负责人…"></label><select id="project-phase" class="select-control"><option value="">全部项目阶段</option>${phaseOptions.map(x=>`<option ${state.projectPhase===x?'selected':''}>${x}</option>`).join('')}</select><select id="project-sort" class="select-control"><option value="priority" ${state.projectSort==='priority'?'selected':''}>默认：风险与近期优先</option><option value="date" ${state.projectSort==='date'?'selected':''}>按场次日期</option><option value="updated" ${state.projectSort==='updated'?'selected':''}>按最近更新</option><option value="name" ${state.projectSort==='name'?'selected':''}>按项目名称</option><option value="client" ${state.projectSort==='client'?'selected':''}>按客户</option><option value="owner" ${state.projectSort==='owner'?'selected':''}>按负责人</option><option value="phase" ${state.projectSort==='phase'?'selected':''}>按项目阶段</option></select><button class="btn btn-secondary" data-action="show-archived">查看归档</button></div><div id="project-list" class="project-list"></div>`;
    $('#project-query').addEventListener('input', e => { state.projectQuery = e.target.value; clearTimeout(state.searchTimer); state.searchTimer=setTimeout(fetchProjectRows,220); });
    $('#project-phase').addEventListener('change', e => { state.projectPhase=e.target.value; fetchProjectRows(); });
    $('#project-sort').addEventListener('change', e => { state.projectSort=e.target.value; fetchProjectRows(); });
    await fetchProjectRows();
  }
  async function fetchProjectRows(archived = false) {
    const list = $('#project-list'); if (!list) return;
    try {
      const params = new URLSearchParams({q:state.projectQuery,sort:state.projectSort});
      if (state.projectPhase) params.set('phase',state.projectPhase);
      if (archived) params.set('archived','1');
      const data = await api(`/api/projects?${params}`);
      if (!data.projects.length) { list.innerHTML=emptyHtml('还没有符合条件的项目',state.projectQuery?'尝试换一个关键词。':'新建项目后，场次、工作包、任务和文件都可以归入同一项目。','<button class="btn btn-primary" data-action="new-project">＋ 新建项目</button>'); return; }
      list.innerHTML = data.projects.map(renderProjectCard).join('');
    } catch (e) { list.innerHTML=emptyHtml('项目列表加载失败',e.message,'<button class="btn btn-secondary" data-action="retry">重试</button>'); }
  }
  function renderProjectCard(p) {
    const next = p.next_session;
    const cover = p.cover_url ? `<img src="${esc(p.cover_url)}" alt="项目主图">` : `<span>ET</span><span class="cover-mark">PROJECT</span>`;
    return `<article class="project-card"><div class="project-cover">${cover}</div><div class="project-info"><div class="project-title-row"><h3 data-action="open-project" data-id="${p.id}">${esc(p.name)}</h3>${phaseTag(p.phase)}</div><div class="project-subline"><span>◉ ${esc(p.client||'客户待补')}</span><span>♙ ${esc(p.owner||'负责人待定')}</span><span>▦ ${p.session_count} 个场次</span></div><div class="project-next">↳ <span>${p.next_action ? `${esc(p.next_action.label)}${p.next_action.due_at?' · '+fmtDateTime(p.next_action.due_at):''}` : '补充下一项执行行动'}</span></div><div class="project-risk">${(p.risks||[]).slice(0,3).map(r=>`<span class="tag ${r.code==='overdue'||r.code==='pending_change'?'red':'orange'}">${esc(r.label)}</span>`).join('')}</div></div><div class="project-actions"><button class="btn btn-secondary" data-action="open-project" data-id="${p.id}">进入执行中心 ↗</button><span class="tiny muted">更新于 ${fmtDate(p.updated_at,{year:true})}</span></div></article>`;
  }

  async function loadProject() {
    if (!state.projectId) return navigate('projects');
    root.innerHTML = `<div class="empty-state"><div class="empty-icon">…</div><h3>正在打开项目</h3><p>加载场次、任务和文件关联。</p></div>`;
    try {
      const data = await api(`/api/projects/${encodeURIComponent(state.projectId)}`);
      state.project = data.project;
      $('#page-title').textContent = state.project.name;
      renderProjectDetail();
      const changes = await api('/api/change-requests');
      updateChangeCount(changes.changes.length);
    } catch (e) { root.innerHTML=emptyHtml('无法打开项目',e.message,'<button class="btn btn-secondary" data-action="go-projects">返回项目台账</button>'); }
  }
  function renderProjectDetail() {
    const p = state.project; if (!p) return;
    const tabs = [
      ['overview','项目总览',null],['schedule','场次与时间',p.sessions.length+p.time_nodes.length],['packages','执行工作包',p.work_packages.length],
      ['requirements','需求清单',p.requirements.length],['tasks','执行任务',p.tasks.length],['files','文件资料',p.documents.length],['changes','变更与归档',p.change_requests.length],
    ];
    const cover = p.cover_url ? `<img src="${esc(p.cover_url)}" alt="项目主图">` : 'ET';
    root.innerHTML = `<div class="page-heading"><div><p class="eyebrow">PROJECT / EXECUTION CENTER</p><h1>项目执行中心</h1><p>在同一项目上下文内推进排期、工作包、需求、任务和资料。</p></div><div class="heading-actions"><button class="btn btn-secondary" data-action="go-projects">← 项目台账</button></div></div>
      <section class="project-detail-head"><div class="detail-cover">${cover}</div><div class="detail-main"><div class="project-title-row">${phaseTag(p.phase)}${p.risks?.length?`<span class="tag red">${p.risk_count} 项风险/待办</span>`:''}</div><h1>${esc(p.name)}</h1><p>${esc(p.description||'尚未填写项目说明。')}</p><div class="detail-meta"><span>客户：${esc(p.client||'待补')}</span><span>负责人：${esc(p.owner||'待指定')}</span><span>场次：${p.session_count}</span><span>最近更新：${fmtDateTime(p.updated_at)}</span></div></div><div class="detail-actions"><button class="btn btn-secondary" data-action="edit-project">编辑项目</button><button class="btn btn-secondary" data-action="upload-project-file">上传资料</button><button class="btn btn-primary" data-action="new-task">＋ 新任务</button></div></section>
      <div class="tab-bar">${tabs.map(([id,label,count])=>`<button class="tab-button ${state.projectTab===id?'active':''}" data-action="project-tab" data-tab="${id}">${label}${count!==null?`<span class="tab-count">${count}</span>`:''}</button>`).join('')}</div>
      <div id="project-tab-content"></div>`;
    const content = $('#project-tab-content');
    if (state.projectTab==='overview') content.innerHTML=renderOverview(p);
    if (state.projectTab==='schedule') content.innerHTML=renderSchedule(p);
    if (state.projectTab==='packages') content.innerHTML=renderPackages(p);
    if (state.projectTab==='requirements') content.innerHTML=renderRequirements(p);
    if (state.projectTab==='tasks') content.innerHTML=renderTasks(p);
    if (state.projectTab==='files') content.innerHTML=renderFiles(p);
    if (state.projectTab==='changes') content.innerHTML=renderProjectChanges(p);
  }
  function renderOverview(p) {
    const next = p.next_session;
    const risk = (p.risks||[]).map(r=>`<div class="summary-row"><span>${esc(r.label)}</span><strong>${r.count}</strong></div>`).join('') || `<div class="summary-row"><span>风险状态</span><strong>当前没有系统识别的紧急风险</strong></div>`;
    const nodes = [...(p.time_nodes||[])].sort((a,b)=>(a.planned_start||'').localeCompare(b.planned_start||'')).slice(0,8);
    const recentTasks = [...(p.tasks||[])].filter(t=>t.status!=='已完成'&&t.status!=='取消').sort((a,b)=>(a.due_at||'9999').localeCompare(b.due_at||'9999')).slice(0,6);
    return `<div class="detail-grid"><div class="entity-list"><section class="summary-box"><h3>项目关键事实</h3><div class="summary-row"><span>客户</span><strong>${esc(p.client||'待补充')}</strong></div><div class="summary-row"><span>主要负责人</span><strong>${esc(p.owner||'待指定')}</strong></div><div class="summary-row"><span>下一场活动</span><strong>${next?`${esc(next.title)} · ${fmtDateTime(next.starts_at)}`:'暂未排期'}</strong></div><div class="summary-row"><span>项目主图</span><strong>${p.cover_document_id?'已设置':'使用统一占位图'}</strong></div><div class="summary-row"><span>系统内部 ID</span><strong class="muted">${esc(p.id)}</strong></div><div class="entity-actions" style="margin-top:12px"><button data-action="new-session" class="primary-mini">＋ 添加场次</button><button data-action="new-package">＋ 添加工作包</button><button data-action="new-requirement">＋ 添加需求项</button></div></section><section class="summary-box"><h3>近期执行时间轴</h3>${nodes.length?`<div class="timeline">${nodes.map(n=>`<div class="timeline-item"><span class="timeline-dot"></span><div class="timeline-time">${fmtDateTime(n.planned_start)}</div><strong>${esc(n.label)} ${statusTag(n.date_status)}</strong><p>${esc(n.responsible||'责任方待指定')}${n.source_text?' · 来源：'+esc(n.source_text):''}</p></div>`).join('')}</div>`:emptyHtml('暂无时间节点','添加布场、彩排、活动、撤场、交付或截止节点。','<button class="btn btn-secondary" data-action="new-node">＋ 添加时间节点</button>')}</section></div><div class="entity-list"><section class="summary-box"><h3>风险与待确认</h3>${risk}<div class="entity-actions" style="margin-top:12px"><button data-action="project-tab" data-tab="changes">查看变更与历史 →</button></div></section><section class="summary-box"><h3>下一步执行任务</h3>${recentTasks.length?recentTasks.map(t=>`<div class="summary-row"><span>${esc(t.name)}</span><strong>${t.due_at?fmtDateTime(t.due_at):'无截止日期'} ${statusTag(t.status)}</strong></div>`).join(''):emptyHtml('暂无执行任务','将需求转化为可跟进的具体动作。','<button class="btn btn-secondary" data-action="new-task">＋ 添加任务</button>')}</section><section class="summary-box"><h3>归档准备</h3><p class="muted" style="font-size:10px;line-height:1.7">归档前请核对交付文件、现场照片、供应商履约和未完成任务。系统不会因活动日期到达自动归档。</p><div class="entity-actions"><button data-action="archive-project">确认归档项目</button></div></section></div></div>`;
  }
  function renderSchedule(p) {
    const sessions = p.sessions || [];
    return `<div class="page-heading"><div><h2 style="font-size:15px;margin:0">场次与时间节点</h2><p>同一个项目可以包含多个场次；布场、彩排、活动、撤场等节点分别记录。</p></div><div class="heading-actions"><button class="btn btn-secondary" data-action="new-node">＋ 时间节点</button><button class="btn btn-primary" data-action="new-session">＋ 新建场次</button></div></div><div class="entity-list">${sessions.length?sessions.map(s=>`<article class="entity-card"><div class="entity-card-header"><div><h3>${esc(s.title)}</h3><p>${s.date_mode==='window'?`择日窗口：${fmtDate(s.window_start)} — ${fmtDate(s.window_end)}`:`${fmtDateTime(s.starts_at)} — ${fmtDateTime(s.ends_at)}`}</p><p>场地：${esc(s.venue||s.location_text||'待确认')}</p></div><div class="entity-actions"><button data-action="edit-session" data-id="${s.id}">编辑场次</button><button data-action="reschedule-session" data-id="${s.id}">预览改期</button><button data-action="new-node" data-session-id="${s.id}">＋ 时间节点</button></div></div><div class="entity-meta">${statusTag(s.status)}<span class="tag gray">${s.date_mode==='window'?'择日窗口':s.date_mode==='undated'?'日期待定':'固定排期'}</span><span class="tag gray">${s.time_nodes.length} 个节点</span></div>${s.notes?`<p>${esc(s.notes)}</p>`:''}</article>`).join(''):emptyHtml('项目尚无场次','纯物料项目可以没有场次；活动项目可先建草稿，不必编造日期。','<button class="btn btn-primary" data-action="new-session">＋ 新建场次</button>')}</div><section class="panel section-gap"><div class="panel-header"><div><h2>项目时间节点</h2><p>固定节点同时显示图标和文字，时间未确认时保留待确认状态。</p></div></div><div class="panel-body"><div class="entity-list">${p.time_nodes.length?p.time_nodes.map(n=>renderNodeCard(n)).join(''):emptyHtml('暂无时间节点','可以添加多批进场、多次彩排和独立交付节点。','<button class="btn btn-secondary" data-action="new-node">＋ 添加时间节点</button>')}</div></div></section>`;
  }
  function renderNodeCard(n) {
    const icons={'布场':'⚒','进场':'↘','彩排':'♫','活动':'⚑','撤场':'⇢','交付':'✓','截止':'◷'};
    return `<article class="entity-card"><div class="entity-card-header"><div><h3>${icons[n.node_type]||'◷'} ${esc(n.label)}</h3><p>${fmtDateTime(n.planned_start)}${n.planned_end?' — '+fmtDateTime(n.planned_end):''}</p><p>${esc(n.responsible||'责任方待指定')}${n.source_text?' · 来源：'+esc(n.source_text):''}</p></div><div class="entity-actions"><button data-action="edit-node" data-id="${n.id}">编辑</button></div></div><div class="entity-meta">${statusTag(n.status)}${statusTag(n.date_status)}<span class="tag gray">${n.move_rule==='follow_session'?'跟随场次改期':'固定承诺'}</span></div>${n.notes?`<p>${esc(n.notes)}</p>`:''}</article>`;
  }
  function renderPackages(p) {
    return `<div class="page-heading"><div><h2 style="font-size:15px;margin:0">执行工作包</h2><p>把 LED、舞台、音响灯光、印刷等独立分派；供应商暂未确定也可以先建工作包。</p></div><div class="heading-actions"><button class="btn btn-primary" data-action="new-package">＋ 新建工作包</button></div></div><div class="entity-list">${p.work_packages.length?p.work_packages.map(w=>`<article class="entity-card"><div class="entity-card-header"><div><h3>${esc(w.name)}</h3><p>${esc(w.description||w.responsibility||'尚未填写工作范围。')}</p></div><div class="entity-actions"><button data-action="edit-package" data-id="${w.id}">编辑工作包</button></div></div><div class="entity-meta">${statusTag(w.status)}<span class="tag gray">供应商：${esc(w.supplier||w.contact_snapshot||'待指派')}</span><span class="tag gray">${p.requirements.filter(r=>r.work_package_id===w.id).length} 项需求</span><span class="tag gray">${p.tasks.filter(t=>t.work_package_id===w.id).length} 项任务</span></div>${w.acceptance_criteria?`<p>验收标准：${esc(w.acceptance_criteria)}</p>`:''}</article>`).join(''):emptyHtml('还没有执行工作包','按交付责任拆分工作包；供应商确定后再绑定。','<button class="btn btn-primary" data-action="new-package">＋ 新建工作包</button>')}</div>`;
  }
  function renderRequirements(p) {
    return `<div class="page-heading"><div><h2 style="font-size:15px;margin:0">需求清单</h2><p>记录真正需要的物件或服务，与“催名单、打样、运输、安装”等执行任务分开。</p></div><div class="heading-actions"><button class="btn btn-primary" data-action="new-requirement">＋ 新增需求项</button></div></div><div class="entity-list">${p.requirements.length?p.requirements.map(r=>`<article class="entity-card"><div class="entity-card-header"><div><h3>${esc(r.name)}</h3><p>${esc(r.specification||'规格待确认')}${r.dimensions?' · 尺寸 '+esc(r.dimensions)+esc(r.dimension_unit):''}</p><p>数量：${esc(r.quantity_text||'待确认')} ${esc(r.quantity_unit||'')} · 用途/位置：${esc(r.intended_use||r.location_text||'待补')}</p></div><div class="entity-actions"><button data-action="edit-requirement" data-id="${r.id}">编辑需求</button></div></div><div class="entity-meta">${statusTag(r.status)}<span class="tag gray">工作包：${esc(r.work_package||'待分派')}</span><span class="tag gray">负责人：${esc(r.owner||'待指定')}</span><span class="tag gray">交付数量：${esc(r.delivered_quantity_text||'待登记')}</span></div>${r.acceptance_criteria?`<p>验收要求：${esc(r.acceptance_criteria)}</p>`:''}${r.source_text?`<p>来源原文：${esc(r.source_text)}</p>`:''}</article>`).join(''):emptyHtml('还没有需求清单项','把客户真正需要的物件或服务登记下来，未明确内容可保留待确认。','<button class="btn btn-primary" data-action="new-requirement">＋ 新增需求项</button>')}</div>`;
  }
  function renderTasks(p) {
    const tasks = [...p.tasks].sort((a,b)=>(a.due_at||'9999').localeCompare(b.due_at||'9999'));
    return `<div class="page-heading"><div><h2 style="font-size:15px;margin:0">执行任务</h2><p>任务可以绑定需求项，也可以是协调进场、催名单、确认定稿等独立动作；依赖不允许形成循环。</p></div><div class="heading-actions"><button class="btn btn-primary" data-action="new-task">＋ 新增任务</button></div></div><div class="entity-list">${tasks.length?tasks.map(t=>`<article class="entity-card"><div class="entity-card-header"><div><h3>${esc(t.name)}</h3><p>${esc(t.work_package||'未分派工作包')} · ${esc(t.owner||'负责人待定')} ${t.responsible_party?'· '+esc(t.responsible_party):''}</p><p>计划开始：${fmtDateTime(t.planned_start)} · 截止：${fmtDateTime(t.due_at)}${t.duration_days?` · 工期 ${t.duration_days} 天`:''}</p></div><div class="entity-actions"><button data-action="edit-task" data-id="${t.id}">编辑任务</button><button data-action="cycle-task" data-id="${t.id}">${t.status==='已完成'?'重新打开':'标记完成'}</button></div></div><div class="entity-meta">${statusTag(t.status)}${t.is_overdue?'<span class="tag red">逾期</span>':''}${t.needs_review?'<span class="tag orange">需要复核</span>':''}<span class="tag gray">${t.dependencies.length} 项前置依赖</span><span class="tag gray">${t.requirement_ids.length} 项关联需求</span></div>${t.notes?`<p>${esc(t.notes)}</p>`:''}${t.dependencies.length?`<p>前置：${t.dependencies.map(d=>esc(d.depends_on_name||d.depends_on_task_id.slice(0,8))).join('、')}</p>`:''}</article>`).join(''):emptyHtml('还没有执行任务','把需求拆成能明确负责人、截止时间和完成证据的动作。','<button class="btn btn-primary" data-action="new-task">＋ 新增任务</button>')}</div>`;
  }
  function renderFiles(p) {
    return `<div class="page-heading"><div><h2 style="font-size:15px;margin:0">文件与版本</h2><p>项目、场次、工作包和任务的附件使用同一文件库；正式 PDF 保留原件，图片压缩成功后只保留压缩版和缩略图。</p></div><div class="heading-actions"><button class="btn btn-primary" data-action="upload-project-file">＋ 上传文件</button></div></div>${p.documents.length?`<div class="file-grid">${p.documents.map(d=>renderFileCard(d)).join('')}</div>`:emptyHtml('项目还没有关联文件','上传主 KV、流程单、定稿 PDF、现场照片或交付凭证。','<button class="btn btn-primary" data-action="upload-project-file">＋ 上传项目文件</button>')}`;
  }
  function renderFileCard(d) {
    const image = d.mime_type?.startsWith('image/');
    const preview = image ? `<img src="${esc(d.thumbnail_url||d.preview_url)}" alt="">` : `<span>${d.mime_type==='application/pdf'?'PDF':'FILE'}</span>`;
    return `<article class="file-card"><div class="file-preview">${preview}</div><div class="file-info"><div class="file-name">${esc(d.original_name)}</div><div class="file-meta">${esc(d.category)} · V${d.version_no} · ${fmtBytes(d.stored_size)}</div><div class="file-meta">${d.is_official?'<span class="tag green">正式文件</span>':''}${fmtDate(d.created_at,{year:true})}</div><div class="file-actions"><button data-action="preview-file" data-id="${d.id}">预览</button><button data-action="download-file" data-id="${d.id}">下载</button><button data-action="set-project-cover" data-id="${d.id}">设为主图</button><button data-action="share-file" data-id="${d.id}">分享</button></div></div></article>`;
  }
  function renderProjectChanges(p) {
    const changes = p.change_requests || [];
    const audit = p.audit || [];
    return `<div class="page-heading"><div><h2 style="font-size:15px;margin:0">变更与归档</h2><p>重要字段先提案，确认前正式值不变；历史恢复通过新变更完成，不删除审计记录。</p></div><div class="heading-actions"><button class="btn btn-secondary" data-action="archive-project">确认归档项目</button></div></div><div class="entity-list">${changes.length?changes.map(renderChangeCard).join(''):emptyHtml('没有待处理的项目变更','重要字段的变更提案会在这里显示。')}<section class="panel section-gap"><div class="panel-header"><div><h2>操作历史</h2><p>只追加记录，不直接修改历史内容。</p></div></div><div class="panel-body"><div class="timeline">${audit.length?audit.map(a=>`<div class="timeline-item"><span class="timeline-dot"></span><div class="timeline-time">${fmtDateTime(a.created_at)} · ${esc(a.actor)}</div><strong>${esc(a.action)}</strong><p>${esc(JSON.stringify(a.after||{}))}</p>${a.before?`<p>修改前：${esc(JSON.stringify(a.before))}</p>`:''}<div class="entity-actions" style="margin-top:6px"><button data-action="restore-audit" data-id="${a.id}">按此记录恢复</button></div></div>`).join(''):'<p class="muted">暂无操作历史。</p>'}</div></div></section></div>`;
  }
  function renderChangeCard(c) {
    return `<article class="change-card"><div class="change-mark">↻</div><div><h3>${esc(c.entity_label)} · ${esc(c.field_path)} ${statusTag(c.status==='conflict'?'冲突待处理':'待确认')}</h3><p>提出人：${esc(c.proposed_by)} · ${fmtDateTime(c.created_at)}${c.source_text?' · 来源：'+esc(c.source_text):''}</p><div class="change-values"><div class="change-value"><small>当前正式值 / 提案旧值</small><strong>${esc(valueLabel(c.old_value))}</strong></div><div class="change-value"><small>拟变更为</small><strong>${esc(valueLabel(c.new_value))}</strong></div></div>${c.resolution_note?`<p>${esc(c.resolution_note)}</p>`:''}</div><div class="change-actions"><button class="approve" data-action="confirm-change" data-id="${c.id}">确认</button><button data-action="reject-change" data-id="${c.id}">驳回</button></div></article>`;
  }
  function valueLabel(v) { if (v === null || v === '') return '（空）'; if (typeof v === 'object') return JSON.stringify(v); return String(v); }

  async function loadResources() {
    root.innerHTML = `<div class="page-heading"><div><p class="eyebrow">MASTER DATA / 跨项目复用</p><h1>资源总库</h1><p>客户、供应商与联系人、场地空间、固定设备独立维护，历史项目保留本次使用事实。</p></div><div class="heading-actions"><button class="btn btn-primary" data-action="new-resource">＋ 新建资源</button></div></div><div class="resource-tabs">${[['clients','客户'],['suppliers','供应商'],['contacts','联系人'],['venues','场地'],['venue_spaces','场地空间'],['equipment','固定设备']].map(([k,l])=>`<button class="resource-tab ${state.resourceKind===k?'active':''}" data-action="resource-tab" data-kind="${k}">${l}</button>`).join('')}</div><div class="project-toolbar"><label class="search-field"><span>⌕</span><input id="resource-query" placeholder="搜索当前资源类型…"></label><span class="tiny muted">资源主档更新不会静默改写历史项目记录。</span></div><div id="resource-list" class="resource-grid"></div>`;
    $('#resource-query').addEventListener('input', e => { clearTimeout(state.searchTimer); state.searchTimer=setTimeout(()=>fetchResources(e.target.value),200); });
    await fetchResources();
  }
  async function fetchResources(q='') {
    const host = $('#resource-list'); if (!host) return;
    try {
      const data = await api(`/api/resources/${state.resourceKind}${q?`?q=${encodeURIComponent(q)}`:''}`);
      state.resources[state.resourceKind] = data.resources;
      if (!data.resources.length) { host.className=''; host.innerHTML=emptyHtml('暂无资源记录','添加后即可在项目和工作包中复用。','<button class="btn btn-primary" data-action="new-resource">＋ 新建资源</button>'); return; }
      host.className='resource-grid';
      const icons={clients:'◉',suppliers:'▦',contacts:'♙',venues:'⌂',venue_spaces:'▤',equipment:'⚙'};
      host.innerHTML=data.resources.map(r=>`<article class="resource-card"><div class="resource-icon">${icons[state.resourceKind]||'▦'}</div><h3>${esc(r.name)}</h3><p>${esc(r.address||r.service_category||r.role||r.space||r.space_type||r.category||r.notes||r.details||'尚未补充说明')}</p>${r.phone?`<p>电话：${esc(r.phone)}</p>`:''}${r.email?`<p>邮箱：${esc(r.email)}</p>`:''}${r.verified_status?`<div class="entity-meta">${statusTag(r.verified_status)}</div>`:''}<div class="entity-actions" style="margin-top:12px"><button data-action="edit-resource" data-id="${r.id}">编辑</button><button data-action="upload-resource-file" data-id="${r.id}">附件</button></div></article>`).join('');
    } catch(e) { host.innerHTML=emptyHtml('资源加载失败',e.message,'<button class="btn btn-secondary" data-action="retry">重试</button>'); }
  }
  async function loadChanges() {
    root.innerHTML = `<div class="page-heading"><div><p class="eyebrow">CHANGE CONTROL / 审核与追溯</p><h1>变更待确认</h1><p>重要字段提案在确认前不替换正式值；冲突字段需要重新核对，不允许静默覆盖。</p></div><div class="heading-actions"><button class="btn btn-secondary" data-action="refresh-changes">刷新列表</button></div></div><div id="changes-list" class="entity-list"></div>`;
    const data = await api('/api/change-requests'); state.changes = data.changes; updateChangeCount(data.changes.length);
    $('#changes-list').innerHTML = data.changes.length ? data.changes.map(renderChangeCard).join('') : emptyHtml('当前没有待确认变更','项目、排期、规格或关键期限发生重要变更时，会先在这里等待处理。');
  }
  function updateChangeCount(n) {
    const badge = $('#nav-change-count');
    badge.textContent = n;
    badge.classList.toggle('hidden', !n);
  }

  function openModal({title,subtitle='',fields=[],initial={},submitLabel='保存',wide=false,note='',noteType='',onSubmit}) {
    modalRoot.innerHTML = `<div class="modal-backdrop"><section class="modal ${wide?'wide':''}" role="dialog" aria-modal="true"><header class="modal-header"><div><h2>${esc(title)}</h2>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div><button type="button" class="modal-close" data-action="close-modal">×</button></header><form id="active-modal-form"><div class="modal-body">${note?`<div class="modal-note ${noteType}">${esc(note)}</div>`:''}<div class="form-grid">${fields.map(f=>fieldHtml(f,initial[f.name])).join('')}</div><p class="form-error" id="modal-error"></p></div><footer class="modal-footer"><button type="button" class="btn btn-secondary" data-action="close-modal">取消</button><button type="submit" class="btn btn-primary">${esc(submitLabel)}</button></footer></form></section></div>`;
    const form = $('#active-modal-form');
    const activeBackdrop = modalRoot.querySelector('.modal-backdrop');
    form.dataset.initialSnapshot = JSON.stringify([...new FormData(form).entries()]);
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const button = $('button[type="submit"]',form); button.disabled=true; button.textContent='保存中…';
      const payload = {};
      fields.forEach(f => {
        const input = $(`[name="${CSS.escape(f.name)}"]`,form);
        if (!input) return;
        if (f.type==='checkbox') payload[f.name]=input.checked;
        else if (f.multiple) payload[f.name]=[...input.selectedOptions].map(o=>o.value).filter(Boolean);
        else payload[f.name]=input.value;
      });
      try {
        await onSubmit(payload);
        // A multi-step action may have opened a *new* confirmation modal.
        // Never destroy that new modal as part of the old form's completion.
        if (modalRoot.contains(activeBackdrop)) closeModal();
      } catch(err) {
        if (modalRoot.contains(activeBackdrop)) {
          $('#modal-error').textContent=err.message;
          button.disabled=false;
          button.textContent=submitLabel;
        } else toast(err.message||'操作失败','error');
      }
    });
    activeBackdrop.addEventListener('click', e => { if (e.target === activeBackdrop) requestCloseModal(); });
    const first = $('input:not([type=hidden]),select,textarea',form); if (first) setTimeout(()=>first.focus(),50);
  }
  function fieldHtml(f, initialValue) {
    const val = initialValue ?? f.value ?? '';
    const full = f.full || f.type==='textarea';
    let input = '';
    if (f.type === 'textarea') input = `<textarea name="${esc(f.name)}" ${f.required?'required':''} placeholder="${esc(f.placeholder||'')}">${esc(val)}</textarea>`;
    else if (f.type === 'select') {
      const values = f.options || [];
      input = `<select name="${esc(f.name)}" ${f.required?'required':''} ${f.multiple?'multiple size="4"':''}><option value="">${esc(f.placeholder||'请选择')}</option>${values.map(o=>{const value=typeof o==='string'?o:o.value;const label=typeof o==='string'?o:o.label;const selected=f.multiple?(Array.isArray(val)&&val.includes(value)):String(val)===String(value);return `<option value="${esc(value)}" ${selected?'selected':''}>${esc(label)}</option>`}).join('')}</select>`;
    } else if (f.type==='checkbox') input = `<label style="display:flex;align-items:center;gap:8px;font-weight:500"><input style="width:auto" type="checkbox" name="${esc(f.name)}" ${val?'checked':''}>${esc(f.checkboxLabel||f.label)}</label>`;
    else input = `<input name="${esc(f.name)}" type="${esc(f.type||'text')}" value="${esc(f.type==='datetime-local'?fmtDateTimeInput(val):val)}" ${f.required?'required':''} ${f.placeholder?`placeholder="${esc(f.placeholder)}"`:''} ${f.min?`min="${esc(f.min)}"`:''} ${f.step?`step="${esc(f.step)}"`:''}>`;
    return `<div class="form-field ${full?'full':''}"><label>${esc(f.label)}${f.required?' *':''}</label>${input}${f.hint?`<span class="hint">${esc(f.hint)}</span>`:''}</div>`;
  }
  function closeModal() { modalRoot.innerHTML=''; }
  function requestCloseModal() {
    const form = $('#active-modal-form', modalRoot);
    if (form && form.dataset.initialSnapshot !== JSON.stringify([...new FormData(form).entries()])) {
      if (!window.confirm('当前修改还没有保存，确认放弃吗？')) return;
    }
    closeModal();
  }
  function confirmModal(title, message, onConfirm, options={}) {
    openModal({title,subtitle:options.subtitle||'',wide:options.wide||false,note:message,noteType:options.noteType||'warning',submitLabel:options.submitLabel||'确认执行',fields:options.fields||[],initial:options.initial||{},onSubmit:async values=>{if(options.requireOperator!==false&&!getOperator(true)) throw new Error('已取消：未确认操作人'); await onConfirm(values);}});
  }
  function resourceOptions(kind, label='请选择') {
    return [{value:'',label} , ...((state.resources[kind]||[]).map(x=>({value:x.id,label:x.name})))];
  }
  async function ensureResource(kind) {
    if (!state.resources[kind]) { const data=await api(`/api/resources/${kind}`); state.resources[kind]=data.resources; }
    return state.resources[kind];
  }
  async function openProjectForm(project=null) {
    await ensureResource('clients');
    const fields=[{name:'name',label:'项目名称',required:true,full:true},{name:'client_id',label:'客户',type:'select',options:resourceOptions('clients','暂不指定客户')},{name:'owner',label:'主要负责人',placeholder:'例如 JC / 任雪'},{name:'phase',label:'项目阶段',type:'select',options:phaseOptions},{name:'description',label:'项目说明',type:'textarea',full:true,placeholder:'记录项目范围、交付边界或待确认事项'}];
    openModal({title:project?'编辑项目基本信息':'新建项目',subtitle:project?'项目内部 ID 保持不变；重要字段变更会进入待确认流程。':'项目可先建草稿；日期、场地或供应商未定不会阻止登记。',fields,initial:project?{...project,client_id:project.client_id||'',phase:project.phase||'新登记'}:{phase:'新登记'},submitLabel:project?'保存修改':'建立项目',note:project?'名称、客户或项目阶段属于重要字段，保存后会生成变更提案，正式值在确认前保持不变。':'系统会生成稳定的内部 ID。若名称重复，会提示你确认，不会自动合并。',onSubmit:async values=>{
      if (!values.name.trim()) throw new Error('项目名称不能为空');
      if (project) {
        const data=await api(`/api/projects/${project.id}`,json('PATCH',{...values,_revision:project.revision,source_text:'项目基本信息编辑'}));
        if (data.proposed_changes?.length) toast(`已提交 ${data.proposed_changes.length} 项重要变更，需在“变更与归档”中确认。`,'warn');
        else toast('项目资料已保存');
        await loadProject();
      } else {
        try {
          const data=await api('/api/projects',json('POST',values));
          state.projectId=data.project.id; state.page='project-detail'; state.projectTab='overview'; location.hash=`#/projects/${data.project.id}`;
          toast('项目已建立'); await loadProject();
        } catch(err) {
          if (err.status===409 && err.data?.duplicate_candidates) {
            const candidates=err.data.duplicate_candidates.map(x=>`${x.name}（${x.client||'客户待补'} · ${x.owner||'负责人待补'}）`).join('\n');
            if (!window.confirm(`发现名称相同的项目：\n${candidates}\n\n确认仍然新建一个独立项目？系统不会自动合并。`)) throw new Error('已取消新建');
            const data=await api('/api/projects',json('POST',{...values,force_create:true}));
            state.projectId=data.project.id; state.page='project-detail'; state.projectTab='overview'; location.hash=`#/projects/${data.project.id}`;
            toast('已按你的确认建立独立项目'); await loadProject();
          } else throw err;
        }
      }
    }});
  }
  async function openSessionForm(session=null) {
    const p=state.project; if (!p) return;
    await ensureResource('venue_spaces');
    const fields=[{name:'title',label:'场次名称',required:true,full:true},{name:'date_mode',label:'排期方式',type:'select',options:[{value:'fixed',label:'固定日期'},{value:'window',label:'择日窗口'},{value:'undated',label:'日期待定'}]},{name:'status',label:'排期状态',type:'select',options:sessionStatus},{name:'starts_at',label:'开始时间',type:'datetime-local'},{name:'ends_at',label:'结束时间',type:'datetime-local'},{name:'window_start',label:'窗口开始',type:'datetime-local'},{name:'window_end',label:'窗口结束',type:'datetime-local'},{name:'venue_space_id',label:'场地空间',type:'select',options:resourceOptions('venue_spaces','暂不指定空间')},{name:'location_text',label:'场地/地点补充',full:true,placeholder:'原文可先保留，未知信息不要猜测'},{name:'notes',label:'备注',type:'textarea',full:true}];
    openModal({title:session?'编辑场次':'新增活动场次',subtitle:'一个项目可以有多个场次；纯物料项目可以没有场次。',fields,initial:session?{...session,starts_at:session.starts_at,ends_at:session.ends_at,window_start:session.window_start,window_end:session.window_end,venue_space_id:session.venue_space_id||''}:{title:p.name,date_mode:'undated',status:'待排期'},submitLabel:session?'保存场次':'建立场次',note:session?'开始/结束时间属于重要字段，修改会生成待确认变更。':'日期待定也可保存为草稿。',onSubmit:async values=>{
      if (values.date_mode==='fixed' && !values.starts_at) throw new Error('固定日期场次需要填写开始时间，或改为“日期待定”。');
      if (values.starts_at && values.ends_at && new Date(values.ends_at)<new Date(values.starts_at)) throw new Error('结束时间不能早于开始时间。');
      if (session) { const data=await api(`/api/sessions/${session.id}`,json('PATCH',{...values,_revision:session.revision,source_text:'场次编辑'})); if(data.proposed_changes?.length) toast('场次重要变更已提交待确认','warn'); else toast('场次已更新'); }
      else { await api(`/api/projects/${p.id}/sessions`,json('POST',values)); toast('场次已建立'); }
      await loadProject();
    }});
  }
  async function openNodeForm(node=null, sessionId='') {
    const p=state.project; if(!p)return;
    const sessions=[{value:'',label:'项目级节点'},...p.sessions.map(s=>({value:s.id,label:s.title}))];
    const packages=[{value:'',label:'不绑定工作包'},...p.work_packages.map(w=>({value:w.id,label:w.name}))];
    const fields=[{name:'node_type',label:'节点类型',type:'select',options:nodeTypes},{name:'label',label:'节点名称',required:true,full:true},{name:'session_id',label:'所属场次',type:'select',options:sessions},{name:'work_package_id',label:'所属工作包',type:'select',options:packages},{name:'planned_start',label:'计划开始',type:'datetime-local'},{name:'planned_end',label:'计划结束',type:'datetime-local'},{name:'date_status',label:'时间确定状态',type:'select',options:['待确认','暂定','已确认','实际','冲突']},{name:'move_rule',label:'场次改期规则',type:'select',options:[{value:'follow_session',label:'跟随场次移动'},{value:'fixed',label:'固定承诺，改期时复核'}]},{name:'responsible',label:'负责人/责任方'},{name:'status',label:'节点状态',type:'select',options:['待办','进行中','待确认','已完成','待复核','取消']},{name:'source_text',label:'来源原文/依据',type:'textarea',full:true},{name:'notes',label:'备注',type:'textarea',full:true}];
    openModal({title:node?'编辑时间节点':'新增时间节点',subtitle:'可存在多条布场、进场、彩排、撤场或交付记录。',fields,initial:node?node:{node_type:'布场',label:'布场进场',session_id:sessionId||'',date_status:'待确认',move_rule:'follow_session',status:'待办'},submitLabel:node?'保存节点':'建立节点',onSubmit:async values=>{
      if(node){const d=await api(`/api/time-nodes/${node.id}`,json('PATCH',{...values,_revision:node.revision,source_text:values.source_text}));if(d.proposed_changes?.length)toast('关键时间变更已提交待确认','warn');}
      else await api(`/api/projects/${p.id}/time-nodes`,json('POST',values));
      toast(node?'节点已更新':'节点已建立'); await loadProject();
    }});
  }
  async function openPackageForm(pkg=null) {
    const p=state.project;if(!p)return; await ensureResource('suppliers');
    const fields=[{name:'name',label:'工作包名称',required:true,full:true},{name:'supplier_id',label:'供应商公司',type:'select',options:resourceOptions('suppliers','暂未确定供应商')},{name:'contact_snapshot',label:'联系人/对接人',placeholder:'例如 罗总、波总、小胡；未确认所属公司可只记联系人'},{name:'status',label:'工作包状态',type:'select',options:packageStatus},{name:'responsibility',label:'责任范围',type:'textarea',full:true},{name:'description',label:'说明',type:'textarea',full:true},{name:'acceptance_criteria',label:'验收标准',type:'textarea',full:true},{name:'planned_entry_at',label:'计划进场',type:'datetime-local'},{name:'planned_strike_at',label:'计划撤场',type:'datetime-local'}];
    openModal({title:pkg?'编辑工作包':'新增执行工作包',subtitle:'供应商公司与联系人分开记录；供应商可以暂时留空。',fields,initial:pkg?pkg:{status:'待指派'},submitLabel:pkg?'保存工作包':'建立工作包',onSubmit:async values=>{
      if(pkg){const d=await api(`/api/work-packages/${pkg.id}`,json('PATCH',{...values,_revision:pkg.revision}));if(d.proposed_changes?.length)toast('供应商/验收等重要变更已提交待确认','warn');}
      else await api(`/api/projects/${p.id}/work-packages`,json('POST',values));
      toast(pkg?'工作包已更新':'工作包已建立'); await loadProject();
    }});
  }
  async function openRequirementForm(req=null) {
    const p=state.project;if(!p)return;
    const fields=[{name:'name',label:'需求项名称',required:true,full:true},{name:'work_package_id',label:'所属工作包',type:'select',options:[{value:'',label:'暂不分派'},...p.work_packages.map(w=>({value:w.id,label:w.name}))]},{name:'status',label:'需求状态',type:'select',options:requirementStatus},{name:'specification',label:'规格说明',type:'textarea',full:true,placeholder:'原文不明确的内容保留待核，不要自行解释'},{name:'dimensions',label:'尺寸',placeholder:'例如 6 × 3.5'},{name:'dimension_unit',label:'尺寸单位',placeholder:'m / cm / mm'},{name:'quantity_text',label:'数量',placeholder:'允许保留原始数量文本'},{name:'quantity_unit',label:'数量单位',placeholder:'块 / 套 / 支 / 张'},{name:'intended_use',label:'用途/现场注意事项',type:'textarea',full:true},{name:'location_text',label:'摆放位置',full:true},{name:'acceptance_criteria',label:'强制验收条件',type:'textarea',full:true},{name:'delivered_quantity_text',label:'实际交付数量'},{name:'owner',label:'负责人'},{name:'source_text',label:'来源原文',type:'textarea',full:true}];
    openModal({title:req?'编辑需求项':'新增需求项',subtitle:'需求清单记录物件/服务，执行动作请另外建任务。',fields,initial:req||{status:'待澄清'},submitLabel:req?'保存需求项':'建立需求项',note:req?'规格、数量和状态属于重要字段，变更将进入待确认流程。':'不确定尺寸、单位或数量时可保留待确认。',onSubmit:async values=>{
      if(req){const d=await api(`/api/requirements/${req.id}`,json('PATCH',{...values,_revision:req.revision,source_text:values.source_text}));if(d.proposed_changes?.length)toast('规格/数量等重要变更已提交待确认','warn');}
      else await api(`/api/projects/${p.id}/requirements`,json('POST',values));
      toast(req?'需求项已更新':'需求项已建立'); await loadProject();
    }});
  }
  async function openTaskForm(task=null) {
    const p=state.project;if(!p)return;
    const fields=[{name:'name',label:'任务名称',required:true,full:true},{name:'work_package_id',label:'所属工作包',type:'select',options:[{value:'',label:'不绑定工作包'},...p.work_packages.map(w=>({value:w.id,label:w.name}))]},{name:'status',label:'任务状态',type:'select',options:taskStatus},{name:'owner',label:'执行人',placeholder:'具体执行同事'},{name:'responsible_party',label:'责任方/供应商联系人',placeholder:'例如 小胡 / 供应商'},{name:'planned_start',label:'计划开始',type:'datetime-local'},{name:'due_at',label:'截止时间',type:'datetime-local'},{name:'duration_days',label:'预计工期（天）',type:'number',min:'0',hint:'只有工期可靠时才用于倒推建议期限。'},{name:'dependency_ids',label:'前置依赖任务',type:'select',multiple:true,options:p.tasks.filter(t=>!task||t.id!==task.id).map(t=>({value:t.id,label:t.name}))},{name:'requirement_ids',label:'关联需求项',type:'select',multiple:true,options:p.requirements.map(r=>({value:r.id,label:r.name}))},{name:'needs_review',label:'需要复核',type:'checkbox',checkboxLabel:'标记需要复核'},{name:'source_text',label:'来源原文',type:'textarea',full:true},{name:'notes',label:'备注/完成证据说明',type:'textarea',full:true}];
    const initial=task?{...task,dependency_ids:task.dependencies.map(d=>d.depends_on_task_id),requirement_ids:task.requirement_ids}:{status:'待办',needs_review:false};
    openModal({title:task?'编辑执行任务':'新增执行任务',subtitle:'任务与需求项分开；任务依赖不能形成循环。',fields,initial,submitLabel:task?'保存任务':'建立任务',note:task?'截止时间、负责人或状态属于重要字段，修改后需确认。':'若没有可靠工期，不要填造精确截止日期。',onSubmit:async values=>{
      if(values.duration_days==='')values.duration_days=null;
      if(task){const d=await api(`/api/tasks/${task.id}`,json('PATCH',{...values,_revision:task.revision}));if(d.proposed_changes?.length)toast('关键任务变更已提交待确认','warn');}
      else await api(`/api/projects/${p.id}/tasks`,json('POST',values));
      toast(task?'任务已更新':'任务已建立'); await loadProject();
    }});
  }
  async function cycleTask(id) {
    const t=state.project.tasks.find(x=>x.id===id);if(!t)return;
    const next=t.status==='已完成'?'待办':'已完成';
    try { const d=await api(`/api/tasks/${id}`,json('PATCH',{status:next,_revision:t.revision,confirm_critical:true,source_ref:'任务快捷状态操作'})); toast(`任务状态已更新：${next}`); await loadProject(); }
    catch(e){toast(e.message,'error');}
  }

  async function openResourceForm(kind=state.resourceKind, resource=null) {
    const specs={
      clients:[{name:'name',label:'客户名称',required:true},{name:'aliases',label:'别名/简称'},{name:'notes',label:'备注',type:'textarea',full:true}],
      suppliers:[{name:'name',label:'供应商公司/团队名称',required:true},{name:'service_category',label:'服务类型',placeholder:'舞台 / LED / 印刷 / 摄影'},{name:'notes',label:'备注',type:'textarea',full:true}],
      contacts:[{name:'name',label:'联系人姓名',required:true},{name:'role',label:'职务/角色'},{name:'supplier_id',label:'所属供应商',type:'select',options:resourceOptions('suppliers','未确认供应商')},{name:'client_id',label:'所属客户',type:'select',options:resourceOptions('clients','未确认客户')},{name:'phone',label:'电话'},{name:'email',label:'邮箱'},{name:'source_text',label:'来源原文',type:'textarea',full:true},{name:'notes',label:'备注',type:'textarea',full:true}],
      venues:[{name:'name',label:'场地名称',required:true},{name:'address',label:'地址',full:true},{name:'verified_status',label:'核实状态',type:'select',options:['待核实','已核实','需要更新']},{name:'verified_by',label:'核实人'},{name:'notes',label:'备注/装卸说明',type:'textarea',full:true}],
      venue_spaces:[{name:'venue_id',label:'所属场地',type:'select',required:true,options:resourceOptions('venues','请选择场地')},{name:'parent_space_id',label:'上级空间',type:'select',options:resourceOptions('venue_spaces','无上级空间')},{name:'name',label:'空间名称',required:true},{name:'space_type',label:'空间类型',type:'select',options:['楼栋','楼层','厅室','室外区域','装卸点','其他']},{name:'floor_label',label:'楼层标识'},{name:'verified_status',label:'核实状态',type:'select',options:['待核实','已核实','需要更新']},{name:'verified_by',label:'核实人'},{name:'details',label:'空间详情/动线/限制',type:'textarea',full:true}],
      equipment:[{name:'space_id',label:'所属空间',type:'select',options:resourceOptions('venue_spaces','暂未关联空间')},{name:'name',label:'设备名称',required:true},{name:'category',label:'设备类别',placeholder:'LED / 音响 / 灯光 / 货梯'},{name:'ownership',label:'所有权',type:'select',options:['场地固定','自有资产','租赁设备','其他']},{name:'physical_dimensions',label:'物理尺寸',placeholder:'区分物理尺寸与分辨率'},{name:'resolution',label:'分辨率'},{name:'pixel_pitch',label:'像素间距'},{name:'verified_status',label:'核实状态',type:'select',options:['待核实','已核实','需要更新']},{name:'verified_by',label:'核实人'},{name:'loading_notes',label:'装卸/运输注意事项',type:'textarea',full:true},{name:'power_audio_notes',label:'供电/音响灯光说明',type:'textarea',full:true},{name:'source_text',label:'来源原文',type:'textarea',full:true}],
    };
    if(['contacts','venue_spaces','equipment'].includes(kind)){await ensureResource('suppliers');await ensureResource('clients');await ensureResource('venues');await ensureResource('venue_spaces');}
    const labels={clients:'客户',suppliers:'供应商',contacts:'联系人',venues:'场地',venue_spaces:'场地空间',equipment:'固定设备'};
    const fields=(specs[kind]||[]).map(f=>({...f,full:f.full||f.type==='textarea'}));
    openModal({title:resource?`编辑${labels[kind]}`:`新建${labels[kind]}`,subtitle:'资源主档可以跨项目复用；项目历史快照不会被静默改写。',fields,initial:resource||{},submitLabel:resource?'保存修改':'新建资源',onSubmit:async values=>{
      const endpoint=`/api/resources/${kind}`;
      if(resource) await api(`${endpoint}/${resource.id}`,json('PATCH',{...values,_revision:resource.revision,source_text:values.source_text}));
      else await api(endpoint,json('POST',values));
      toast(resource?'资源已更新':'资源已创建'); delete state.resources[kind]; await loadResources();
    }});
  }

  async function uploadForm(entityType, entityId, label='项目资料') {
    openModal({title:`上传${label}`,subtitle:'支持混合上传图片/PDF；图片会自动纠正方向并压缩，重要 PDF 保留原件。',wide:true,fields:[
      {name:'files',label:'选择文件（可多选）',type:'text',placeholder:'点击下方按钮选择图片或 PDF',full:true},
      {name:'category',label:'资料分类',type:'select',options:['主 KV / 主画面','设计稿','正式 PDF','现场照片','场地指引','设备资料','交付凭证','其他']},
      {name:'is_official',label:'正式文件',type:'checkbox',checkboxLabel:'标记为正式/已确认文件'},
      {name:'notes',label:'说明',type:'textarea',full:true},
    ],submitLabel:'开始上传',note:'普通照片处理成功后只保留压缩版和缩略图；透明 PNG 会保留透明通道。处理失败不会先删除唯一有效副本。',onSubmit:async values=>{
      const input=$('#upload-real-files');
      if(!input?.files?.length)throw new Error('请选择至少一个文件');
      const form=new FormData();[...input.files].forEach(f=>form.append('files',f));
      form.append('entity_type',entityType||'');form.append('entity_id',entityId||'');form.append('category',values.category||'其他');form.append('is_official',values.is_official?'1':'0');form.append('notes',values.notes||'');
      const res=await api('/api/documents',{method:'POST',body:form});
      if(res.failures?.length)toast(`上传成功 ${res.documents.length} 个，失败 ${res.failures.length} 个：${res.failures.map(f=>f.filename).join('、')}`,'warn');
      else toast(`已上传 ${res.documents.length} 个文件`);
      if(state.page==='project-detail')await loadProject();else if(state.page==='resources')await loadResources();
    }});
    const modal=$('.modal',modalRoot); const holder=$('.modal-body',modal);
    const field=$('[name="files"]',modal);
    field.outerHTML=`<div class="file-pick-area"><input id="upload-real-files" type="file" accept=".jpg,.jpeg,.png,.webp,.heic,.heif,.pdf" multiple><span class="hint">支持 JPG / PNG / WebP / HEIC / HEIF / PDF，单文件最大 100MB，批量总量最大 250MB。</span></div>`;
  }

  async function setCover(docId, sessionId='') {
    const p=state.project;if(!p)return;
    const entity = sessionId ? p.sessions.find(s=>s.id===sessionId) : p;
    if(!entity)return;
    confirmModal(sessionId?'设置场次主图':'设置项目主图','将此文件设为当前封面引用。不会删除旧附件或历史版本。',async()=>{
      if(!getOperator(true))throw new Error('已取消操作');
      const path=sessionId?`/api/sessions/${sessionId}`:`/api/projects/${p.id}`;
      const d=await api(path,json('PATCH',{cover_document_id:docId,_revision:entity.revision}));
      if(d.proposed_changes?.length)toast('封面变更已提交待确认','warn');else toast('主图已更新');
      await loadProject();
    },{requireOperator:false,submitLabel:'设置主图',noteType:''});
  }
  async function shareFile(id) {
    confirmModal('创建受控分享链接','将创建一个有有效期、可撤销的文件分享链接。分享文件的接收方下载后的副本无法远程收回。',async values=>{
      const d=await api(`/api/documents/${id}/shares`,json('POST',{days:Number(values.days||7),allow_download:values.allow_download!==false}));
      const url=new URL(d.share.url,location.origin).href;
      try{await navigator.clipboard.writeText(url);toast('分享链接已复制到剪贴板');}catch(_){window.prompt('复制以下分享链接',url);}
    },{fields:[{name:'days',label:'有效期（天）',type:'number',min:'1',value:7,required:true},{name:'allow_download',label:'允许下载',type:'checkbox',checkboxLabel:'允许下载文件'}],initial:{days:7,allow_download:true},requireOperator:true,submitLabel:'创建并复制链接'});
  }

  async function handleClick(e) {
    const b=e.target.closest('[data-action]'); if(!b)return;
    const action=b.dataset.action;
    try {
      if(action==='close-modal'){requestCloseModal();return;}
      if(action==='go-projects')return navigate('projects');
      if(action==='go-changes')return navigate('changes');
      if(action==='new-project')return openProjectForm();
      if(action==='open-project') { state.projectId=b.dataset.id;state.page='project-detail';state.projectTab='overview';location.hash=`#/projects/${state.projectId}`;updateNav();return loadProject(); }
      if(action==='project-tab'){state.projectTab=b.dataset.tab;location.hash=`#/projects/${state.projectId}?tab=${state.projectTab}`;return renderProjectDetail();}
      if(action==='edit-project')return openProjectForm(state.project);
      if(action==='new-session')return openSessionForm();
      if(action==='edit-session')return openSessionForm(state.project.sessions.find(x=>x.id===b.dataset.id));
      if(action==='new-node')return openNodeForm(null,b.dataset.sessionId||'');
      if(action==='edit-node')return openNodeForm(state.project.time_nodes.find(x=>x.id===b.dataset.id));
      if(action==='new-package')return openPackageForm();
      if(action==='edit-package')return openPackageForm(state.project.work_packages.find(x=>x.id===b.dataset.id));
      if(action==='new-requirement')return openRequirementForm();
      if(action==='edit-requirement')return openRequirementForm(state.project.requirements.find(x=>x.id===b.dataset.id));
      if(action==='new-task')return openTaskForm();
      if(action==='edit-task')return openTaskForm(state.project.tasks.find(x=>x.id===b.dataset.id));
      if(action==='cycle-task')return cycleTask(b.dataset.id);
      if(action==='upload-project-file')return uploadForm('projects',state.project.id,'项目资料');
      if(action==='upload-resource-file')return uploadForm(state.resourceKind,b.dataset.id,'资源附件');
      if(action==='set-project-cover')return setCover(b.dataset.id);
      if(action==='preview-file'){window.open(`/api/documents/${b.dataset.id}/content?variant=preview`,'_blank','noopener');return;}
      if(action==='download-file'){window.open(`/api/documents/${b.dataset.id}/content?variant=download`,'_blank','noopener');return;}
      if(action==='share-file')return shareFile(b.dataset.id);
      if(action==='confirm-change')return confirmChange(b.dataset.id);
      if(action==='reject-change')return rejectChange(b.dataset.id);
      if(action==='archive-project')return archiveProject();
      if(action==='restore-audit')return restoreAudit(Number(b.dataset.id));
      if(action==='calendar-prev'){state.calendarDate.setMonth(state.calendarDate.getMonth()-1);return renderCalendar(state.dashboard);}
      if(action==='calendar-next'){state.calendarDate.setMonth(state.calendarDate.getMonth()+1);return renderCalendar(state.dashboard);}
      if(action==='calendar-today'){state.calendarDate=new Date();return renderCalendar(state.dashboard);}
      if(action==='open-day'){openDayModal(b.dataset.date);return;}
      if(action==='open-session'){closeModal();const id=b.dataset.projectId;const sessionId=b.dataset.sessionId;state.projectId=id;state.page='project-detail';state.projectTab='schedule';location.hash=`#/projects/${id}?tab=schedule`;await loadProject();return;}
      if(action==='reschedule-session')return rescheduleSession(b.dataset.id);
      if(action==='resource-tab'){state.resourceKind=b.dataset.kind;return loadResources();}
      if(action==='new-resource')return openResourceForm();
      if(action==='edit-resource'){const kind=state.resourceKind;const item=(state.resources[kind]||[]).find(x=>x.id===b.dataset.id);return openResourceForm(kind,item);}
      if(action==='refresh-changes')return loadChanges();
      if(action==='show-archived')return fetchProjectRows(true);
      if(action==='retry')return refreshPage();
    } catch(err) { toast(err.message || '操作失败', 'error'); }
  }
  root.addEventListener('click',handleClick);
  root.addEventListener('click', e=>{
    const day=e.target.closest('.calendar-day');
    if(day&&!e.target.closest('[data-action]'))openDayModal(day.dataset.date);
  });
  modalRoot.addEventListener('click',handleClick);
  modalRoot.addEventListener('click',e=>{
    if(e.target.classList.contains('day-detail-backdrop'))closeModal();
  });
  $('#search-results').addEventListener('click',e=>{const b=e.target.closest('[data-search-url]');if(!b)return;$('#search-results').classList.add('hidden');state.searchOpen=false;location.hash=b.dataset.searchUrl;});

  async function confirmChange(id) {
    confirmModal('确认重要变更','确认后将把拟变更值写入正式数据，并记录确认人、确认时间和审计。若该字段在提案后被其他设备修改，系统会保留冲突，不覆盖现值。',async()=>{
      const result=await api(`/api/change-requests/${id}/confirm`,json('POST',{confirm:true}));toast('变更已确认');if(state.page==='project-detail')await loadProject();else await loadChanges();
    },{requireOperator:true,submitLabel:'确认并生效',noteType:'warning'});
  }
  async function rejectChange(id) {
    confirmModal('驳回这项变更？','驳回后正式值保持不变，驳回原因会留在审计记录中。',async values=>{
      await api(`/api/change-requests/${id}/reject`,json('POST',{confirm:true,note:values.note||''}));toast('变更已驳回');if(state.page==='project-detail')await loadProject();else await loadChanges();
    },{requireOperator:true,submitLabel:'确认驳回',fields:[{name:'note',label:'驳回原因（可选）',type:'textarea',full:true}],noteType:'warning'});
  }
  async function archiveProject() {
    const p=state.project;if(!p)return;
    confirmModal('归档项目','归档不会删除项目、历史文件或审计记录。请先核对交付文件、现场照片、未完成任务与供应商履约；资料未齐时可先将项目阶段改为“收尾”。',async()=>{
      await api(`/api/projects/${p.id}/archive`,json('POST',{confirm:true}));toast('项目已归档');state.page='projects';state.projectId='';location.hash='#/projects';await loadProjects();
    },{requireOperator:true,submitLabel:'确认归档',noteType:'warning'});
  }
  async function restoreAudit(id) {
    confirmModal('按历史记录恢复字段','系统会尝试将该次修改前的字段值恢复。如果是重要字段，会生成新的变更提案；不会删除当前审计记录。',async()=>{
      const result=await api(`/api/audit/${id}/restore`,json('POST',{confirm:true}));toast(result.proposed_changes?.length?'已生成恢复提案，请再次确认':'历史字段已恢复');await loadProject();
    },{requireOperator:true,submitLabel:'确认恢复'});
  }
  async function rescheduleSession(id) {
    const s=state.project.sessions.find(x=>x.id===id);if(!s)return;
    openModal({title:'预览场次改期',subtitle:'先预览受影响的相对节点和任务，再决定是否保存。',fields:[{name:'starts_at',label:'新开始时间',type:'datetime-local',required:true},{name:'ends_at',label:'新结束时间',type:'datetime-local'}],initial:{starts_at:s.starts_at,ends_at:s.ends_at},submitLabel:'计算影响范围',onSubmit:async values=>{
      const data=await api(`/api/sessions/${id}/reschedule-preview`,json('POST',values));
      closeModal();const x=data.preview;
      const lines=[`项目：${x.project_name}`,`原时间：${fmtDateTime(x.old.starts_at)} — ${fmtDateTime(x.old.ends_at)}`,`新时间：${fmtDateTime(x.new.starts_at)} — ${fmtDateTime(x.new.ends_at)}`,`将跟随移动的节点：${x.following_nodes.length}`,`固定承诺需复核：${x.fixed_nodes_to_review.length}`,`可能需要复核的任务：${x.tasks_to_review.length}`,`供应商承诺：${x.supplier_commitments.length} 项`].join('\n');
      confirmModal('确认改期？',lines,async()=>{
        await api(`/api/sessions/${id}/reschedule`,json('POST',{...values,confirm:true,_revision:s.revision,source_ref:'calendar-reschedule-preview'}));toast('改期已保存；关联任务已标记复核');await loadProject();
      },{requireOperator:true,submitLabel:'确认改期',noteType:'warning'});
    }});
  }

  // Calendar drag: preview first; only a second explicit confirmation writes the date.
  let draggedSession = null;
  root.addEventListener('dragstart',e=>{
    const pill=e.target.closest('.event-pill[draggable="true"]');if(!pill)return;
    draggedSession={id:pill.dataset.sessionId,projectId:pill.dataset.projectId,start:pill.dataset.start,end:pill.dataset.end,revision:Number(pill.dataset.revision)};
    e.dataTransfer.setData('text/plain',pill.dataset.sessionId);e.dataTransfer.effectAllowed='move';
  });
  root.addEventListener('dragover',e=>{const day=e.target.closest('.calendar-day');if(!day)return;e.preventDefault();day.classList.add('drop-target');});
  root.addEventListener('dragleave',e=>{const day=e.target.closest('.calendar-day');if(day&&!day.contains(e.relatedTarget))day.classList.remove('drop-target');});
  root.addEventListener('drop',async e=>{
    const day=e.target.closest('.calendar-day');if(!day||!draggedSession)return;e.preventDefault();$$('.calendar-day.drop-target').forEach(x=>x.classList.remove('drop-target'));
    const d=day.dataset.date;const s=draggedSession;draggedSession=null;
    if(!s.start){toast('该场次没有固定开始时间，不能拖动改期。','warn');return;}
    const oldStart=new Date(s.start),oldEnd=s.end?new Date(s.end):null;
    const dur=oldEnd?oldEnd-oldStart:0;const timePart=fmtDateTimeInput(s.start).slice(11,16)||'09:00';
    const newStart=`${d}T${timePart}+08:00`;
    let newEnd='';
    if(oldEnd){ newEnd=new Date(new Date(newStart).getTime()+dur).toISOString(); }
    try {
      const data=await api(`/api/sessions/${s.id}/reschedule-preview`,json('POST',{starts_at:newStart,ends_at:newEnd}));const x=data.preview;
      const message=[`场次：${x.session_title||x.project_name}`,`原时间：${fmtDateTime(x.old.starts_at)} — ${fmtDateTime(x.old.ends_at)}`,`拟改为：${fmtDateTime(x.new.starts_at)} — ${fmtDateTime(x.new.ends_at)}`,`跟随场次移动的节点：${x.following_nodes.length}`,`固定节点待复核：${x.fixed_nodes_to_review.length}`,`关联任务需复核：${x.tasks_to_review.length}`,`供应商承诺不自动覆盖。`].join('\n');
      confirmModal('日历改期预览',message,async()=>{
        state.projectId=s.projectId;state.page='project-detail';state.projectTab='schedule';
        await api(`/api/sessions/${s.id}/reschedule`,json('POST',{starts_at:newStart,ends_at:newEnd,confirm:true,_revision:s.revision,source_ref:'calendar-drag'}));toast('改期已确认并保存');await navigate('home');
      },{requireOperator:true,submitLabel:'确认并保存改期',noteType:'warning'});
    } catch(err){toast(err.message,'error');}
  });

  // Global search
  const searchInput=$('#global-search');
  searchInput.addEventListener('focus',()=>{if(searchInput.value.trim())runGlobalSearch(searchInput.value.trim());});
  searchInput.addEventListener('input',()=>{clearTimeout(state.searchTimer);const q=searchInput.value.trim();if(q.length<2){$('#search-results').classList.add('hidden');state.searchOpen=false;return;}state.searchTimer=setTimeout(()=>runGlobalSearch(q),240);});
  document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();searchInput.focus();}if(e.key==='Escape'){requestCloseModal();$('#search-results').classList.add('hidden');state.searchOpen=false;}});
  async function runGlobalSearch(q) {
    try {const d=await api(`/api/search?q=${encodeURIComponent(q)}`);const host=$('#search-results');state.searchOpen=true;host.classList.remove('hidden');host.innerHTML=d.results.length?d.results.map(r=>`<button class="search-result" data-search-url="${esc(r.url)}"><strong>${esc(r.title)}</strong><small>${esc(r.type)} · ${esc(r.subtitle||'')}</small></button>`).join(''):`<div class="search-result"><strong>没有匹配结果</strong><small>试试项目名称、联系人、任务或物料名称。</small></div>`;}catch(e){toast(e.message,'error');}
  }

  // Add a real file picker to upload modals after form rendering.
  const modalObserver = new MutationObserver(() => {
    const modal=$('.modal',modalRoot);if(!modal)return;
    const field=$('[name="files"]',modal);
    if(field && !$('#upload-real-files',modal)) {
      field.outerHTML=`<div class="file-pick-area"><input id="upload-real-files" type="file" accept=".jpg,.jpeg,.png,.webp,.heic,.heif,.pdf" multiple><span class="hint">支持 JPG / PNG / WebP / HEIC / HEIF / PDF，单文件最大 100MB，批量总量最大 250MB。</span></div>`;
    }
  });
  modalObserver.observe(modalRoot,{childList:true,subtree:true});

  boot();
})();
