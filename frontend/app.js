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
    state.draft = null;
    state.fenran = null;
    setImage("referencePreview", state.reference.file_url);
    $("draftPreview").removeAttribute("src");
    $("fenranPreview").removeAttribute("src");
    $("downloadDraft").hidden = true;
    $("downloadFenran").hidden = true;
    $("fenranForm").hidden = true;
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
    setStatus("白描稿已生成，可以继续生成分染图。");
  } catch (error) {
    setStatus(`生成失败：${error.message}`);
  }
});

$("fenranForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.reference || !state.draft) return;
  setStatus("正在生成分染图...");
  try {
    state.fenran = await jsonFetch("/api/v1/color-steps/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reference_upload_id: state.reference.id,
        line_draft_id: state.draft.id,
        step_type: "fenran",
        provider: "ai_fenran",
      }),
    });
    setImage("fenranPreview", state.fenran.file_url);
    $("downloadFenran").href = state.fenran.file_url;
    $("downloadFenran").hidden = false;
    setStatus("分染图已生成，可以下载。");
  } catch (error) {
    setStatus(`生成失败：${error.message}`);
  }
});
