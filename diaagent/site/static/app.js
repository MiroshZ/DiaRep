const tokenKey = "diaagent.authToken";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

const state = {
  user: null,
  profile: null,
  historyItems: [],
};

const page = document.body.dataset.page || "home";
const elements = {
  menuToggle: $("#menuToggle"),
  menuOverlay: $("#menuOverlay"),
  navLinks: $$("[data-route]"),
  profileStatus: $("#profileStatus"),
  toast: $("#toast"),
};

function token() {
  return localStorage.getItem(tokenKey) || "";
}

function setToken(value) {
  if (value) {
    localStorage.setItem(tokenKey, value);
  } else {
    localStorage.removeItem(tokenKey);
  }
}

function authHeaders() {
  return token() ? { Authorization: `Bearer ${token()}` } : {};
}

function showToast(message) {
  if (!elements.toast) {
    return;
  }
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  window.setTimeout(() => elements.toast.classList.remove("visible"), 2800);
}

async function apiRequest(url, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...authHeaders(),
    ...(options.headers || {}),
  };
  const response = await fetch(url, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Запрос не выполнен");
  }
  return payload;
}

async function uploadRequest(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Запрос не выполнен");
  }
  return payload;
}

function numberValue(input, fallback = 0) {
  if (!input) {
    return fallback;
  }
  const value = Number(String(input.value).replace(",", "."));
  return Number.isFinite(value) ? value : fallback;
}

