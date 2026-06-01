const profileKey = "diaagent.profile";

const $ = (selector) => document.querySelector(selector);

const elements = {
  form: $("#calcForm"),
  mealText: $("#mealText"),
  foodPhoto: $("#foodPhoto"),
  recognizePhoto: $("#recognizePhoto"),
  photoPreview: $("#photoPreview"),
  photoResult: $("#photoResult"),
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
  applyProfile: $("#applyProfile"),
  accountRatio: $("#accountRatio"),
  accountTarget: $("#accountTarget"),
  accountCorrectionFactor: $("#accountCorrectionFactor"),
  accessCard: $("#accessCard"),
  nightscoutCard: $("#nightscoutCard"),
  lastGlucoseCard: $("#lastGlucoseCard"),
  lastGlucoseHint: $("#lastGlucoseHint"),
  proteinMetric: $("#proteinMetric"),
  fatMetric: $("#fatMetric"),
  carbsMetric: $("#carbsMetric"),
  bolusMetric: $("#bolusMetric"),
  kcalMetric: $("#kcalMetric"),
  heroBolus: $("#heroBolus"),
  heroCarbs: $("#heroCarbs"),
  resultHint: $("#resultHint"),
  glucoseCard: $("#glucoseCard"),
  foodTable: $("#foodTable"),
  warnings: $("#warnings"),
  explanation: $("#explanation"),
  accountHistoryTable: $("#accountHistoryTable"),
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

function formatNumber(value, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return number.toLocaleString("ru-RU", {
    maximumFractionDigits: digits,
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function loadProfile() {
  const profile = getProfile();
  elements.paidAccess.value = String(Boolean(profile.paidAccess));
  elements.nightscoutUrl.value = profile.nightscoutUrl || "";
  elements.nightscoutKey.value = profile.nightscoutKey || "";
  elements.accountRatio.value = profile.insulinToCarbRatio || elements.ratio.value;
  elements.accountTarget.value = profile.targetGlucoseMmol || elements.target.value;
  elements.accountCorrectionFactor.value =
    profile.correctionFactorMmol || elements.correctionFactor.value;
  if (profile.insulinToCarbRatio) {
    elements.ratio.value = profile.insulinToCarbRatio;
  }
  if (profile.targetGlucoseMmol) {
    elements.target.value = profile.targetGlucoseMmol;
  }
  if (profile.correctionFactorMmol) {
    elements.correctionFactor.value = profile.correctionFactorMmol;
  }
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
  const profile = getProfile();
  elements.accessCard.textContent = profile.paidAccess ? "Активен" : "Не активен";
  elements.nightscoutCard.textContent = profileReady() ? "Подключён" : "Не подключён";
  if (profile.lastGlucoseMmol) {
    elements.lastGlucoseCard.textContent = `${profile.lastGlucoseMmol} ммоль/л`;
    elements.lastGlucoseHint.textContent = profile.lastGlucoseAt
      ? `Обновлено ${new Date(profile.lastGlucoseAt).toLocaleString("ru-RU")}`
      : "Получено из Nightscout";
  } else {
    elements.lastGlucoseCard.textContent = "—";
    elements.lastGlucoseHint.textContent = "Проверка ещё не выполнялась";
  }

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

async function uploadRequest(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    body: formData,
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
        .map((column) => `<td>${escapeHtml(row[column.key] ?? "—")}</td>`)
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");

  container.className = "food-table";
  container.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderMealLedger(container, rows) {
  if (!rows.length) {
    container.className = "meal-ledger empty";
    container.textContent = "Журнал пока пуст.";
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
          <td>
            <strong>${escapeHtml(createdAt)}</strong>
            <small>${escapeHtml(source)}</small>
          </td>
          <td class="meal-cell">
            <strong>${escapeHtml(item.meal_text || "Приём пищи")}</strong>
            <small>${formatNumber(item.kcal, 0)} ккал</small>
          </td>
          <td>
            <span class="macro-chip protein">Б ${formatNumber(item.protein_g)} г</span>
            <span class="macro-chip fat">Ж ${formatNumber(item.fat_g)} г</span>
            <span class="macro-chip carbs">У ${formatNumber(item.carbs_g)} г</span>
          </td>
          <td>${formatNumber(item.current_glucose_mmol)} ммоль/л</td>
          <td>${formatNumber(item.meal_bolus)} ед.</td>
          <td>${formatNumber(item.correction_bolus)} ед.</td>
          <td><strong>${formatNumber(item.total_bolus)} ед.</strong></td>
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
          <th>Болюс еды</th>
          <th>БЖУ</th>
          <th>Глюкоза</th>
          <th>Еда</th>
          <th>Коррекция</th>
          <th>Итог</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function renderResult(payload) {
  const nutrition = payload.nutrition;
  const result = payload.result;

  elements.proteinMetric.textContent = `${nutrition.total_protein} г`;
  elements.fatMetric.textContent = `${nutrition.total_fat} г`;
  elements.carbsMetric.textContent = `${nutrition.total_carbs} г`;
  elements.bolusMetric.textContent = `${result.total_bolus} ед.`;
  elements.kcalMetric.textContent = `${nutrition.total_kcal} ккал`;
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
    renderMealLedger(elements.accountHistoryTable, payload.items);
    renderMealLedger(elements.historyTable, payload.items);
  } catch {
    elements.accountHistoryTable.className = "meal-ledger empty";
    elements.accountHistoryTable.textContent = "Журнал недоступен.";
    elements.historyTable.className = "meal-ledger empty";
    elements.historyTable.textContent = "История недоступна.";
  }
}

elements.form.addEventListener("submit", calculate);
elements.useNightscout.addEventListener("change", updateGlucoseMode);

elements.foodPhoto.addEventListener("change", () => {
  const file = elements.foodPhoto.files?.[0];
  if (!file) {
    elements.photoPreview.classList.add("hidden");
    elements.photoPreview.innerHTML = "";
    return;
  }

  const url = URL.createObjectURL(file);
  elements.photoPreview.classList.remove("hidden");
  elements.photoPreview.innerHTML = `<img src="${url}" alt="Фото еды" />`;
});

elements.recognizePhoto.addEventListener("click", async () => {
  const file = elements.foodPhoto.files?.[0];
  if (!file) {
    showToast("Сначала выберите фото еды.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  elements.photoResult.classList.remove("hidden");
  elements.photoResult.textContent = "Gemini анализирует фото...";

  try {
    const result = await uploadRequest("/api/recognize-food-photo", formData);
    elements.mealText.value = result.meal_text;
    const rows = result.items
      .map((item) => `${item.name} — ${item.weight_g} г (${item.confidence})`)
      .join("; ");
    elements.photoResult.textContent = `${rows}. ${result.notes || ""}`.trim();
    showToast("Еда распознана и перенесена в форму.");
  } catch (error) {
    elements.photoResult.textContent = "Распознавание не выполнено.";
    showToast(error.message);
  }
});

elements.saveProfile.addEventListener("click", () => {
  const currentProfile = getProfile();
  saveProfile({
    ...currentProfile,
    paidAccess: elements.paidAccess.value === "true",
    nightscoutUrl: elements.nightscoutUrl.value.trim(),
    nightscoutKey: elements.nightscoutKey.value.trim(),
    insulinToCarbRatio: numberValue(elements.accountRatio),
    targetGlucoseMmol: numberValue(elements.accountTarget),
    correctionFactorMmol: numberValue(elements.accountCorrectionFactor),
  });
  loadProfile();
  showToast("Профиль сохранён в браузере.");
});

elements.applyProfile.addEventListener("click", () => {
  elements.ratio.value = elements.accountRatio.value || elements.ratio.value;
  elements.target.value = elements.accountTarget.value || elements.target.value;
  elements.correctionFactor.value =
    elements.accountCorrectionFactor.value || elements.correctionFactor.value;
  showToast("Коэффициенты подставлены в форму.");
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
    saveProfile({
      ...profile,
      lastGlucoseMmol: result.glucose_mmol,
      lastGlucoseAt: new Date().toISOString(),
      lastGlucoseDirection: result.direction,
    });
    updateProfileStatus();
    showToast(`Nightscout работает: ${result.glucose_mmol} ммоль/л.`);
  } catch (error) {
    showToast(error.message);
  }
});

loadProfile();
loadHistory();
