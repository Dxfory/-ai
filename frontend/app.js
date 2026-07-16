const state = {
  reference: null,
  draft: null,
  registration: null,
  fenran: null,
  session: null,
  currentStep: null,
  registrationPoints: [],
};

const $ = (id) => document.getElementById(id);

function setStatus(message) {
  $("status").textContent = message;
}

function setImage(id, url) {
  const img = $(id);
  img.src = `${url}?t=${Date.now()}`;
}

function computeRenderedRect(img) {
  const box = img.getBoundingClientRect();
  const naturalWidth = img.naturalWidth || 1;
  const naturalHeight = img.naturalHeight || 1;
  const scale = Math.min(box.width / naturalWidth, box.height / naturalHeight);
  const width = naturalWidth * scale;
  const height = naturalHeight * scale;
  return {
    x: box.left + (box.width - width) / 2,
    y: box.top + (box.height - height) / 2,
    width,
    height,
    scaleX: width / naturalWidth,
    scaleY: height / naturalHeight,
    naturalWidth,
    naturalHeight,
  };
}

function screenToCanonicalPoint(event, img) {
  const rect = computeRenderedRect(img);
  return {
    x: Math.max(0, Math.min(rect.naturalWidth, (event.clientX - rect.x) / rect.scaleX)),
    y: Math.max(0, Math.min(rect.naturalHeight, (event.clientY - rect.y) / rect.scaleY)),
    renderedRect: rect,
  };
}

function updateRegistrationSvg() {
  const original = $("registrationOriginal");
  const svg = $("registrationSvg");
  if (!original.naturalWidth || !original.naturalHeight) return;
  svg.setAttribute("viewBox", `0 0 ${original.naturalWidth} ${original.naturalHeight}`);
  svg.innerHTML = state.registrationPoints.map((point, index) => (
    `<circle class="registration-point" data-index="${index}" cx="${point.x}" cy="${point.y}" r="5"></circle>`
  )).join("");
}

function renderRegistration(registration) {
  state.registration = registration;
  $("registrationArea").hidden = false;
  setImage("registrationOriginal", state.reference.file_url);
  setImage("registrationBaimiao", registration.registered_baimiao_image_uri);
  $("registrationBaimiao").style.opacity = String(Number($("registrationOpacity").value) / 100);
  $("registrationMeta").textContent = `配准状态：${registration.status}，坐标系：${registration.canonical_size.join(" x ")}，评分：${registration.registration_score}`;
}

function revealDraftActions() {
  $("downloadDraft").href = state.draft.file_url;
  $("downloadDraft").hidden = false;
  $("createSessionButton").hidden = false;
  $("fenranControls").hidden = false;
}

function renderFenranStages(fenran) {
  const container = $("fenranStages");
  const stages = fenran.stages || [];
  container.hidden = stages.length === 0;
  container.innerHTML = "";
  stages.forEach((stage) => {
    const article = document.createElement("article");
    article.className = "fenran-stage";
    const heading = document.createElement("div");
    heading.className = "fenran-stage-heading";
    const title = document.createElement("h3");
    title.textContent = stage.title;
    const meta = document.createElement("p");
    const validationScore = stage.validation && typeof stage.validation.score === "number"
      ? ` ${Math.round(stage.validation.score * 100)}分`
      : "";
    meta.textContent = `${stage.technique} · ${stage.pigments.join("、") || "按原画底色"} · 校验：${stage.status}${validationScore}`;
    heading.append(title, meta);
    const image = document.createElement("img");
    image.alt = stage.title;
    image.src = `${stage.file_url}?t=${Date.now()}`;
    const download = document.createElement("a");
    download.className = "download";
    download.href = stage.file_url;
    download.download = "";
    download.textContent = `下载${stage.title}`;
    article.append(heading, image, download);
    container.append(article);
  });
}

function renderStep() {
  if (!state.session) return;
  const active = state.session.steps.find((step) => step.status === "active")
    || state.session.steps.find((step) => step.status === "review")
    || state.session.steps.find((step) => step.status === "needs_revision")
    || state.session.steps[state.session.steps.length - 1];
  state.currentStep = active;
  $("practiceArea").hidden = false;
  $("stepMeta").textContent = `第 ${active.step_num} 步 / 共 ${state.session.steps.length} 步`;
  $("stepTitle").textContent = active.title;
  $("stepInstruction").textContent = active.instruction;
  $("checklist").innerHTML = active.checklist.map((item) => `<li>${item}</li>`).join("");
  $("mistakes").innerHTML = active.common_mistakes.map((item) => `<li>${item}</li>`).join("");
  if (active.submission_image_url) setImage("submissionPreview", active.submission_image_url);
  if (active.overlay_image_url) setImage("overlayPreview", active.overlay_image_url);
}