function formatNumber(value, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return number.toLocaleString("ru-RU", { maximumFractionDigits: digits });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setMenuOpen(open) {
  document.body.classList.toggle("menu-open", open);
  elements.menuToggle?.setAttribute("aria-expanded", String(open));
}

function setupNavigation() {
  elements.navLinks.forEach((link) => {
    link.classList.toggle("active", link.dataset.route === page);
    link.addEventListener("click", () => setMenuOpen(false));
  });
  elements.menuToggle?.addEventListener("click", () => {
    setMenuOpen(!document.body.classList.contains("menu-open"));
  });
  elements.menuOverlay?.addEventListener("click", () => setMenuOpen(false));
}

function updateProfileStatus() {
  const dot = $(".status-dot");
  if (!elements.profileStatus || !dot) {
    return;
  }

  if (state.user) {
    elements.profileStatus.textContent = `${state.user.name}: вход выполнен`;
    dot.classList.add("active");
  } else {
    elements.profileStatus.textContent = "Вход не выполнен";
    dot.classList.remove("active");
  }
}

async function refreshSession() {
  if (!token()) {
    updateProfileStatus();
    return null;
  }

  try {
    const payload = await apiRequest("/api/auth/me");
    state.user = payload.user;
    state.profile = payload.profile;
    updateProfileStatus();
    return payload;
  } catch {
    setToken("");
    state.user = null;
    state.profile = null;
    updateProfileStatus();
    return null;
  }
}

function renderTable(container, rows, columns) {
  if (!container) {
    return;
  }
  if (!rows.length) {
    container.className = "food-table empty";
    container.textContent = "Данных пока нет.";
    return;
  }

  const head = columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map(
          (column) =>
            `<td data-label="${escapeHtml(column.label)}">${escapeHtml(row[column.key] ?? "—")}</td>`,
        )
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");

  container.className = "food-table";
  container.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderMealLedger(container, rows) {
  if (!container) {
    return;
  }
  if (!rows.length) {
    container.className = "meal-ledger empty";
    container.textContent = "За выбранный период записей нет.";
    return;
  }

  const body = rows
    .map((item) => {
      const createdAt = new Date(item.created_at).toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
      const source =
        item.glucose_source === "nightscout" ? "Nightscout" : "Вручную";

      return `
        <tr>
          <td data-label="Время">
            <strong>${escapeHtml(createdAt)}</strong>
            <small>${escapeHtml(source)}</small>
          </td>
          <td class="meal-cell" data-label="Еда">
            <strong>${escapeHtml(item.meal_text || "Приём пищи")}</strong>
            <small>${formatNumber(item.kcal, 0)} ккал</small>
          </td>
          <td data-label="БЖУ">
            <span class="macro-chip protein">Б ${formatNumber(item.protein_g)} г</span>
            <span class="macro-chip fat">Ж ${formatNumber(item.fat_g)} г</span>
            <span class="macro-chip carbs">У ${formatNumber(item.carbs_g)} г</span>
          </td>
          <td data-label="Глюкоза">${formatNumber(item.current_glucose_mmol)} ммоль/л</td>
          <td data-label="Болюс еды">${formatNumber(item.meal_bolus)} ед.</td>
          <td data-label="Коррекция">${formatNumber(item.correction_bolus)} ед.</td>
          <td data-label="Итог"><strong>${formatNumber(item.total_bolus)} ед.</strong></td>
        </tr>
      `;
    })
    .join("");

  container.className = "meal-ledger";
  container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Время</th>
          <th>Еда</th>
          <th>БЖУ</th>
          <th>Глюкоза</th>
          <th>Болюс еды</th>
          <th>Коррекция</th>
          <th>Итог</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function parseDateStart(value) {
  if (!value) {
    return null;
  }
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function parseDateEnd(value) {
  if (!value) {
    return null;
  }
  const date = new Date(`${value}T23:59:59.999`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function filterByDate(rows, fromValue, toValue) {
  const from = parseDateStart(fromValue);
  const to = parseDateEnd(toValue);

  return rows.filter((item) => {
    const createdAt = new Date(item.created_at);
    if (Number.isNaN(createdAt.getTime())) {
      return false;
    }
    if (from && createdAt < from) {
      return false;
    }
    return !(to && createdAt > to);
  });
}

function profileReadyForNightscout() {
  return Boolean(
    state.user &&
      state.profile?.paid_access_active &&
      state.profile?.nightscout_connected,
  );
}

function applyProfileToCalculator() {
  const profile = state.profile;
  if (!profile) {
    return;
  }
  const ratio = $("#ratio");
  const target = $("#target");
  const correction = $("#correctionFactor");
  if (ratio) {
    ratio.value = profile.insulin_to_carb_ratio || ratio.value;
  }
  if (target) {
    target.value = profile.target_glucose_mmol || target.value;
  }
  if (correction) {
    correction.value = profile.correction_factor_mmol || correction.value;
  }
}

function initCalculatorPage() {
  const form = $("#calcForm");
  if (!form) {
    return;
  }

  const useNightscout = $("#useNightscout");
  const manualGlucoseField = $("#manualGlucoseField");
  const foodPhoto = $("#foodPhoto");
  const recognizePhoto = $("#recognizePhoto");
  const photoPreview = $("#photoPreview");
  const photoResult = $("#photoResult");

  const updateGlucoseMode = () => {
    manualGlucoseField?.classList.toggle("hidden", Boolean(useNightscout?.checked));
  };

  useNightscout?.addEventListener("change", updateGlucoseMode);
  updateGlucoseMode();

  foodPhoto?.addEventListener("change", () => {
    const file = foodPhoto.files?.[0];
    if (!file) {
      photoPreview?.classList.add("hidden");
      if (photoPreview) {
        photoPreview.innerHTML = "";
      }
      return;
    }
    const url = URL.createObjectURL(file);
    photoPreview?.classList.remove("hidden");
    if (photoPreview) {
      photoPreview.innerHTML = `<img src="${url}" alt="Фото еды" />`;
    }
  });

  recognizePhoto?.addEventListener("click", async () => {
    const file = foodPhoto?.files?.[0];
    if (!file) {
      showToast("Сначала выберите фото еды.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    photoResult?.classList.remove("hidden");
    if (photoResult) {
      photoResult.textContent = "Gemini анализирует фото...";
    }

    try {
      const result = await uploadRequest("/api/recognize-food-photo", formData);
      $("#mealText").value = result.meal_text;
      const rows = result.items
        .map((item) => `${item.name} — ${item.weight_g} г (${item.confidence})`)
        .join("; ");
      if (photoResult) {
        photoResult.textContent = `${rows}. ${result.notes || ""}`.trim();
      }
      showToast("Еда распознана и перенесена в форму.");
    } catch (error) {
      if (photoResult) {
        photoResult.textContent = "Распознавание не выполнено.";
      }
      showToast(error.message);
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const resultHint = $("#resultHint");
    const useNightscoutEnabled = Boolean(useNightscout?.checked);

    if (useNightscoutEnabled && !profileReadyForNightscout()) {
      showToast("Сначала войдите и привяжите Nightscout в личном кабинете.");
      return;
    }

    const payload = {
      meal_text: $("#mealText").value,
      insulin_to_carb_ratio: numberValue($("#ratio"), 12),
      target_glucose_mmol: numberValue($("#target"), 6),
      correction_factor_mmol: numberValue($("#correctionFactor"), 2),
      active_insulin: numberValue($("#activeInsulin"), 0),
      use_nightscout: useNightscoutEnabled,
    };

    if (!useNightscoutEnabled) {
      payload.current_glucose_mmol = numberValue($("#currentGlucose"), 6.5);
    }

    if (resultHint) {
      resultHint.textContent = "Считаю...";
    }

    try {
      const payloadResult = await apiRequest("/api/calculate", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      renderCalculationResult(payloadResult);
    } catch (error) {
      if (resultHint) {
        resultHint.textContent = "Расчёт не выполнен.";
      }
      showToast(error.message);
    }
  });
}

function renderCalculationResult(payload) {
  const nutrition = payload.nutrition;
  const result = payload.result;
  $("#proteinMetric").textContent = `${nutrition.total_protein} г`;
  $("#fatMetric").textContent = `${nutrition.total_fat} г`;
  $("#carbsMetric").textContent = `${nutrition.total_carbs} г`;
  $("#bolusMetric").textContent = `${result.total_bolus} ед.`;
  $("#kcalMetric").textContent = `${nutrition.total_kcal} ккал`;
  $("#resultHint").textContent = "Расчёт выполнен.";

  renderTable($("#foodTable"), nutrition.items, [
    { key: "name", label: "Продукт" },
    { key: "weight_g", label: "Масса, г" },
    { key: "protein_g", label: "Белки, г" },
    { key: "fat_g", label: "Жиры, г" },
    { key: "carbs_g", label: "Углеводы, г" },
    { key: "kcal", label: "Ккал" },
    { key: "source", label: "Источник" },
  ]);

  const glucoseCard = $("#glucoseCard");
  if (payload.glucose) {
    glucoseCard?.classList.remove("hidden");
    glucoseCard.textContent = `Nightscout: ${payload.glucose.glucose_mmol} ммоль/л, тренд ${payload.glucose.direction}`;
  } else {
    glucoseCard?.classList.add("hidden");
  }

  $("#warnings").innerHTML = payload.warnings
    .map((warning) => `<div class="warning-item">${escapeHtml(warning)}</div>`)
    .join("");
  $("#explanation").textContent = payload.explanation;
}

function fillProfileForm() {
  const profile = state.profile;
  if (!profile) {
    return;
  }
  $("#paidAccess").value = String(Boolean(profile.paid_access_active));
  $("#nightscoutUrl").value = profile.nightscout_url || "";
  $("#nightscoutKey").value = "";
  $("#accountRatio").value = profile.insulin_to_carb_ratio || 12;
  $("#accountTarget").value = profile.target_glucose_mmol || 6;
  $("#accountCorrectionFactor").value = profile.correction_factor_mmol || 2;
  $("#accessCard").textContent = profile.paid_access_active ? "Активен" : "Не активен";
  $("#nightscoutCard").textContent = profile.nightscout_connected
    ? "Подключён"
    : "Не подключён";
}

function renderAccountState() {
  const authForms = $("#authForms");
  const accountPanel = $("#accountPanel");
  if (!authForms || !accountPanel) {
    return;
  }

  authForms.classList.toggle("hidden", Boolean(state.user));
  accountPanel.classList.toggle("hidden", !state.user);
  if (state.user) {
    $("#accountUserName").textContent = state.user.name;
    $("#accountUserEmail").textContent = state.user.email;
    fillProfileForm();
  }
}

function initAccountPage() {
  if (page !== "account") {
    return;
  }

  $("#registerForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = await apiRequest("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          name: $("#registerName").value,
          email: $("#registerEmail").value,
          password: $("#registerPassword").value,
        }),
      });
      setToken(payload.token);
      await refreshSession();
      renderAccountState();
      showToast("Аккаунт создан.");
    } catch (error) {
      showToast(error.message);
    }
  });

  $("#loginForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = await apiRequest("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: $("#loginEmail").value,
          password: $("#loginPassword").value,
        }),
      });
      setToken(payload.token);
      await refreshSession();
      renderAccountState();
      showToast("Вход выполнен.");
    } catch (error) {
      showToast(error.message);
    }
  });

  $("#saveProfile")?.addEventListener("click", async () => {
    try {
      const payload = {
        paid_access_active: $("#paidAccess").value === "true",
        nightscout_url: $("#nightscoutUrl").value.trim(),
        nightscout_api_key: $("#nightscoutKey").value.trim(),
        insulin_to_carb_ratio: numberValue($("#accountRatio"), 12),
        target_glucose_mmol: numberValue($("#accountTarget"), 6),
        correction_factor_mmol: numberValue($("#accountCorrectionFactor"), 2),
      };
      const result = await apiRequest("/api/profile", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.profile = result.profile;
      fillProfileForm();
      showToast("Профиль сохранён.");
    } catch (error) {
      showToast(error.message);
    }
  });

  $("#testNightscout")?.addEventListener("click", async () => {
    try {
      const result = await apiRequest("/api/nightscout/current", {
        method: "POST",
        body: JSON.stringify({}),
      });
      showToast(`Nightscout работает: ${result.glucose_mmol} ммоль/л.`);
    } catch (error) {
      showToast(error.message);
    }
  });

  $("#logoutButton")?.addEventListener("click", async () => {
    try {
      await apiRequest("/api/auth/logout", { method: "POST" });
    } catch {
      // Сессия могла уже истечь; локальный выход всё равно нужен.
    }
    setToken("");
    state.user = null;
    state.profile = null;
    updateProfileStatus();
    renderAccountState();
    showToast("Вы вышли из аккаунта.");
  });
}

