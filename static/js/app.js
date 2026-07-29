(() => {
  document.documentElement.classList.add("js-ready");

  const NAV_OPEN_KEY = "hrms.navOpen";

  function readOpenIds() {
    try {
      const raw = sessionStorage.getItem(NAV_OPEN_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
    } catch {
      return [];
    }
  }

  function writeOpenIds(ids) {
    try {
      sessionStorage.setItem(NAV_OPEN_KEY, JSON.stringify([...new Set(ids)]));
    } catch {
      /* ignore quota / private mode */
    }
  }

  function setDropdownOpen(item, open, { persist = true, animate = false } = {}) {
    if (animate) item.classList.add("nav-anim");
    item.classList.toggle("is-open", open);
    const btn = item.querySelector(":scope > [data-nav-toggle]");
    if (btn) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.classList.toggle("active-branch", open);
    }
    const submenu = item.querySelector(":scope > .nav-submenu");
    if (submenu) submenu.classList.toggle("is-open", open);
    if (!persist) return;
    const id = item.getAttribute("data-nav-id");
    if (!id) return;
    const ids = readOpenIds();
    if (open) {
      if (!ids.includes(id)) ids.push(id);
      writeOpenIds(ids);
    } else {
      writeOpenIds(ids.filter((x) => x !== id));
    }
  }

  // Restore menus the user left open (do not auto-accumulate server opens —
  // that kept every visited section expanded and broke scroll).
  readOpenIds().forEach((id) => {
    const item = document.querySelector(
      `.nav-dropdown[data-nav-id="${CSS.escape(id)}"]`
    );
    if (item && !item.classList.contains("is-open")) {
      setDropdownOpen(item, true, { persist: false });
    }
  });

  document.querySelectorAll("[data-nav-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const item = btn.closest(".nav-dropdown");
      if (!item) return;
      setDropdownOpen(item, !item.classList.contains("is-open"), { animate: true });
    });
  });

  initSidebarScroll();
  initMobileNav();
  initSidebarRail();
  initContentSelects();
  initRegisterFilter();
  initPasswordToggles();
})();

function initSidebarRail() {
  const btn = document.querySelector("[data-sidebar-toggle]");
  if (!btn) return;
  const KEY = "hrms.sidebar";
  const mq = window.matchMedia("(max-width: 960px)");

  function mode() {
    return document.documentElement.getAttribute("data-sidebar") === "short"
      ? "short"
      : "open";
  }

  function syncUi() {
    const short = !mq.matches && mode() === "short";
    const drawerOpen = document.body.classList.contains("nav-open");
    // Mobile: arrow means close drawer when open; Desktop: left=collapse, right=expand
    const showExpand = mq.matches ? false : short;
    btn.setAttribute("aria-pressed", showExpand ? "true" : "false");
    if (mq.matches) {
      btn.setAttribute("aria-label", "Close menu");
      btn.setAttribute("title", "Close menu");
    } else {
      btn.setAttribute(
        "aria-label",
        showExpand ? "Expand sidebar" : "Collapse sidebar"
      );
      btn.setAttribute(
        "title",
        showExpand ? "Expand sidebar" : "Collapse sidebar"
      );
    }
    const collapseIco = btn.querySelector(".sidebar-rail-ico-collapse");
    const expandIco = btn.querySelector(".sidebar-rail-ico-expand");
    if (collapseIco && expandIco) {
      if (showExpand) {
        collapseIco.setAttribute("hidden", "");
        expandIco.removeAttribute("hidden");
      } else {
        expandIco.setAttribute("hidden", "");
        collapseIco.removeAttribute("hidden");
      }
    }
    // Keep button useful on mobile only when drawer is open
    btn.hidden = mq.matches && !drawerOpen;
  }

  function setMode(next) {
    if (mq.matches) return;
    document.documentElement.setAttribute("data-sidebar", next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
    syncUi();
  }

  btn.addEventListener("click", () => {
    if (mq.matches) {
      document.body.classList.remove("nav-open");
      const openBtn = document.querySelector("[data-nav-open]");
      const backdrop = document.querySelector("[data-nav-backdrop]");
      openBtn?.setAttribute("aria-expanded", "false");
      backdrop?.setAttribute("hidden", "");
      syncUi();
      return;
    }
    setMode(mode() === "short" ? "open" : "short");
  });

  mq.addEventListener("change", () => syncUi());
  document.addEventListener("nav-drawer-change", () => syncUi());
  syncUi();
}

function initMobileNav() {
  const openBtn = document.querySelector("[data-nav-open]");
  const closeBtn = document.querySelector("[data-nav-close]");
  const backdrop = document.querySelector("[data-nav-backdrop]");
  const sidebar = document.getElementById("app-sidebar");
  if (!openBtn || !sidebar) return;

  const mq = window.matchMedia("(max-width: 960px)");

  function setOpen(open) {
    document.body.classList.toggle("nav-open", open);
    openBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (backdrop) {
      if (open) backdrop.removeAttribute("hidden");
      else backdrop.setAttribute("hidden", "");
    }
    document.dispatchEvent(new CustomEvent("nav-drawer-change"));
  }

  function close() {
    setOpen(false);
  }

  openBtn.addEventListener("click", () => setOpen(true));
  closeBtn?.addEventListener("click", close);
  backdrop?.addEventListener("click", close);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.body.classList.contains("nav-open")) {
      close();
    }
  });

  sidebar.querySelectorAll("a[href]").forEach((a) => {
    a.addEventListener("click", () => {
      if (mq.matches) close();
    });
  });

  mq.addEventListener("change", (e) => {
    if (!e.matches) close();
  });
}

