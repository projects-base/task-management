// In-page updates: forms and filter links talk to the server with fetch and only
// the #page region is swapped, so actions no longer trigger a full page reload.
(function () {
    const AJAX_HEADERS = { 'X-Requested-With': 'fetch' };
    let filtersOpen = false;
    const collapsedGroups = new Set();
    let refreshSeq = 0;

    const $ = (sel, root = document) => root.querySelector(sel);
    const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

    function toast(message, kind = 'success') {
        const box = $('#toasts');
        if (!box) return;
        const el = document.createElement('div');
        el.className = 'toast ' + kind;
        el.innerHTML = '<i class="fas ' + (kind === 'error' ? 'fa-circle-exclamation' : 'fa-circle-check') + '"></i>';
        el.appendChild(document.createTextNode(' ' + message));
        box.appendChild(el);
        setTimeout(() => el.classList.add('hide'), kind === 'error' ? 5000 : 2200);
        setTimeout(() => el.remove(), kind === 'error' ? 5400 : 2600);
    }

    function setBusy(on) {
        document.body.classList.toggle('busy', on);
    }

    // Re-apply client-only UI state (open filter panel, collapsed groups) after a swap
    function afterRender() {
        const controls = $('#controls');
        if (controls) controls.classList.toggle('open', filtersOpen);
        const toggle = $('[data-toggle-filters]');
        if (toggle) toggle.setAttribute('aria-expanded', String(filtersOpen));
        $$('details.group').forEach(d => {
            if (collapsedGroups.has(d.dataset.group)) d.open = false;
        });
    }

    async function refresh(url, push) {
        const target = url || location.href;
        const seq = ++refreshSeq;
        setBusy(true);
        try {
            const res = await fetch(target, { headers: AJAX_HEADERS, cache: 'no-store' });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
            // A newer navigation started meanwhile; drop this stale response
            if (seq !== refreshSeq) return;
            const fresh = doc.getElementById('page');
            const current = document.getElementById('page');
            if (!fresh || !current) throw new Error('missing #page');
            current.replaceWith(fresh);
            document.title = doc.title;
            if (push) history.pushState(null, '', target);
            afterRender();
        } catch (err) {
            // Fall back to a normal navigation rather than leaving a stale page
            location.href = target;
        } finally {
            if (seq === refreshSeq) setBusy(false);
        }
    }

    async function post(action, formData) {
        const res = await fetch(action, {
            method: 'POST',
            headers: { ...AJAX_HEADERS, 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams(formData),
        });
        let payload = {};
        try { payload = await res.json(); } catch (e) { /* non-JSON error page */ }
        if (!res.ok || payload.ok === false) throw new Error(payload.error || 'Request failed (' + res.status + ')');
    }

    function openModal(id) {
        const modal = document.getElementById(id);
        if (!modal) return;
        modal.classList.add('show');
        const first = $('input:not([type=hidden]), textarea, select', modal);
        if (first) setTimeout(() => first.focus(), 50);
    }

    function closeModals() {
        $$('.modal-overlay.show').forEach(m => m.classList.remove('show'));
    }

    function closeMenus() {
        const dd = $('#settingsDropdown');
        if (dd) dd.classList.remove('show');
        const nav = $('#nav');
        if (nav) nav.classList.remove('open');
    }

    function openEdit(card) {
        const task = JSON.parse(card.dataset.task);
        const form = $('#editForm');
        if (!form) return;
        for (const [name, value] of Object.entries(task)) {
            const field = form.elements.namedItem(name);
            if (field) field.value = value == null ? '' : value;
        }
        openModal('editModal');
    }

    function formToUrl(form) {
        const params = new URLSearchParams(new FormData(form));
        for (const [key, value] of Array.from(params.entries())) {
            if (!value || (key === 'filter' && value === 'all')) params.delete(key);
        }
        const qs = params.toString();
        return form.getAttribute('action') + (qs ? '?' + qs : '');
    }

    document.addEventListener('submit', async (event) => {
        const form = event.target;
        const method = (form.getAttribute('method') || 'GET').toUpperCase();

        if (method === 'GET') {
            if (!form.hasAttribute('data-swap')) return;
            event.preventDefault();
            refresh(formToUrl(form), true);
            return;
        }

        event.preventDefault();
        if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;

        const card = form.closest('.task-card');
        const buttons = $$('button[type=submit], button:not([type])', form);
        buttons.forEach(b => (b.disabled = true));
        if (card) card.classList.add('pending');

        try {
            await post(form.getAttribute('action'), new FormData(form));
            closeModals();
            closeMenus();
            await refresh();
            if (form.dataset.success) toast(form.dataset.success);
        } catch (err) {
            toast(err.message, 'error');
            if (card) card.classList.remove('pending');
        } finally {
            buttons.forEach(b => (b.disabled = false));
        }
    });

    document.addEventListener('change', (event) => {
        const el = event.target;
        if (el.matches('[data-autosubmit]') && el.form) el.form.requestSubmit();
    });

    document.addEventListener('click', (event) => {
        const t = event.target;

        const swapLink = t.closest('a[data-swap]');
        if (swapLink && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
            event.preventDefault();
            refresh(swapLink.href, true);
            return;
        }

        if (t.closest('[data-edit]')) {
            openEdit(t.closest('.task-card'));
            return;
        }

        const opener = t.closest('[data-open-modal]');
        if (opener) {
            openModal(opener.dataset.openModal);
            return;
        }

        if (t.closest('[data-close-modal]') || t.classList.contains('modal-overlay')) {
            closeModals();
            return;
        }

        if (t.closest('[data-toggle-filters]')) {
            filtersOpen = !filtersOpen;
            afterRender();
            return;
        }

        if (t.closest('[data-toggle-settings]')) {
            $('#nav').classList.remove('open');
            $('#settingsDropdown').classList.toggle('show');
            return;
        }

        if (t.closest('[data-toggle-nav]')) {
            $('#settingsDropdown').classList.remove('show');
            $('#nav').classList.toggle('open');
            return;
        }

        if (!t.closest('#settingsDropdown')) $('#settingsDropdown').classList.remove('show');
    });

    // Remember collapsed groups across in-page refreshes
    document.addEventListener('toggle', (event) => {
        const d = event.target;
        if (!(d instanceof HTMLDetailsElement) || !d.dataset.group) return;
        if (d.open) collapsedGroups.delete(d.dataset.group);
        else collapsedGroups.add(d.dataset.group);
    }, true);

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeModals();
            closeMenus();
        }
    });

    window.addEventListener('popstate', () => refresh(location.href, false));

    afterRender();
})();
