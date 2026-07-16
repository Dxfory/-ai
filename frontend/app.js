const state = {
  reference: null,
  draft: null,
  registration: null,
  fenran: null,
  shiseUpstream: null,
  shise: null,
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

function revealShiseControls(upstream) {
  state.shiseUpstream = upstream;
  $("shiseControls").hidden = false;
  $("shiseInputMeta").textContent = "当前输入：" + (upstream.original_filename || "分染阶段输出");
}

function updateFixingRequirement() {
  const silk = $("shiseMedium").value === "silk";
  $("shiseFixing").required = silk;
  $("shiseFixingLabel").classList.toggle("required-fixing", silk);
  $("shiseFixingNote").textContent = silk
    ? "绢本必须确认胶矾水固定并待干，否则系统不会开始石色罩染。"
    : "纸本胶矾水固定为可选步骤。";
}

function renderShisePlan(result) {
  const area = $("shisePlan");
  area.hidden = false;
  area.innerHTML = "";
  const heading = document.createElement("h2");
  heading.textContent = "石色罩染计划";
  area.append(heading);
  const readiness = document.createElement("p");
  readiness.className = result.readiness.ready ? "plan-ready" : "plan-blocked";
  readiness.textContent = result.readiness.ready
    ? "前置条件通过"
    : "尚不能开始：" + result.readiness.reasons.join("；");
  area.append(readiness);
  const list = document.createElement("div");
  list.className = "plan-list";
  result.plan_summary.forEach((item) => {
    const row = document.createElement("article");
    const title = document.createElement("strong");
    title.textContent = item.object_label + " · " + item.pigment;
    const detail = document.createElement("p");
    detail.textContent = item.action + "。" + item.reason;
    row.append(title, detail);
    list.append(row);
  });
  area.append(list);
  if (result.validation_result?.warnings?.length) {
    const warnings = document.createElement("p");
    warnings.className = "plan-warning";
    warnings.textContent = result.validation_result.warnings.join("；");
    area.append(warnings);
  }
}

function formatShiseError(message) {
  const normalized = message.toLowerCase();
  if (normalized.includes("413") || normalized.includes("payload too large")) {
    return "模型接口拒绝了过大的图片；系统已压缩并尝试单图降级，但服务仍未接受请求。";
  }
  if (normalized.includes("524") || normalized.includes("timeout") || normalized.includes("timed out")) {
    return "模型接口处理超时；请稍后重试，系统会保留本次错误记录。";
  }
  if (normalized.includes("400") || normalized.includes("415") || normalized.includes("422")) {
    return "模型接口不接受当前图片编辑格式；详细响应已保存到任务错误文件。";
  }
  return message;
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
    throw new Error(text || response.statusText);
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
      }),
    });
    setImage("fenranPreview", state.fenran.file_url);
    $("downloadFenran").href = state.fenran.file_url;
    $("downloadFenran").hidden = false;
    revealShiseControls({ file_url: state.fenran.file_url, original_filename: "分染与水色罩染完成图" });
    setStatus("分染教学图已生成。现在可以继续进行独立的石色罩染。");
  } catch (error) {
    if (error.message.includes("registration_review")) {
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

$("shiseUpstreamForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("shiseUpstreamFile").files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  setStatus("正在上传分染与水色罩染完成图...");
  try {
    const upstream = await jsonFetch("/api/v1/shise-zhaoran/upstream", {
      method: "POST",
      body: formData,
    });
    revealShiseControls(upstream);
    setStatus("上一阶段完成图已上传。请选择媒介并确认石色罩染规则。");
  } catch (error) {
    setStatus("石色罩染输入上传失败：" + error.message);
  }
});

$("shiseMedium").addEventListener("change", updateFixingRequirement);
updateFixingRequirement();

$("startShiseButton").addEventListener("click", async () => {
  if (!state.shiseUpstream) return;
  const button = $("startShiseButton");
  button.disabled = true;
  setStatus("正在分析对象并生成石色罩染...");
  const hints = $("shiseHints").value
    .split(/[,，、]/)
    .map((value) => value.trim())
    .filter(Boolean);
  try {
    state.shise = await jsonFetch("/api/v1/shise-zhaoran/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        upstream_image: state.shiseUpstream.file_url,
        reference_image: state.reference?.file_url || null,
        medium: $("shiseMedium").value,
        apply_fixing: $("shiseFixing").checked,
        subject_hints: hints,
        textbook_notes: $("shiseTextbookNotes").value,
        teaching_goal: $("shiseGoal").value,
      }),
    });
    renderShisePlan(state.shise);
    if (state.shise.status === "not_ready") {
      setStatus("石色罩染未开始：" + state.shise.readiness.reasons.join("；"));
      return;
    }
    setImage("shisePreview", state.shise.final_image_url);
    $("downloadShise").href = state.shise.final_image_url;
    $("downloadShise").hidden = false;
    setStatus("石色罩染完成图已生成。请结合计划摘要检查正反叶、果实与枝干关系。");
  } catch (error) {
    setStatus("石色罩染失败：" + formatShiseError(error.message));
  } finally {
    button.disabled = false;
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