function initSidebarScroll() {
  const nav = document.getElementById("side-nav");
  if (!nav) return;

  const KEY = "hrms.sidebarScroll";
  let suppressSave = false;
  let savedY = 0;

  try {
    const n = Number(sessionStorage.getItem(KEY));
    savedY = Number.isFinite(n) && n > 0 ? n : 0;
  } catch {
    savedY = 0;
  }

  function writeScroll(force) {
    if (suppressSave && !force) return;
    try {
      const y = Math.max(0, Math.round(nav.scrollTop));
      // Never clobber a real saved position with 0 during early layout
      if (y === 0 && savedY > 0 && !force) return;
      savedY = y;
      sessionStorage.setItem(KEY, String(y));
    } catch {
      /* ignore */
    }
  }

  function restoreScroll() {
    if (savedY <= 0) return;
    suppressSave = true;
    const max = Math.max(0, nav.scrollHeight - nav.clientHeight);
    if (max <= 0) {
      suppressSave = false;
      return false;
    }
    nav.scrollTop = Math.min(savedY, max);
    suppressSave = false;
    return true;
  }

  // Restore after dropdowns/layout; retry until scroll metrics exist
  let tries = 0;
  const tryRestore = () => {
    tries += 1;
    if (restoreScroll() || tries >= 12) return;
    window.setTimeout(tryRestore, 40);
  };
  requestAnimationFrame(tryRestore);

  let ticking = false;
  nav.addEventListener(
    "scroll",
    () => {
      if (suppressSave || ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        writeScroll(true);
        ticking = false;
      });
    },
    { passive: true }
  );

  const saveNow = () => writeScroll(true);
  nav.addEventListener("click", (e) => {
    if (e.target.closest("a[href], [data-nav-toggle]")) saveNow();
  });
  document.querySelectorAll(".sidebar a[href]").forEach((a) => {
    a.addEventListener("click", saveNow);
  });
  window.addEventListener("pagehide", saveNow);
  window.addEventListener("beforeunload", saveNow);
}

function initPasswordToggles() {
  document.querySelectorAll("[data-password-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wrap = btn.closest(".password-field");
      const input = wrap && wrap.querySelector("input");
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      btn.setAttribute("title", show ? "Hide password" : "Show password");
      btn.classList.toggle("is-visible", show);
    });
  });
}

