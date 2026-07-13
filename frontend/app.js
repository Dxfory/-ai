const state = {
  reference: null,
  draft: null,
  fenran: null,
  session: null,
  currentStep: null,
};

const $ = (id) => document.getElementById(id);

function setStatus(message) {
  $("status").textContent = message;
}

function setImage(id, url) {
  const img = $(id);
  img.src = `${url}?t=${Date.now()}`;
}

function revealDraftActions() {
  $("downloadDraft").href = state.draft.file_url;
  $("downloadDraft").hidden = false;
  $("createSessionButton").hidden = false;
  $("fenranControls").hidden = false;
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
    setStatus("分染教学图已生成。它使用原画和白描作为输入，并保留白描线稿不变。");
  } catch (error) {
    setStatus(`分染失败：${error.message}`);
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
