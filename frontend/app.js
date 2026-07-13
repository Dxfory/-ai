const state = {
  reference: null,
  draft: null,
  fenran: null,
};

const $ = (id) => document.getElementById(id);

function setStatus(message) {
  $("status").textContent = message;
}

function setImage(id, url) {
  const img = $(id);
  img.src = `${url}?t=${Date.now()}`;
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

$("uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("referenceFile").files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("notes", "user_original_artwork");
  setStatus("正在上传原画...");
  try {
    state.reference = await jsonFetch("/api/v1/uploads/reference", {
      method: "POST",
      body: formData,
    });
    setImage("referencePreview", state.reference.file_url);
    $("draftForm").hidden = false;
    setStatus("原画已上传，可以生成白描稿。");
  } catch (error) {
    setStatus(`上传失败：${error.message}`);
  }
});

$("draftForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.reference) return;
  setStatus("正在生成白描稿...");
  try {
    state.draft = await jsonFetch("/api/v1/line-drafts/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reference_upload_id: state.reference.id,
        line_strength: 3,
        detail_level: 3,
        preserve_texture: true,
        provider: "ai_baimiao",
      }),
    });
    setImage("draftPreview", state.draft.file_url);
    $("downloadDraft").href = state.draft.file_url;
    $("downloadDraft").hidden = false;
    $("fenranForm").hidden = false;
    setStatus("白描稿已生成。白描文件保持不变，现在可以生成独立分染稿。");
  } catch (error) {
    setStatus(`生成失败：${error.message}`);
  }
});

$("fenranForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.reference || !state.draft) return;
  setStatus("正在生成分染稿...");
  try {
    state.fenran = await jsonFetch("/api/v1/fenran/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reference_upload_id: state.reference.id,
        line_draft_id: state.draft.id,
        subject_hint: $("subjectHint").value,
        step_count: 5,
      }),
    });
    setImage("fenranPreview", state.fenran.preview_url);
    $("downloadFenran").href = state.fenran.preview_url;
    $("downloadFenran").hidden = false;
    renderColorReport(state.fenran.metadata.regions || []);
    renderFenranSteps(state.fenran.steps);
    if (state.fenran.metadata.status === "segmentation_failed") {
      setStatus(`未生成分染图：${state.fenran.metadata.reason}`);
    } else {
      setStatus("分染稿已生成：已先识别原画颜色，再在白描对象内部局部分染。");
    }
  } catch (error) {
    setStatus(`分染生成失败：${error.message}`);
  }
});

function renderColorReport(regions) {
  const container = $("colorReport");
  container.hidden = false;
  container.innerHTML = "";
  const title = document.createElement("h2");
  title.textContent = "原画色彩识别";
  container.append(title);
  const meta = state.fenran?.metadata || {};
  if (meta.quality) {
    const summary = document.createElement("div");
    summary.className = meta.status === "segmentation_failed" ? "quality quality-failed" : "quality";
    const counts = meta.quality.object_counts || {};
    summary.innerHTML = `
      <strong>${meta.status === "segmentation_failed" ? "识别未通过" : "识别通过"}</strong>
      <span>背景占比：${Math.round((meta.quality.background_ratio || 0) * 100)}%</span>
      <span>对象占比：${Math.round((meta.quality.object_area_ratio || 0) * 100)}%</span>
      <span>叶：${counts.leaf || 0}</span>
      <span>红花：${counts.red_flower || 0}</span>
      <span>白花：${counts.white_flower || 0}</span>
      <span>果：${counts.fruit || 0}</span>
      <span>枝：${counts.branch || 0}</span>
      <span>鸟：${counts.bird || 0}</span>
      <span>虫：${counts.insect || 0}</span>
    `;
    if (meta.reason) {
      const reason = document.createElement("p");
      reason.textContent = meta.reason;
      summary.append(reason);
    }
    container.append(summary);
  }
  regions.slice(0, 12).forEach((region) => {
    const item = document.createElement("article");
    item.className = "color-item";
    const source = document.createElement("span");
    source.className = "swatch";
    source.style.background = region.average_color;
    const target = document.createElement("span");
    target.className = "swatch";
    target.style.background = region.fenran_color;
    const text = document.createElement("p");
    text.textContent = `${region.region_id} ${region.object_type}：原画 ${region.average_color} -> ${region.pigment} ${region.fenran_color}`;
    item.append(source, target, text);
    container.append(item);
  });
}

function renderFenranSteps(steps) {
  const container = $("fenranSteps");
  container.hidden = false;
  container.innerHTML = "";
  steps.forEach((step) => {
    const card = document.createElement("article");
    card.className = "step-card";
    const title = document.createElement("h2");
    title.textContent = `${step.step_num}. ${step.title}`;
    const text = document.createElement("p");
    text.textContent = step.instruction;
    const image = document.createElement("img");
    image.src = `${step.image_url}?t=${Date.now()}`;
    image.alt = step.title;
    card.append(title, text, image);
    container.append(card);
  });
}