function initRegisterFilter() {
  const page = document.querySelector("[data-register-page]");
  if (!page) return;
  const input = page.querySelector("[data-register-filter]");
  if (!input) return;

  const rows = Array.from(page.querySelectorAll("[data-register-row]"));
  const countEl = page.querySelector("[data-register-count]");
  const emptyEl = page.querySelector("[data-register-empty]");
  const clearBtn = page.querySelector("[data-register-clear]");

  const setEmptyVisible = (show) => {
    if (!emptyEl) return;
    emptyEl.hidden = !show;
    emptyEl.classList.toggle("is-visible", show);
  };

  const apply = () => {
    const q = (input.value || "").trim().toLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const hay = (row.getAttribute("data-search") || "").toLowerCase();
      const show = !q || hay.includes(q);
      row.style.display = show ? "" : "none";
      if (show) visible += 1;
    });
    if (countEl) {
      countEl.textContent = q
        ? `${visible} of ${rows.length} shown`
        : `${rows.length} shown`;
    }
    // Only show overlay when a search is active and nothing matches
    setEmptyVisible(Boolean(q) && visible === 0 && rows.length > 0);
    if (clearBtn) clearBtn.hidden = !q;
  };

  input.addEventListener("input", apply);
  input.addEventListener("search", apply);
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      input.value = "";
      input.focus();
      apply();
    });
  }
  apply();
}

let activeSearchSelect = null;

function initContentSelects() {
  const root = document.querySelector("main.content");
  if (!root) return;

  root.querySelectorAll("select:not([multiple]):not([data-ss-ready])").forEach((select) => {
    const searchable =
      select.hasAttribute("data-searchable") ||
      /^(employee|manager|user)$/i.test(select.name || "") ||
      (select.name || "").includes("employee") ||
      (select.name || "").includes("manager") ||
      select.options.length >= 10;

    enhanceSelect(select, { searchable });
  });
}

