const profileKey = "diaagent.profile";

const $ = (selector) => document.querySelector(selector);

const elements = {
  form: $("#calcForm"),
  mealText: $("#mealText"),
  ratio: $("#ratio"),
  target: $("#target"),
  correctionFactor: $("#correctionFactor"),
  activeInsulin: $("#activeInsulin"),
  currentGlucose: $("#currentGlucose"),
  useNightscout: $("#useNightscout"),
  manualGlucoseField: $("#manualGlucoseField"),
  profileStatus: $("#profileStatus"),
  paidAccess: $("#paidAccess"),
  nightscoutUrl: $("#nightscoutUrl"),
  nightscoutKey: $("#nightscoutKey"),
  saveProfile: $("#saveProfile"),
  testNightscout: $("#testNightscout"),
  proteinMetric: $("#proteinMetric"),
  fatMetric: $("#fatMetric"),
  carbsMetric: $("#carbsMetric"),
  bolusMetric: $("#bolusMetric"),
  heroBolus: $("#heroBolus"),
  heroCarbs: $("#heroCarbs"),
  resultHint: $("#resultHint"),
  glucoseCard: $("#glucoseCard"),
  foodTable: $("#foodTable"),
  warnings: $("#warnings"),
  explanation: $("#explanation"),
  historyTable: $("#historyTable"),
  toast: $("#toast"),
};

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  window.setTimeout(() => elements.toast.classList.remove("visible"), 2800);
}

function getProfile() {
  try {
    return JSON.parse(localStorage.getItem(profileKey)) || {};
  } catch {
    return {};
  }
}

function saveProfile(profile) {
  localStorage.setItem(profileKey, JSON.stringify(profile));
}

function loadProfile() {
  const profile = getProfile();
  elements.paidAccess.value = String(Boolean(profile.paidAccess));
  elements.nightscoutUrl.value = profile.nightscoutUrl || "";
  elements.nightscoutKey.value = profile.nightscoutKey || "";
  elements.useNightscout.checked = Boolean(
    profile.paidAccess && profile.nightscoutUrl && profile.nightscoutKey,
  );
  updateProfileStatus();
  updateGlucoseMode();
}

function profileReady() {
  const profile = getProfile();
  return Boolean(profile.paidAccess && profile.nightscoutUrl && profile.nightscoutKey);
}

function updateProfileStatus() {
  const dot = document.querySelector(".status-dot");
  if (profileReady()) {
    elements.profileStatus.textContent = "Nightscout подключён";
    dot.classList.add("active");
  } else {
    elements.profileStatus.textContent = "Nightscout не подключён";
    dot.classList.remove("active");
  }
}

function updateGlucoseMode() {
  const enabled = elements.useNightscout.checked;
  elements.manualGlucoseField.classList.toggle("hidden", enabled);
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Запрос не выполнен");
  }
  return payload;
}

function numberValue(input) {
  return Number(input.value.replace(",", "."));
}