async function createRegistrationCandidate() {
  if (!state.draft) return null;
  setStatus("正在生成配准审核图...");
  state.registration = await jsonFetch(`/api/v1/registrations/line-drafts/${state.draft.id}/auto`, {
    method: "POST",
  });
  renderRegistration(state.registration);
  setStatus("配准审核图已生成。请检查原画与白描是否对齐，确认后保存配准版本。");
  return state.registration;
}

async function approveRegistrationCandidate() {
  if (!state.draft || !state.registration) return null;
  setStatus("正在保存配准版本...");
  state.registration = await jsonFetch(`/api/v1/registrations/line-drafts/${state.draft.id}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ registration_id: state.registration.registration_id }),
  });
  renderRegistration(state.registration);
  setStatus("配准版本已保存。现在可以开始分染。");
  return state.registration;
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    let payload = null;
    try {
      payload = JSON.parse(text);
    } catch (_) {
      payload = null;
    }
    const error = new Error(text || response.statusText);
    error.payload = payload;
    throw error;
  }
  return response.json();
}

$("lineStrength").addEventListener("input", (event) => {
  $("lineStrengthValue").textContent = event.target.value;
});

$("detailLevel").addEventListener("input", (event) => {
  $("detailLevelValue").textContent = event.target.value;
});

$("uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("referenceFile").files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("notes", $("notes").value);
  setStatus("正在上传原画...");
  try {
    state.reference = await jsonFetch("/api/v1/uploads/reference", {
      method: "POST",
      body: formData,
    });
    setImage("referencePreview", state.reference.file_url);
    $("draftForm").hidden = false;
    $("lineDraftUploadForm").hidden = false;
    setStatus("原画已上传。你可以生成白描，也可以上传已有白描后进入分染。");
  } catch (error) {
    setStatus(`上传失败：${error.message}`);
  }
});

$("draftForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.reference) return;
  const provider = $("provider").value;
  const providerLabels = {
    source_locked_baimiao: "精准提线白描",
    local_edge_preview: "本地边缘预览",
    ai_baimiao: "AI 白描实验",
  };
  setStatus(`正在生成${providerLabels[provider] || "白描"}...`);
  try {
    state.draft = await jsonFetch("/api/v1/line-drafts/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reference_upload_id: state.reference.id,
        line_strength: Number($("lineStrength").value),
        detail_level: Number($("detailLevel").value),
        preserve_texture: $("preserveTexture").checked,
        provider,
      }),
    });
    setImage("draftPreview", state.draft.file_url);
    revealDraftActions();
    const statusMessages = {
      source_locked_baimiao: "精准提线白描已生成。它会作为分染的线稿输入，但分染不会修改它。",
      local_edge_preview: "本地边缘预览已生成。它可用于快速测试分染入口。",
      ai_baimiao: "AI 白描实验已生成。进入分染前请检查构图是否偏移。",
    };
    setStatus(statusMessages[provider] || "白描已生成。");
  } catch (error) {
    setStatus(`生成失败：${error.message}`);
  }
});

$("lineDraftUploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.reference) return;
  const file = $("lineDraftFile").files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("reference_upload_id", state.reference.id);
  formData.append("file", file);
  setStatus("正在上传已有白描...");
  try {
    state.draft = await jsonFetch("/api/v1/line-drafts/upload", {
      method: "POST",
      body: formData,
    });
    setImage("draftPreview", state.draft.file_url);
    revealDraftActions();
    setStatus("已有白描已上传。现在可以开始分染教学渲染。");
  } catch (error) {
    setStatus(`上传白描失败：${error.message}`);
  }
});

$("openRegistrationButton").addEventListener("click", async () => {
  if (!state.reference || !state.draft) return;
  try {
    await createRegistrationCandidate();
  } catch (error) {
    setStatus(`配准生成失败：${error.message}`);
  }
});

$("autoRegistrationButton").addEventListener("click", async () => {
  try {
    await createRegistrationCandidate();
  } catch (error) {
    setStatus(`配准生成失败：${error.message}`);
  }
});

$("approveRegistrationButton").addEventListener("click", async () => {
  try {
    await approveRegistrationCandidate();
  } catch (error) {
    setStatus(`保存配准失败：${error.message}`);
  }
});

$("registrationOpacity").addEventListener("input", (event) => {
  $("registrationBaimiao").style.opacity = String(Number(event.target.value) / 100);
});

$("registrationSvg").addEventListener("click", (event) => {
  const point = screenToCanonicalPoint(event, $("registrationOriginal"));
  state.registrationPoints.push({ x: Math.round(point.x), y: Math.round(point.y) });
  updateRegistrationSvg();
});

$("registrationOriginal").addEventListener("load", updateRegistrationSvg);
window.registrationGeometry = { computeRenderedRect, screenToCanonicalPoint };

$("startFenranButton").addEventListener("click", async () => {
  if (!state.reference || !state.draft) return;
  $("startFenranButton").disabled = true;
  setStatus("正在调用分染大模型生成教学图...");
  try {
    state.fenran = await jsonFetch("/api/v1/fenran/training-renders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reference_upload_id: state.reference.id,
        line_draft_id: state.draft.id,
        teaching_goal: $("fenranGoal").value,
        include_base_color: $("includeBaseColor").checked,
        force_regenerate: $("forceFenranRegenerate").checked,
      }),
    });
    renderFenranStages(state.fenran);
    setStatus(state.fenran.cache_hit ? "已复用相同输入的分染阶段。" : "分染阶段已生成并通过完整性校验。");
  } catch (error) {
    const detail = error.payload && error.payload.detail;
    if (detail && detail.status === "review_required") {
      renderFenranStages({ stages: detail.completed_stages || [] });
      setStatus(`分染需要审核：${detail.failed_stage}，${(detail.reasons || []).join("、")}`);
    } else if (error.message.includes("registration_review")) {
      setStatus("分染前需要先完成白描配准审核。");
      try {
        await createRegistrationCandidate();
      } catch (registrationError) {
        setStatus(`配准生成失败：${registrationError.message}`);
      }
    } else {
      setStatus(`分染失败：${error.message}`);
    }
  } finally {
    $("startFenranButton").disabled = false;
  }
});

$("createSessionButton").addEventListener("click", async () => {
  if (!state.reference || !state.draft) return;
  setStatus("正在创建分步练习...");
  try {
    state.session = await jsonFetch("/api/v1/practice-sessions/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reference_upload_id: state.reference.id,
        line_draft_id: state.draft.id,
        title: "工笔花鸟白描与分染练习",
      }),
    });
    renderStep();
    setStatus("分步练习已创建。先完成当前步骤，再上传作业图。");
  } catch (error) {
    setStatus(`创建失败：${error.message}`);
  }
});

$("submissionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.currentStep) return;
  const file = $("submissionFile").files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  setStatus("正在上传作业并生成叠图...");
  try {
    const updatedStep = await jsonFetch(`/api/v1/practice-steps/${state.currentStep.id}/submission`, {
      method: "POST",
      body: formData,
    });
    state.session.steps = state.session.steps.map((step) => (
      step.id === updatedStep.id ? updatedStep : step
    ));
    renderStep();
    setStatus("叠图已生成。你可以继续下一步，或者再修改一下。");
  } catch (error) {
    setStatus(`上传失败：${error.message}`);
  }
});

$("continueButton").addEventListener("click", async () => {
  if (!state.currentStep) return;
  setStatus("正在进入下一步...");
  try {
    state.session = await jsonFetch(`/api/v1/practice-steps/${state.currentStep.id}/continue`, {
      method: "POST",
    });
    renderStep();
    setStatus(state.session.status === "completed" ? "练习完成。" : "已进入下一步。");
  } catch (error) {
    setStatus(`操作失败：${error.message}`);
  }
});

$("retryButton").addEventListener("click", async () => {
  if (!state.currentStep) return;
  setStatus("已标记为需要再修改。");
  try {
    const updatedStep = await jsonFetch(`/api/v1/practice-steps/${state.currentStep.id}/retry`, {
      method: "POST",
    });
    state.session.steps = state.session.steps.map((step) => (
      step.id === updatedStep.id ? updatedStep : step
    ));
    renderStep();
  } catch (error) {
    setStatus(`操作失败：${error.message}`);
  }
});