function enhanceSelect(select, { searchable }) {
  if (select.dataset.ssReady) return;
  select.dataset.ssReady = "1";

  const wrap = document.createElement("div");
  wrap.className = "ss" + (searchable ? " ss-searchable" : "");
  select.parentNode.insertBefore(wrap, select);
  wrap.appendChild(select);
  select.classList.add("ss-native");
  select.tabIndex = -1;
  select.setAttribute("aria-hidden", "true");

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "ss-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");

  const label = document.createElement("span");
  label.className = "ss-label";
  trigger.appendChild(label);

  const chevron = document.createElement("span");
  chevron.className = "ss-chevron";
  chevron.setAttribute("aria-hidden", "true");
  trigger.appendChild(chevron);

  const panel = document.createElement("div");
  panel.className = "ss-panel";
  panel.hidden = true;

  let searchInput = null;
  if (searchable) {
    const searchWrap = document.createElement("div");
    searchWrap.className = "ss-search";
    searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.className = "ss-search-input";
    searchInput.placeholder =
      select.getAttribute("data-search-placeholder") || "Type to search…";
    searchInput.autocomplete = "off";
    searchInput.setAttribute("aria-label", "Search options");
    searchWrap.appendChild(searchInput);
    panel.appendChild(searchWrap);
  }

  const list = document.createElement("ul");
  list.className = "ss-list";
  list.setAttribute("role", "listbox");
  panel.appendChild(list);

  wrap.appendChild(trigger);
  // Portal to body so panel isn't clipped by .panel { overflow: hidden }
  document.body.appendChild(panel);

  const api = { wrap, trigger, panel, select, searchInput, close, open, positionPanel };
  wrap._ss = api;

  function optionText(opt) {
    return (opt.textContent || "").trim();
  }

  function syncLabel() {
    const opt = select.options[select.selectedIndex];
    label.textContent = opt ? optionText(opt) : "Select…";
    label.classList.toggle("is-placeholder", !opt || !opt.value);
  }

  function buildList(filter) {
    list.innerHTML = "";
    const q = (filter || "").trim().toLowerCase();
    let visible = 0;
    Array.from(select.options).forEach((opt, idx) => {
      const text = optionText(opt);
      if (q && !text.toLowerCase().includes(q)) return;
      visible += 1;
      const li = document.createElement("li");
      li.className = "ss-option";
      li.setAttribute("role", "option");
      li.dataset.index = String(idx);
      li.textContent = text || "—";
      if (opt.disabled) {
        li.classList.add("is-disabled");
        li.setAttribute("aria-disabled", "true");
      }
      if (opt.selected) {
        li.classList.add("is-selected");
        li.setAttribute("aria-selected", "true");
      }
      if (!opt.value) li.classList.add("is-empty");
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (opt.disabled) return;
        select.selectedIndex = idx;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        syncLabel();
        close();
        trigger.focus();
      });
      list.appendChild(li);
    });
    if (!visible) {
      const empty = document.createElement("li");
      empty.className = "ss-empty";
      empty.textContent = "No matches";
      list.appendChild(empty);
    }
  }

  function positionPanel() {
    const rect = trigger.getBoundingClientRect();
    const gutter = 8;
    const maxH = Math.min(320, window.innerHeight - gutter * 2);
    const spaceBelow = window.innerHeight - rect.bottom - gutter;
    const spaceAbove = rect.top - gutter;
    const openUp = spaceBelow < 180 && spaceAbove > spaceBelow;

    const width = Math.max(rect.width, searchable ? 260 : rect.width);
    let left = rect.left;
    if (left + width > window.innerWidth - gutter) {
      left = Math.max(gutter, window.innerWidth - width - gutter);
    }

    panel.style.position = "fixed";
    panel.style.zIndex = "10050";
    panel.style.width = `${width}px`;
    panel.style.left = `${left}px`;
    panel.style.right = "auto";
    panel.style.maxHeight = `${maxH}px`;

    if (openUp) {
      panel.style.top = "auto";
      panel.style.bottom = `${window.innerHeight - rect.top + 6}px`;
    } else {
      panel.style.bottom = "auto";
      panel.style.top = `${rect.bottom + 6}px`;
    }
  }

  function open() {
    if (activeSearchSelect && activeSearchSelect !== api) {
      activeSearchSelect.close();
    }
    activeSearchSelect = api;
    wrap.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    panel.hidden = false;
    panel.classList.add("is-open");
    if (searchInput) searchInput.value = "";
    buildList("");
    positionPanel();
    if (searchInput) {
      requestAnimationFrame(() => searchInput.focus());
    }
  }

  function close() {
    if (activeSearchSelect === api) activeSearchSelect = null;
    wrap.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
    panel.hidden = true;
    panel.classList.remove("is-open");
  }

  trigger.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (select.disabled) return;
    if (wrap.classList.contains("is-open")) close();
    else open();
  });

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      buildList(searchInput.value);
      positionPanel();
    });
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
        trigger.focus();
      }
    });
    searchInput.addEventListener("mousedown", (e) => e.stopPropagation());
    searchInput.addEventListener("click", (e) => e.stopPropagation());
  }

  panel.addEventListener("mousedown", (e) => e.stopPropagation());

  select.addEventListener("change", syncLabel);
  syncLabel();

  if (select.disabled) {
    wrap.classList.add("is-disabled");
    trigger.disabled = true;
  }
}

document.addEventListener("mousedown", (e) => {
  if (!activeSearchSelect) return;
  const { wrap, panel } = activeSearchSelect;
  if (wrap.contains(e.target) || panel.contains(e.target)) return;
  activeSearchSelect.close();
});

window.addEventListener(
  "scroll",
  () => {
    if (activeSearchSelect) activeSearchSelect.positionPanel();
  },
  true
);

window.addEventListener("resize", () => {
  if (activeSearchSelect) activeSearchSelect.positionPanel();
});

/* —— Salary line Amount / % guidance —— */
function payLineSelectedOption(select) {
  if (!select || select.selectedIndex < 0) return null;
  return select.options[select.selectedIndex] || null;
}