function renderTable(container, rows, columns) {
  if (!rows.length) {
    container.className = "food-table empty";
    container.textContent = "Данных пока нет.";
    return;
  }

  const head = columns.map((column) => `<th>${column.label}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((column) => `<td>${row[column.key] ?? "—"}</td>`)
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");

  container.className = "food-table";
  container.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderResult(payload) {
  const nutrition = payload.nutrition;
  const result = payload.result;

  elements.proteinMetric.textContent = `${nutrition.total_protein} г`;
  elements.fatMetric.textContent = `${nutrition.total_fat} г`;
  elements.carbsMetric.textContent = `${nutrition.total_carbs} г`;
  elements.bolusMetric.textContent = `${result.total_bolus} ед.`;
  elements.heroBolus.textContent = `${result.total_bolus} ед.`;
  elements.heroCarbs.textContent = `${nutrition.total_carbs} г углеводов`;
  elements.resultHint.textContent = "Расчёт выполнен.";

  renderTable(elements.foodTable, nutrition.items, [
    { key: "name", label: "Продукт" },
    { key: "weight_g", label: "Масса, г" },
    { key: "protein_g", label: "Белки, г" },
    { key: "fat_g", label: "Жиры, г" },
    { key: "carbs_g", label: "Углеводы, г" },
    { key: "kcal", label: "Ккал" },
    { key: "source", label: "Источник" },
  ]);

  if (payload.glucose) {
    elements.glucoseCard.classList.remove("hidden");
    elements.glucoseCard.textContent = `Nightscout: ${payload.glucose.glucose_mmol} ммоль/л, тренд ${payload.glucose.direction}`;
  } else {
    elements.glucoseCard.classList.add("hidden");
  }

  elements.warnings.innerHTML = payload.warnings
    .map((warning) => `<div class="warning-item">${warning}</div>`)
    .join("");
  elements.explanation.textContent = payload.explanation;
}

async function calculate(event) {
  event.preventDefault();
  const profile = getProfile();
  const useNightscout = elements.useNightscout.checked;

  if (useNightscout && !profileReady()) {
    showToast("Сначала подключите Nightscout в личном кабинете.");
    return;
  }

  const payload = {
    meal_text: elements.mealText.value,
    insulin_to_carb_ratio: numberValue(elements.ratio),
    target_glucose_mmol: numberValue(elements.target),
    correction_factor_mmol: numberValue(elements.correctionFactor),
    active_insulin: numberValue(elements.activeInsulin),
    use_nightscout: useNightscout,
    nightscout_url: profile.nightscoutUrl || "",
    nightscout_api_key: profile.nightscoutKey || "",
  };

  if (!useNightscout) {
    payload.current_glucose_mmol = numberValue(elements.currentGlucose);
  }

  elements.resultHint.textContent = "Считаю...";
  try {
    const result = await apiRequest("/api/calculate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderResult(result);
    await loadHistory();
  } catch (error) {
    elements.resultHint.textContent = "Расчёт не выполнен.";
    showToast(error.message);
  }
}

async function loadHistory() {
  try {
    const payload = await apiRequest("/api/history?limit=12");
    const rows = payload.items.map((item) => ({
      created_at: new Date(item.created_at).toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }),
      carbs_g: item.carbs_g,
      current_glucose_mmol: item.current_glucose_mmol,
      meal_bolus: item.meal_bolus,
      correction_bolus: item.correction_bolus,
      total_bolus: item.total_bolus,
    }));

    renderTable(elements.historyTable, rows, [
      { key: "created_at", label: "Дата" },
      { key: "carbs_g", label: "Углеводы" },
      { key: "current_glucose_mmol", label: "Глюкоза" },
      { key: "meal_bolus", label: "На еду" },
      { key: "correction_bolus", label: "Коррекция" },
      { key: "total_bolus", label: "Итог" },
    ]);
  } catch {
    elements.historyTable.className = "food-table empty";
    elements.historyTable.textContent = "История недоступна.";
  }
}

elements.form.addEventListener("submit", calculate);
elements.useNightscout.addEventListener("change", updateGlucoseMode);

elements.saveProfile.addEventListener("click", () => {
  saveProfile({
    paidAccess: elements.paidAccess.value === "true",
    nightscoutUrl: elements.nightscoutUrl.value.trim(),
    nightscoutKey: elements.nightscoutKey.value.trim(),
  });
  loadProfile();
  showToast("Профиль сохранён в браузере.");
});

elements.testNightscout.addEventListener("click", async () => {
  const profile = getProfile();
  if (!profileReady()) {
    showToast("Сначала заполните профиль Nightscout и активируйте доступ.");
    return;
  }

  try {
    const result = await apiRequest("/api/nightscout/current", {
      method: "POST",
      body: JSON.stringify({
        nightscout_url: profile.nightscoutUrl,
        nightscout_api_key: profile.nightscoutKey,
      }),
    });
    showToast(`Nightscout работает: ${result.glucose_mmol} ммоль/л.`);
  } catch (error) {
    showToast(error.message);
  }
});

loadProfile();
loadHistory();
