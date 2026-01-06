/* Gymiboost Course Tools Renderer
   Scans a module card for data-tool blocks and wires them to backend APIs.

   Exposes:
   - window.initCourseTools(cardEl, courseId)
*/

(function(){
  function $(sel, root){ return (root||document).querySelector(sel); }
  function $all(sel, root){ return Array.from((root||document).querySelectorAll(sel)); }

  async function fetchJSON(url, opts) {
    const res = await fetch(url, opts || {});
    const ct = res.headers.get('content-type') || '';
    if (!res.ok) {
      if (ct.includes('text/html')) {
        // likely auth redirect
        window.location.href = res.url || '/login';
        throw new Error('Redirected');
      }
      const txt = await res.text().catch(()=> '');
      throw new Error(txt || ('HTTP ' + res.status));
    }
    if (ct.includes('application/json')) return res.json();
    return res.text();
  }

  function el(tag, attrs, ...children){
    const e = document.createElement(tag);
    if (attrs && typeof attrs === 'object') {
      Object.entries(attrs).forEach(([k,v])=>{
        if (k === 'class') e.className = v || '';
        else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
        else if (v !== undefined && v !== null) e.setAttribute(k, String(v));
      });
    }
    children.flat().forEach(c=>{
      if (c === null || c === undefined) return;
      if (c instanceof Node) e.appendChild(c);
      else e.appendChild(document.createTextNode(String(c)));
    });
    return e;
  }

  function bar(percent, label){
    const wrap = el('div', { class: 'poll-bar', style: { background: 'rgba(255,255,255,0.06)', borderRadius: '8px', overflow: 'hidden', position:'relative', margin:'4px 0' } },
      el('div', { class: 'poll-bar__fill', style: { width: percent+'%', background: 'linear-gradient(90deg,#60a5fa,#a78bfa)', height:'10px' } }),
      el('div', { class: 'poll-bar__label', style: { position:'absolute', left:'8px', top:'-2px', fontSize: '0.8rem', color:'#d1d5db' } }, label)
    );
    return wrap;
  }

  // ========== QUIZ ==========
  async function initQuiz(block, courseId, moduleId){
    const slug = block.getAttribute('data-slug');
    if (!slug) { block.textContent = 'Quiz: data-slug fehlt.'; return; }
    block.innerHTML = '<div class="muted">Lade Quiz…</div>';
    let quiz;
    try {
      quiz = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/quiz/${encodeURIComponent(slug)}`);
    } catch (e) {
      block.innerHTML = '<div class="muted">Quiz nicht gefunden.</div>';
      return;
    }
    const data = quiz.data || {};
    const qs = Array.isArray(data.questions) ? data.questions : [];
    const wrap = el('div', { class: 'tool tool-quiz' });
    if (quiz.title) wrap.appendChild(el('h5', {}, quiz.title));

    const form = el('form', { class: 'quiz-form' });
    qs.forEach((q, idx)=>{
      const qWrap = el('div', { class: 'quiz-q', style: { margin: '10px 0', padding:'8px', border:'1px solid rgba(255,255,255,0.1)', borderRadius:'8px' } });
      const label = (q.type || 'mc') === 'mc' ? (q.question || '') : (q.prompt || q.question || '');
      qWrap.appendChild(el('div', { class: 'quiz-q__label' }, `Frage ${idx+1}: `, label));
      if ((q.type || 'mc') === 'mc') {
        const choices = Array.isArray(q.choices) ? q.choices : [];
        choices.forEach((c, ci)=>{
          const id = `q${idx}_c${ci}_${moduleId}_${slug}`;
          const row = el('label', { for: id, style: { display:'flex', gap:'8px', alignItems:'center', marginTop:'4px', cursor:'pointer' } },
            el('input', { type:'radio', name:`q_${idx}`, id, value:String(ci) }),
            el('span', {}, c)
          );
          qWrap.appendChild(row);
        });
      } else {
        qWrap.appendChild(el('textarea', { name:`q_${idx}`, rows:'3', style: { width:'100%', background:'rgba(15,23,42,0.6)', color:'#e5e7eb', border:'1px solid rgba(255,255,255,0.1)', borderRadius:'8px', padding:'6px' } }));
      }
      qWrap.appendChild(el('div', { class:'quiz-q__feedback', style:{ marginTop:'6px', fontSize:'0.9rem' } }));
      form.appendChild(qWrap);
    });
    const actions = el('div', { class:'quiz-actions', style:{ display:'flex', gap:'8px', marginTop:'8px' } },
      el('button', { type:'submit', class:'btn btn-primary' }, 'Abgeben')
    );
    form.appendChild(actions);
    wrap.appendChild(form);
    block.innerHTML = '';
    block.appendChild(wrap);

    form.addEventListener('submit', async (e)=>{
      e.preventDefault();
      const btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = true; btn.textContent = 'Werte aus…'; }
      try {
        const answers = qs.map((q, idx)=>{
          if ((q.type || 'mc') === 'mc') {
            const sel = form.querySelector(`input[name="q_${idx}"]:checked`);
            return sel ? Number(sel.value) : null;
          } else {
            const ta = form.querySelector(`textarea[name="q_${idx}"]`);
            return ta ? ta.value : '';
          }
        });
        const res = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/quiz/${encodeURIComponent(slug)}/attempt`, {
          method: 'POST', headers: { 'Content-Type':'application/json' },
          body: JSON.stringify({ answers })
        });
        // paint feedback
        const feedbackEls = $all('.quiz-q__feedback', form);
        const qBlocks = $all('.quiz-q', form);
        (res.results || []).forEach((r, i)=>{
          const f = feedbackEls[i];
          if (!f) return;
          f.innerHTML = '';
          const ok = !!r.correct;
          f.appendChild(el('div', { style:{ color: ok ? '#10b981' : '#ef4444' } }, ok ? 'Richtig!' : 'Falsch'));
          if (r.explanation) {
            f.appendChild(el('div', { class:'muted', style:{ marginTop:'4px' } }, r.explanation));
          }
          // subtle flash animation on the question block
          const qb = qBlocks[i];
          if (qb) {
            const old = qb.style.backgroundColor;
            qb.style.transition = 'background-color 0.3s ease';
            qb.style.backgroundColor = ok ? 'rgba(16,185,129,0.18)' : 'rgba(239,68,68,0.18)';
            setTimeout(()=>{ qb.style.backgroundColor = old || 'transparent'; }, 350);
          }
        });
        // summary
        wrap.appendChild(el('div', { style:{ marginTop:'8px' } }, `Punkte: ${res.correct}/${res.total} (${Math.round((res.score||0)*100)}%)`));
        // Try to refresh course progress UI after server-side bump
        try {
          const me = await fetchJSON('/api/courses/me');
          const mine = (me && Array.isArray(me.enrolled)) ? me.enrolled.find(c => c && c.id === courseId) : null;
          if (mine && typeof mine.progress === 'number') {
            const p = Math.max(0, Math.min(100, mine.progress|0));
            const bar = document.querySelector('#cd-progress');
            const label = document.querySelector('#cd-progress-label');
            if (bar) bar.style.width = p + '%';
            if (label) label.textContent = p + '%';
          }
        } catch (e) {
          // ignore UI refresh failures
        }
      } catch (err) {
        alert('Quiz-Abgabe fehlgeschlagen.');
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Abgeben'; }
      }
    });
  }

  // ========== POLL ==========
  async function initPoll(block, courseId, moduleId){
    const slug = block.getAttribute('data-slug');
    if (!slug) { block.textContent = 'Umfrage: data-slug fehlt.'; return; }
    block.innerHTML = '<div class="muted">Lade Umfrage…</div>';
    let state;
    try {
      state = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/poll/${encodeURIComponent(slug)}`);
    } catch (e) {
      block.innerHTML = '<div class="muted">Umfrage nicht gefunden.</div>';
      return;
    }
    const { question, options, multiple, tally, myVote } = state;
    const voted = Array.isArray(myVote) && myVote.length > 0;
    const wrap = el('div', { class: 'tool tool-poll' });
    wrap.appendChild(el('div', { style:{ fontWeight:'600', marginBottom:'6px' } }, question));

    const optWrap = el('div', {});
    if (voted) {
      const totalVotes = (tally || []).reduce((a,b)=> a+b, 0) || 1;
      options.forEach((opt, i)=>{
        const pct = Math.round(((tally[i] || 0) / totalVotes) * 100);
        const label = `${opt} — ${tally[i]||0} (${pct}%)`;
        optWrap.appendChild(bar(pct, label));
      });
      wrap.appendChild(optWrap);
      wrap.appendChild(el('div', { class:'muted', style:{ marginTop:'6px' } }, 'Danke fürs Abstimmen.'));
    } else {
      const inputType = multiple ? 'checkbox' : 'radio';
      options.forEach((opt, i)=>{
        const id = `poll_${moduleId}_${slug}_${i}`;
        const row = el('label', { for:id, style:{ display:'flex', gap:'8px', alignItems:'center', margin:'6px 0', cursor:'pointer' } },
          el('input', { type: inputType, name:'poll', id, value: String(i) }),
          el('span', {}, opt)
        );
        optWrap.appendChild(row);
      });
      wrap.appendChild(optWrap);
      const voteBtn = el('button', { class:'btn btn-primary', style:{ marginTop:'8px' } }, 'Abstimmen');
      wrap.appendChild(voteBtn);
      voteBtn.addEventListener('click', async ()=>{
        try {
          const selected = $all('input[name="poll"]:checked', wrap).map(x => Number(x.value));
          if (!selected.length) { alert('Bitte eine Option wählen.'); return; }
          const res = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/poll/${encodeURIComponent(slug)}/vote`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ options: selected })
          });
          // re-render results
          initPoll(block, courseId, moduleId);
        } catch (e) {
          alert('Abstimmung fehlgeschlagen.');
        }
      });
    }
    block.innerHTML = '';
    block.appendChild(wrap);
  }

  // ========== FLASHCARDS ==========
  function renderFlashUI(container, card, deck, stats){
    container.innerHTML = '';
    container.appendChild(el('div', { class:'muted', style:{ marginBottom:'4px' } }, deck && deck.title ? deck.title : 'Karteikarten'));
    const cardEl = el('div', { class:'flashcard', style:{ padding:'10px', border:'1px solid rgba(255,255,255,0.15)', borderRadius:'10px', background:'rgba(15,23,42,0.6)' } },
      el('div', { class:'flash-front', style:{ fontWeight:'600' } }, card.front),
      el('div', { class:'flash-back', style:{ display:'none', marginTop:'8px' } }, card.back)
    );
    container.appendChild(cardEl);
    const actions = el('div', { style:{ display:'flex', gap:'8px', marginTop:'8px', flexWrap:'wrap' } });
    const showBtn = el('button', { class:'btn btn-secondary' }, 'Antwort zeigen');
    actions.appendChild(showBtn);
    const grades = [
      {v:1, text:'Sehr schwer'},
      {v:2, text:'Schwer'},
      {v:3, text:'Gut'},
      {v:4, text:'Einfach'},
      {v:5, text:'Sehr einfach'},
    ];
    grades.forEach(g=>{
      const b = el('button', { class:'btn', 'data-ease': String(g.v), style:{ display:'none' } }, g.text);
      actions.appendChild(b);
    });
    container.appendChild(actions);
    const stat = el('div', { class:'muted', style:{ marginTop:'6px', fontSize:'0.9rem' } }, `Gelernt: ${stats.studied}/${stats.total}, Fällig: ${stats.due}`);
    container.appendChild(stat);

    showBtn.addEventListener('click', ()=>{
      const back = $('.flash-back', cardEl);
      if (back) back.style.display = '';
      showBtn.style.display = 'none';
      $all('button[data-ease]', actions).forEach(b => b.style.display = '');
    });
    return { cardEl };
  }

  async function initFlashcards(block, courseId, moduleId){
    const slug = block.getAttribute('data-slug');
    if (!slug) { block.textContent = 'Karteikarten: data-slug fehlt.'; return; }
    const container = el('div', { class:'tool tool-flashcards' }, el('div', { class:'muted' }, 'Lade Karteikarten…'));
    block.innerHTML = '';
    block.appendChild(container);

    const titleAttr = (block.getAttribute('data-title') || '').trim();
    const cardsAttr = (block.getAttribute('data-cards') || '').trim();
    let triedUpsert = false;

    async function ensureDeckFromAttr(){
      if (!cardsAttr || triedUpsert) return false;
      triedUpsert = true;
      let cards = [];
      try {
        cards = JSON.parse(cardsAttr);
      } catch {
        cards = [];
      }
      if (!Array.isArray(cards) || cards.length === 0) return false;
      try {
        await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/flashcards/upsert`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            slug,
            title: titleAttr || null,
            config: {},
            cards
          })
        });
        return true;
      } catch {
        return false;
      }
    }

    async function loadNext(){
      try {
        const state = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/flashcards/${encodeURIComponent(slug)}/next`);
        const { deck, card, stats } = state;
        const ui = renderFlashUI(container, card, deck, stats);
        $all('button[data-ease]', container).forEach(btn=>{
          btn.addEventListener('click', async ()=>{
            const ease = Number(btn.getAttribute('data-ease'));
            try {
              await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/flashcards/${encodeURIComponent(slug)}/review`, {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({ card_id: card.id, ease })
              });
              await loadNext();
            } catch (e) {
              alert('Bewertung fehlgeschlagen.');
            }
          });
        });
      } catch (e) {
        // If deck not found yet, try to upsert from data-cards
        const msg = (e && e.message) ? String(e.message) : '';
        if (/404/.test(msg) || /No cards/i.test(msg)) {
          const created = await ensureDeckFromAttr();
          if (created) {
            // try again after creating
            return loadNext();
          }
        }
        container.innerHTML = '<div class="muted">Keine Karten verfügbar.</div>';
      }
    }
    loadNext();
  }

  // ========== NOTES ==========
  async function initNotes(block, courseId, moduleId){
    block.innerHTML = '';
    const wrap = el('div', { class:'tool tool-notes' });
    wrap.appendChild(el('div', { class:'muted', style:{ marginBottom:'6px' } }, 'Meine Notizen'));
    const ta = el('textarea', { rows:'5', style:{ width:'100%', background:'rgba(15,23,42,0.6)', color:'#e5e7eb', border:'1px solid rgba(255,255,255,0.15)', borderRadius:'8px', padding:'8px' } });
    wrap.appendChild(ta);
    const row = el('div', { style:{ display:'flex', gap:'8px', alignItems:'center', marginTop:'6px' } },
      el('button', { class:'btn btn-secondary', type:'button' }, 'Speichern'),
      el('span', { class:'muted', style:{ fontSize:'0.85rem' } }, '')
    );
    wrap.appendChild(row);
    const saveBtn = $('button', row);
    const status = $('span', row);
    block.appendChild(wrap);

    // load
    try {
      const res = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/notes`);
      ta.value = res.content || '';
    } catch {}

    async function save(){
      try {
        status.textContent = 'Speichere…';
        await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/notes`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ content: ta.value })
        });
        status.textContent = 'Gespeichert';
        setTimeout(()=>{ status.textContent = ''; }, 1200);
      } catch {
        status.textContent = 'Fehler beim Speichern';
      }
    }
    let t;
    ta.addEventListener('input', ()=>{
      status.textContent = 'Änderungen…';
      clearTimeout(t);
      t = setTimeout(save, 800);
    });
    saveBtn.addEventListener('click', save);
  }

  // ========== CHECKLIST ==========
  async function initChecklist(block, courseId, moduleId){
    const seedAttr = block.getAttribute('data-items');
    block.innerHTML = '<div class="muted">Lade Checkliste…</div>';
    let state;
    try {
      state = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/checklist`);
    } catch (e) {
      block.innerHTML = '<div class="muted">Fehler beim Laden.</div>';
      return;
    }
    let items = Array.isArray(state.items) ? state.items : [];
    if ((!items || items.length === 0) && seedAttr) {
      try {
        // parse JSON or semicolon/comma string
        let arr;
        try { arr = JSON.parse(seedAttr); }
        catch { arr = String(seedAttr).split(/[,;]\s*/).filter(Boolean); }
        items = arr.map(label => ({ label: String(label), done: false }));
        await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/checklist`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ items })
        });
      } catch {}
    }
    const wrap = el('div', { class:'tool tool-checklist' });
    wrap.appendChild(el('div', { class:'muted', style:{ marginBottom:'4px' } }, 'Checkliste'));
    const list = el('ul', { style:{ listStyle:'none', padding:'0', margin:'0' } });
    function paint(){
      list.innerHTML = '';
      items.forEach((it, idx)=>{
        const id = `ck_${moduleId}_${idx}`;
        const li = el('li', { style:{ display:'flex', alignItems:'center', gap:'8px', padding:'4px 0' } },
          el('input', { type:'checkbox', id, checked: it.done ? 'checked' : null }),
          el('label', { for:id }, it.label || '')
        );
        const cb = $('input', li);
        cb.addEventListener('change', async ()=>{
          items[idx].done = !!cb.checked;
          try {
            await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/checklist`, {
              method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify({ items })
            });
          } catch {}
        });
        list.appendChild(li);
      });
    }
    paint();
    wrap.appendChild(list);
    block.innerHTML = '';
    block.appendChild(wrap);
  }

  // ========== CHECKPOINT ==========
  async function initCheckpoint(block, courseId, moduleId){
    const slug = (block.getAttribute('data-slug') || '').trim();
    const labelAttr = (block.getAttribute('data-label') || '').trim();
    if (!slug) { block.textContent = 'Checkpoint: data-slug fehlt.'; return; }
    block.innerHTML = '<div class="muted">Lade Checkpoint…</div>';

    // Load list of checkpoints and completion status
    let listState = { items: [], completedSlugs: [] };
    try {
      listState = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/checkpoints`);
    } catch (e) {
      block.innerHTML = '<div class="muted">Fehler beim Laden.</div>';
      return;
    }
    let items = Array.isArray(listState.items) ? listState.items : [];
    let completedSet = new Set(Array.isArray(listState.completedSlugs) ? listState.completedSlugs : []);

    // Find or create item locally
    let item = items.find(x => (x && (x.slug || x) === slug));
    if (!item) {
      // Attempt to upsert this checkpoint to the backend so it is tracked
      try {
        await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/checkpoints/upsert`, {
          method: 'POST', headers: { 'Content-Type':'application/json' },
          body: JSON.stringify({ items: [{ slug, label: labelAttr || slug, description: '', weight: 1 }] })
        });
        // Reload list
        listState = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/checkpoints`);
        items = Array.isArray(listState.items) ? listState.items : [];
        completedSet = new Set(Array.isArray(listState.completedSlugs) ? listState.completedSlugs : []);
        item = items.find(x => (x && (x.slug || x) === slug));
      } catch (e) {
        // continue with a local fallback item
        item = { slug, label: labelAttr || slug, description: '' };
      }
    }

    const done = completedSet.has(slug);
    const wrap = el('div', { class:'tool tool-checkpoint', style:{ display:'flex', alignItems:'center', gap:'8px' } });
    const btn = el('button', { class: done ? 'btn btn-success' : 'btn btn-secondary', type:'button' }, done ? 'Abgehakt' : (item?.label || labelAttr || 'Checkpoint'));
    const hint = el('span', { class:'muted', style:{ fontSize:'0.85rem' } }, item?.description || '');
    wrap.appendChild(btn);
    if ((item?.description || '').trim()) wrap.appendChild(hint);

    function flash(color){
      const old = wrap.style.backgroundColor;
      wrap.style.transition = 'background-color 0.3s ease';
      wrap.style.backgroundColor = color;
      setTimeout(()=>{ wrap.style.backgroundColor = old || 'transparent'; }, 350);
    }

    btn.addEventListener('click', async ()=>{
      btn.disabled = true;
      const wantDone = btn.textContent !== 'Abgehakt';
      try {
        const res = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/checkpoints/${encodeURIComponent(slug)}/set`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ done: wantDone })
        });
        const isDone = Array.isArray(res.completedSlugs) && res.completedSlugs.includes(slug);
        if (isDone) {
          btn.className = 'btn btn-success';
          btn.textContent = 'Abgehakt';
          flash('rgba(16,185,129,0.25)'); // green flash
        } else {
          btn.className = 'btn btn-secondary';
          btn.textContent = item?.label || labelAttr || 'Checkpoint';
          flash('rgba(239,68,68,0.25)'); // red flash
        }
      } catch (e) {
        alert('Checkpoint konnte nicht gespeichert werden.');
      } finally {
        btn.disabled = false;
      }
    });

    block.innerHTML = '';
    block.appendChild(wrap);
  }

  // ========== AI HINT ==========
  function findQuestionText(btn){
    const q = btn.getAttribute('data-question') || '';
    if (q) return q;
    // try nearest preceding text node/element
    let node = btn.previousElementSibling;
    if (node) {
      const txt = node.textContent || '';
      if (txt.trim().length > 10) return txt.trim().slice(0, 800);
    }
    // fallback to content of module card
    const card = btn.closest('.module-card');
    const txt = card ? (card.querySelector('.module-content')?.textContent || '') : '';
    return txt.trim().slice(0, 800);
  }

  function attachAIHint(btn, courseId, moduleId){
    let holder = el('div', { class:'ai-hint-box', style:{ marginTop:'6px', padding:'8px', border:'1px solid rgba(255,255,255,0.12)', borderRadius:'8px', background:'rgba(15,23,42,0.6)', display:'none' } });
    btn.insertAdjacentElement('afterend', holder);
    btn.addEventListener('click', async ()=>{
      const questionId = btn.getAttribute('data-question-id') || '';
      const qText = findQuestionText(btn);
      btn.disabled = true;
      const old = btn.innerHTML;
      btn.innerHTML = '<i class="bi bi-lightbulb"></i> Lädt…';
      try {
        const res = await fetchJSON(`/api/courses/${courseId}/modules/${moduleId}/tools/ai_hint`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ question: qText, context: questionId ? `question_id: ${questionId}` : '' })
        });
        holder.style.display = '';
        holder.textContent = res.hints || '—';
      } catch (e) {
        holder.style.display = '';
        holder.textContent = 'Hinweis konnte nicht geladen werden.';
      } finally {
        btn.disabled = false;
        btn.innerHTML = old;
      }
    });
  }

  // Public initializer for a single module card
  function initCourseTools(cardEl, courseId){
    if (!cardEl || !courseId) return;
    const moduleId = parseInt(cardEl.getAttribute('data-module-id') || '0', 10);
    if (!moduleId) return;

    // Find tool blocks
    const blocks = $all('[data-tool]', cardEl);
    blocks.forEach(block => {
      const type = (block.getAttribute('data-tool') || '').toLowerCase();
      try {
        if (type === 'quiz') initQuiz(block, courseId, moduleId);
        else if (type === 'poll') initPoll(block, courseId, moduleId);
        else if (type === 'flashcards') initFlashcards(block, courseId, moduleId);
        else if (type === 'notes') initNotes(block, courseId, moduleId);
        else if (type === 'checklist') initChecklist(block, courseId, moduleId);
        else if (type === 'checkpoint') initCheckpoint(block, courseId, moduleId);
      } catch (e) {
        // swallow per-block errors
      }
    });

    // Attach AI hint buttons
    $all('[data-tool="ai-hint"]', cardEl).forEach(btn => {
      attachAIHint(btn, courseId, moduleId);
    });
  }

  // Export
  window.initCourseTools = initCourseTools;
})();