function syncPayLineRow(row) {
  const select =
    row.querySelector("select.pay-line-component") ||
    row.querySelector("select[name$='-component']");
  const guide = row.querySelector("[data-pay-guide]");
  const amountWrap = row.querySelector(".pay-input-amount");
  const percentWrap = row.querySelector(".pay-input-percent");
  const percentInput = row.querySelector(".pay-line-percent");
  if (!select || !guide) return;

  const opt = payLineSelectedOption(select);
  const calc = (opt && opt.getAttribute("data-calc")) || "";
  const defPct = (opt && opt.getAttribute("data-percent")) || "";
  const isBasic = opt && opt.getAttribute("data-basic") === "1";

  guide.classList.remove("is-percent", "is-fixed");
  if (!opt || !opt.value) {
    guide.textContent = "—";
    return;
  }
  if (isBasic) {
    guide.textContent = "Basic — enter fixed Amount";
    guide.classList.add("is-fixed");
    if (amountWrap) amountWrap.classList.add("is-emphasis");
    if (percentWrap) percentWrap.classList.remove("is-emphasis");
    return;
  }
  if (calc === "percent_basic") {
    guide.textContent = defPct
      ? `% of Basic (default ${defPct}%)`
      : "% of Basic — fill %";
    guide.classList.add("is-percent");
    if (percentWrap) percentWrap.classList.add("is-emphasis");
    if (amountWrap) amountWrap.classList.remove("is-emphasis");
    if (percentInput && !percentInput.value && defPct) {
      percentInput.value = defPct;
    }
    return;
  }
  if (calc === "percent_gross") {
    guide.textContent = defPct
      ? `% of Gross (default ${defPct}%)`
      : "% of Gross — fill %";
    guide.classList.add("is-percent");
    if (percentWrap) percentWrap.classList.add("is-emphasis");
    if (amountWrap) amountWrap.classList.remove("is-emphasis");
    if (percentInput && !percentInput.value && defPct) {
      percentInput.value = defPct;
    }
    return;
  }
  guide.textContent = "Fixed — use Amount";
  guide.classList.add("is-fixed");
  if (amountWrap) amountWrap.classList.add("is-emphasis");
  if (percentWrap) percentWrap.classList.remove("is-emphasis");
}