function initJournalPage() {
  if (page !== "journal") {
    return;
  }

  const fromInput = $("#historyDateFrom");
  const toInput = $("#historyDateTo");
  const renderFilteredHistory = () => {
    renderMealLedger(
      $("#historyTable"),
      filterByDate(state.historyItems, fromInput?.value, toInput?.value),
    );
  };

  fromInput?.addEventListener("change", renderFilteredHistory);
  toInput?.addEventListener("change", renderFilteredHistory);
  $("#historyClearDates")?.addEventListener("click", () => {
    fromInput.value = "";
    toInput.value = "";
    renderFilteredHistory();
  });

  loadHistory(renderFilteredHistory);
}

async function loadHistory(renderFilteredHistory) {
  const authNotice = $("#journalAuthNotice");
  const journalContent = $("#journalContent");
  if (!state.user) {
    authNotice?.classList.remove("hidden");
    journalContent?.classList.add("hidden");
    return;
  }

  authNotice?.classList.add("hidden");
  journalContent?.classList.remove("hidden");
  try {
    const payload = await apiRequest("/api/history?limit=50");
    state.historyItems = payload.items;
    renderFilteredHistory();
  } catch (error) {
    showToast(error.message);
  }
}

async function init() {
  setupNavigation();
  await refreshSession();
  applyProfileToCalculator();
  initCalculatorPage();
  initAccountPage();
  renderAccountState();
  initJournalPage();
}

init();
