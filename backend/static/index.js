// KnowMe public landing page behaviour.
// Created: 2026-05-29
// Created by: ChatGPT / OpenAI, with Rob Voto
// Purpose: Keep public-page interaction logic out of index.html.
// Rules: do not call the LLM endpoint for empty questions; keep public API calls under /api/*.

function createClientId(prefix = 'km') {
      if (window.crypto?.randomUUID) {
        return `${prefix}_${window.crypto.randomUUID()}`;
      }
      return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
    }

    function getStoredId(storage, key, prefix) {
      try {
        const existing = storage.getItem(key);
        if (existing) {
          return existing;
        }
        const created = createClientId(prefix);
        storage.setItem(key, created);
        return created;
      } catch (error) {
        return createClientId(prefix);
      }
    }

    function buildClientContext(sourcePage) {
      return {
        request_id: createClientId('req'),
        client_id: getStoredId(window.localStorage, 'knowme_client_id', 'client'),
        session_id: getStoredId(window.sessionStorage, 'knowme_session_id', 'session'),
        source_page: sourcePage,
        source_path: window.location.pathname
      };
    }

    function setStatus(text, isError = false) {
      const status = document.getElementById('status');
      status.textContent = text || '';
      status.style.color = isError ? '#b62f2f' : 'var(--muted)';
    }

    async function postJSON(url, data) {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      if (!res.ok) {
        let message = `Request failed: ${res.status}`;
        try {
          const body = await res.json();
          if (body && body.detail) {
            message = body.detail;
          }
        } catch (error) {
          // Keep the generic HTTP status when the error body is not JSON.
        }
        throw new Error(message);
      }
      return await res.json();
    }

    async function loadReadyState() {
      try {
        const resp = await fetch('/api/ready');
        if (!resp.ok) throw new Error('Backend responded with error');
        const ready = await resp.json();
        if (!ready.ok) {
          setStatus('Backend content is not ready yet.', true);
          document.getElementById('askBtn').disabled = true;
        }
      } catch (error) {
        setStatus('Backend unavailable', true);
        const askBtn = document.getElementById('askBtn');
        askBtn.disabled = true;
        askBtn.style.opacity = '0.5';
        askBtn.title = 'Backend is currently offline';
      }
    }

    function updateAnswer(text) {
      const pretty = document.getElementById('pretty');
      pretty.textContent = text;
      const copyBtn = document.getElementById('copyBtn');
      copyBtn.style.display = text && text !== '(no answer yet)' ? 'inline-flex' : 'none';
    }

    function buildFollowUps(question) {
      const normalized = (question || '').toLowerCase();
      const suggestions = [];
      const add = (q) => {
        if (!suggestions.includes(q)) {
          suggestions.push(q);
        }
      };

      if (/(tool|technology|platform|software)/.test(normalized)) {
        add('What specific tools or platforms did Rob use in delivery and testing?');
      }
      if (/(ai|automation|llm|machine learning|artificial intelligence)/.test(normalized)) {
        add('What AI or automation projects has Rob worked on?');
        add('Has Rob used LLMs or prompt workflows in real projects?');
      }
      if (/(bpmn|process mapping)/.test(normalized)) {
        add('What experience does Rob have with BPMN or process mapping?');
      }
      if (/(data|sql|reporting|analytics)/.test(normalized)) {
        add('How has Rob used SQL and reporting in past projects?');
      }
      if (/(stakeholder|vendor|client|clients|vendors)/.test(normalized)) {
        add('Give examples of Rob working with stakeholders or vendors.');
      }
      if (/(star|example|challenge|situation|task|action|result)/.test(normalized)) {
        add('Describe a time Rob improved a process. Give a clear example.');
      }
      if (/(fit|strong fit|good fit|why would|why is)/.test(normalized)) {
        add('Why would Rob be a strong fit for a senior business analyst role?');
      }
      if (/(industry|industries|department|organisations|organizations|government)/.test(normalized)) {
        add('What types of organisations has Rob worked with and why are they relevant?');
      }
      if (/(test|uat|quality assurance|qa)/.test(normalized)) {
        add('What experience does Rob have in testing, UAT, or quality assurance?');
      }

      const defaultFollowups = [
        'Why would Rob be a strong fit for a senior business analyst role?',
        'Give examples of Rob working with stakeholders or vendors.',
        'Describe a time Rob improved a process. Give a clear example.',
        'How does Rob approach data analysis or reporting in projects?',
        'What experience does Rob have with BPMN or process mapping?'
      ];

      if (!suggestions.length) {
        return defaultFollowups.slice(0, 3);
      }
      return suggestions.slice(0, 3);
    }

    function renderFollowUps(question = '', backendSuggestions = null) {
      const followups = (backendSuggestions && backendSuggestions.length) ? backendSuggestions : buildFollowUps(question);
      document.getElementById('followups').innerHTML = followups
        .map(q => `<button type="button" class="ex followup" data-q="${q}">${q}</button>`)
        .join('');
      document.querySelectorAll('#followups .followup').forEach(btn => {
        btn.addEventListener('click', () => {
          const q = btn.dataset.q;
          document.getElementById('q').value = q;
          renderFollowUps(q);
        });
      });
    }

    function clearForm() {
      document.getElementById('q').value = '';
      document.getElementById('pretty').textContent = '(no answer yet)';
      document.getElementById('status').textContent = '';
      document.getElementById('copyBtn').style.display = 'none';
      renderFollowUps();
    }

    document.querySelectorAll('button.sample').forEach(btn => {
      btn.addEventListener('click', () => {
        const q = btn.dataset.q;
        const input = document.getElementById('q');
        input.value = q;
        renderFollowUps(q);
        input.scrollIntoView({ behavior: 'smooth', block: 'center' });
        input.focus();
        input.classList.remove('q-loaded');
        void input.offsetWidth;
        input.classList.add('q-loaded');
      });
    });

    async function submitQuestion() {
      const questionInput = document.getElementById('q');
      const question = questionInput.value.trim();

      if (!question) {
        setStatus('Please type a question.', true);
        questionInput.focus();
        return;
      }

      const use_llm = document.getElementById('use_llm').checked;
      const detailed = document.getElementById('detailed_answer').checked ? 'detailed' : 'concise';
      const name = document.getElementById('name').value.trim() || 'unknown';
      const company = document.getElementById('company').value.trim() || 'unknown';
      const askBtn = document.getElementById('askBtn');

      if (askBtn.disabled) return;

      askBtn.disabled = true;
      document.getElementById('pretty').classList.add('is-loading');
      updateAnswer('Thinking...');
      setStatus('');

      try {
        const resp = await postJSON('/api/ask', {
          question,
          use_llm,
          debug: false,
          detail_level: detailed,
          name,
          company,
          ...buildClientContext('landing')
        });
        let text = '';
        if (typeof resp.answer === 'string') {
          text = resp.answer;
        } else if (Array.isArray(resp.answer)) {
          text = resp.answer.join('\n');
        } else {
          text = JSON.stringify(resp, null, 2);
        }
        updateAnswer(text);
        renderFollowUps(question, resp.follow_up_questions || null);
        if (resp.llm_error) {
          setStatus('AI rewrite failed; showing retrieved evidence.', true);
        } else if (resp.answer_source === 'llm') {
          setStatus('AI rewrite used.');
        } else {
          setStatus('Showing retrieved evidence.');
        }
      } catch (error) {
        updateAnswer('(error loading answer)');
        setStatus(error.message || 'Failed to get an answer.', true);
      } finally {
        askBtn.disabled = false;
        document.getElementById('pretty').classList.remove('is-loading');
      }
    }

    document.getElementById('askBtn').addEventListener('click', submitQuestion);
    document.getElementById('q').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        submitQuestion();
      }
    });

    document.getElementById('copyBtn').addEventListener('click', async () => {
      const text = document.getElementById('pretty').textContent;
      if (!text || text === '(no answer yet)') return;
      await navigator.clipboard.writeText(text);
      setStatus('Answer copied to clipboard.');
    });

    document.getElementById('clearBtn').addEventListener('click', clearForm);

    clearForm();
    renderFollowUps();
    loadReadyState();