function initPayLines(root) {
  const scope = root || document;
  scope.querySelectorAll("[data-pay-line]").forEach((row) => {
    const select =
      row.querySelector("select.pay-line-component") ||
      row.querySelector("select[name$='-component']");
    if (!select || select.dataset.payLineBound === "1") return;
    select.dataset.payLineBound = "1";
    select.addEventListener("change", () => syncPayLineRow(row));
    syncPayLineRow(row);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initPayLines();
  initExpenseClaimForm();
});

function initExpenseClaimForm() {
  const root = document.querySelector("[data-expense-form]");
  if (!root) return;

  const list = root.querySelector("[data-exp-line-list]");
  const totalEl = root.querySelector("[data-exp-total]");
  const totalCurEl = root.querySelector("[data-exp-total-currency]");
  const countEl = root.querySelector("[data-exp-line-count]");
  const currencySelect = root.querySelector(".exp-currency-select, select[name='currency']");
  const addBtn = root.querySelector("[data-exp-add-line]");
  const tmpl = root.querySelector("[data-exp-empty-form]");
  const totalForms = root.querySelector("#id_lines-TOTAL_FORMS");

  const currencyCode = () => {
    if (!currencySelect) return totalCurEl?.textContent?.trim() || "AED";
    const opt = currencySelect.selectedOptions?.[0];
    const raw = (opt?.value || currencySelect.value || "AED").trim();
    return raw || "AED";
  };

  const syncCurrencyAffixes = () => {
    const code = currencyCode();
    root.querySelectorAll("[data-exp-currency-affix]").forEach((el) => {
      el.textContent = code;
    });
    if (totalCurEl) totalCurEl.textContent = code;
  };

  const refreshIndexes = () => {
    let n = 0;
    list.querySelectorAll("[data-exp-line]").forEach((card) => {
      if (card.classList.contains("is-removed")) return;
      n += 1;
      const idx = card.querySelector("[data-exp-line-index]");
      if (idx) idx.textContent = `#${n}`;
    });
  };

  const updateReceiptHint = (card) => {
    const select = card.querySelector(".exp-line-category, select[name*='-category']");
    const hint = card.querySelector("[data-exp-receipt-hint]");
    if (!select || !hint) return;
    const opt = select.selectedOptions?.[0];
    const needed = opt?.getAttribute("data-receipt") === "1";
    hint.hidden = !needed;
  };

  const updateReceiptName = (card) => {
    const input = card.querySelector(".exp-line-receipt-input, input[type='file']");
    const nameEl = card.querySelector("[data-exp-receipt-name]");
    const drop = card.querySelector("[data-exp-receipt]");
    if (!input || !nameEl) return;
    const file = input.files && input.files[0];
    if (file) {
      nameEl.textContent = file.name;
      drop?.classList.add("has-file");
    } else {
      nameEl.textContent = "PDF or image";
      drop?.classList.remove("has-file");
    }
  };

  const updateTotal = () => {
    let total = 0;
    let lines = 0;
    list.querySelectorAll("[data-exp-line]").forEach((card) => {
      if (card.classList.contains("is-removed")) return;
      const amountInput = card.querySelector(".exp-line-amount, input[name*='-amount']");
      const val = parseFloat(amountInput?.value || "");
      if (!Number.isFinite(val) || val <= 0) return;
      total += val;
      lines += 1;
    });
    if (totalEl) totalEl.textContent = total.toFixed(2);
    if (countEl) countEl.textContent = String(lines);
  };

  const wireCard = (card) => {
    updateReceiptHint(card);
    updateReceiptName(card);

    card.querySelector(".exp-line-category, select[name*='-category']")
      ?.addEventListener("change", () => updateReceiptHint(card));

    card.querySelector(".exp-line-amount, input[name*='-amount']")
      ?.addEventListener("input", updateTotal);

    card.querySelector(".exp-line-receipt-input, input[type='file']")
      ?.addEventListener("change", () => updateReceiptName(card));

    const del = card.querySelector("input[name*='-DELETE']");
    if (del) {
      const applyRemoved = () => {
        card.classList.toggle("is-removed", del.checked);
        refreshIndexes();
        updateTotal();
      };
      del.addEventListener("change", applyRemoved);
      if (del.checked) applyRemoved();
    }
  };

  list.querySelectorAll("[data-exp-line]").forEach(wireCard);

  currencySelect?.addEventListener("change", () => {
    syncCurrencyAffixes();
  });
  syncCurrencyAffixes();
  refreshIndexes();
  updateTotal();

  addBtn?.addEventListener("click", () => {
    if (!tmpl || !totalForms || !list) return;
    const index = parseInt(totalForms.value, 10) || 0;
    const html = tmpl.innerHTML.replace(/__prefix__/g, String(index));
    const wrap = document.createElement("div");
    wrap.innerHTML = html.trim();
    const card = wrap.firstElementChild;
    if (!card) return;
    list.appendChild(card);
    totalForms.value = String(index + 1);
    // Re-enhance new selects (searchable / styled)
    if (typeof initContentSelects === "function") initContentSelects();
    wireCard(card);
    syncCurrencyAffixes();
    refreshIndexes();
    updateTotal();
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
}
document.addEventListener("change", (e) => {
  const t = e.target;
  if (
    t instanceof HTMLInputElement &&
    t.matches("[data-attendance-inline-field]")
  ) {
    const form = t.form;
    const row = t.closest("tr");
    if (form instanceof HTMLFormElement) {
      row?.classList.add("is-saving");
      row?.setAttribute("aria-busy", "true");
      form.requestSubmit();
      return;
    }
  }
  if (
    t instanceof HTMLElement &&
    t.matches("[data-auto-submit-field]")
  ) {
    const form = t.closest("form[data-auto-submit]");
    if (form instanceof HTMLFormElement) {
      form.requestSubmit();
      return;
    }
  }
  if (!(t instanceof HTMLSelectElement)) return;
  if (!t.matches(".pay-line-component, select[name$='-component']")) return;
  const row = t.closest("[data-pay-line]");
  if (row) syncPayLineRow(row);
});

document.addEventListener("click", (e) => {
  const target = e.target;
  if (!(target instanceof Element)) return;
  const button = target.closest("[data-date-picker-for]");
  if (!(button instanceof HTMLButtonElement)) return;
  const inputId = button.dataset.datePickerFor;
  const input = inputId ? document.getElementById(inputId) : null;
  if (!(input instanceof HTMLInputElement) || input.type !== "date") return;
  try {
    input.showPicker();
  } catch {
    input.focus();
    input.click();
  }
});

const autoSearchTimers = new WeakMap();
document.addEventListener("DOMContentLoaded", () => {
  const input = document.querySelector("[data-auto-search-field][autofocus]");
  if (!(input instanceof HTMLInputElement) || !input.value) return;
  input.focus({ preventScroll: true });
  const end = input.value.length;
  input.setSelectionRange(end, end);
});

document.addEventListener("input", (e) => {
  const target = e.target;
  if (
    !(target instanceof HTMLInputElement) ||
    !target.matches("[data-auto-search-field]")
  ) {
    return;
  }
  const form = target.closest("form[data-auto-search]");
  if (!(form instanceof HTMLFormElement)) return;

  const previous = autoSearchTimers.get(form);
  if (previous) window.clearTimeout(previous);
  const timer = window.setTimeout(() => form.requestSubmit(), 450);
  autoSearchTimers.set(form, timer);
});

document.addEventListener("click", (e) => {
  const toggle = e.target.closest("[data-absent-toggle]");
  const openMenus = document.querySelectorAll(".absent-leave.is-open");

  if (toggle) {
    e.preventDefault();
    const root = toggle.closest("[data-absent-leave]");
    const menu = root?.querySelector(".absent-leave-menu");
    const willOpen = !root?.classList.contains("is-open");
    openMenus.forEach((item) => {
      item.classList.remove("is-open");
      item.classList.remove("is-up");
      const btn = item.querySelector("[data-absent-toggle]");
      const panel = item.querySelector(".absent-leave-menu");
      if (btn) btn.setAttribute("aria-expanded", "false");
      if (panel) panel.hidden = true;
    });
    if (root && menu && willOpen) {
      root.classList.add("is-open");
      toggle.setAttribute("aria-expanded", "true");
      menu.hidden = false;
      const triggerRect = toggle.getBoundingClientRect();
      const menuHeight = menu.getBoundingClientRect().height;
      const roomBelow = window.innerHeight - triggerRect.bottom;
      const roomAbove = triggerRect.top;
      root.classList.toggle(
        "is-up",
        roomBelow < menuHeight + 16 && roomAbove > roomBelow
      );
    }
    return;
  }

  if (!e.target.closest("[data-absent-leave]")) {
    openMenus.forEach((item) => {
      item.classList.remove("is-open");
      item.classList.remove("is-up");
      const btn = item.querySelector("[data-absent-toggle]");
      const panel = item.querySelector(".absent-leave-menu");
      if (btn) btn.setAttribute("aria-expanded", "false");
      if (panel) panel.hidden = true;
    });
  }
});

/* Right-side filter drawers (Manage shifts / Bulk assign) */
(() => {
  const drawers = document.querySelectorAll("[data-filter-drawer]");
  if (!drawers.length) return;

  drawers.forEach((drawer) => {
    const backdrop =
      drawer.previousElementSibling?.matches?.("[data-filter-drawer-backdrop]")
        ? drawer.previousElementSibling
        : document.querySelector("[data-filter-drawer-backdrop]");
    const openButtons = document.querySelectorAll(
      `[data-filter-drawer-open][aria-controls="${drawer.id}"], [data-filter-drawer-open]:not([aria-controls])`
    );
    const closeButton = drawer.querySelector("[data-filter-drawer-close]");
    let trigger = null;

    function setOpen(open) {
      drawer.classList.toggle("is-open", open);
      drawer.setAttribute("aria-hidden", open ? "false" : "true");
      if (backdrop) backdrop.hidden = !open;
      document.body.classList.toggle("bulk-filter-is-open", open);
      openButtons.forEach((button) => {
        button.setAttribute("aria-expanded", open ? "true" : "false");
      });
      if (open) {
        window.setTimeout(() => {
          drawer.querySelector("input, select, button")?.focus();
        }, 80);
      } else {
        trigger?.focus();
      }
    }

    openButtons.forEach((button) => {
      if (button.getAttribute("aria-controls") && button.getAttribute("aria-controls") !== drawer.id) {
        return;
      }
      button.addEventListener("click", () => {
        trigger = button;
        setOpen(true);
      });
    });
    closeButton?.addEventListener("click", () => setOpen(false));
    backdrop?.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && drawer.classList.contains("is-open")) {
        setOpen(false);
      }
    });
  });
})();
