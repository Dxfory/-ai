const state = {
  data: null,
  view: "pages",
  query: "",
  type: "all",
};

const $ = (id) => document.getElementById(id);

function text(value) {
  if (Array.isArray(value)) return value.join(" ");
  return String(value || "");
}

function includesQuery(item) {
  if (!state.query) return true;
  return JSON.stringify(item).toLowerCase().includes(state.query.toLowerCase());
}

function renderStats(data) {
  $("stats").innerHTML = [
    ["页数", data.page_count],
    ["图像条目", data.figure_index.length],
    ["墨线规则", data.existing_ink_line_rules.length],
    ["技法单元", data.technique_units.length],
  ].map(([label, value]) => `
    <div class="stat">
      <strong>${value}</strong>
      <span>${label}</span>
    </div>
  `).join("");
}

function renderTypeFilter(data) {
  const types = [...new Set(data.page_summaries.map((page) => page.page_type || "unknown"))].sort();
  $("typeFilter").innerHTML = `<option value="all">全部</option>${types.map((type) => (
    `<option value="${type}">${type}</option>`
  )).join("")}`;
}

function pageTitle(page) {
  const titles = page.titles?.length ? ` · ${page.titles.join(" / ")}` : "";
  return `第 ${page.page_index} 页${titles}`;
}

function renderPages() {
  const items = state.data.page_summaries
    .filter((page) => state.type === "all" || page.page_type === state.type)
    .filter(includesQuery);
  $("viewTitle").textContent = "页面学习结果";
  $("viewSummary").textContent = "检查每一页被识别成什么类型、涉及哪些图号，以及是否包含已有墨线规则。";
  renderList(items, (page) => `
    <article class="item">
      <div class="item-head">
        <div>
          <h3>${pageTitle(page)}</h3>
          <p class="meta">${page.figure_numbers.join("、") || "未识别图号"}</p>
        </div>
        <span class="badge">${page.page_type}</span>
      </div>
      <p class="summary">${page.short_text_summary || "暂无摘要"}</p>
      <div class="chips">
        ${(page.key_terms || []).slice(0, 12).map((term) => `<span class="chip">${term}</span>`).join("")}
      </div>
    </article>
  `);
}

function renderLines() {
  const items = state.data.existing_ink_line_rules.filter(includesQuery);
  $("viewTitle").textContent = "原作已有墨线规则";
  $("viewSummary").textContent = "这些规则只描述原画或书中白描稿已经存在的作者勾线，用于约束后续白描生成。";
  renderList(items, (rule) => `
    <article class="item">
      <div class="item-head">
        <div>
          <h3>第 ${rule.page_index} 页 · ${rule.object || "未命名对象"}</h3>
          <p class="meta">${rule.source_figure_no || "无图号"}</p>
        </div>
        <span class="badge gold">${rule.line_function || "unknown"}</span>
      </div>
      <div class="rule-grid">
        <strong>取线规则</strong>
        <span>${rule.line_extraction_rule || "暂无"}</span>
        <strong>不要发明</strong>
        <span>${(rule.do_not_invent || []).join("；") || "暂无"}</span>
      </div>
    </article>
  `);
}

function renderTechniques() {
  const items = state.data.technique_units.filter(includesQuery);
  $("viewTitle").textContent = "设色与技法单元";
  $("viewSummary").textContent = "从书页中抽取的对象、颜色、动作、条件和风险，用于后续生成一步一页教学。";
  renderList(items, (unit) => `
    <article class="item">
      <div class="item-head">
        <div>
          <h3>第 ${unit.page_index} 页 · ${(unit.objects || []).join("、") || "对象未定"}</h3>
          <p class="meta">${(unit.linked_figure_nos || []).join("、") || "无图号"}</p>
        </div>
        <span class="badge">${unit.step_order ? `Step ${unit.step_order}` : "技法"}</span>
      </div>
      <div class="rule-grid">
        <strong>颜色材料</strong>
        <span>${(unit.materials_or_colors || []).join("、") || "暂无"}</span>
        <strong>动作</strong>
        <span>${(unit.actions || []).join("；") || "暂无"}</span>
        <strong>条件</strong>
        <span>${(unit.conditions || []).join("；") || "暂无"}</span>
        <strong>风险</strong>
        <span>${(unit.warnings || []).join("；") || "暂无"}</span>
      </div>
    </article>
  `);
}

function renderConstraints() {
  const items = state.data.faithfulness_constraints
    .map((value, index) => ({ value, index: index + 1 }))
    .filter(includesQuery);
  $("viewTitle").textContent = "白描忠实度约束";
  $("viewSummary").textContent = "生成白描稿时必须遵守这些约束：不改构图、不改对象数量、不改原作者已有线的结构关系。";
  renderList(items, (item) => `
    <article class="item">
      <div class="item-head">
        <h3>约束 ${item.index}</h3>
        <span class="badge red">faithful</span>
      </div>
      <p class="summary">${item.value}</p>
    </article>
  `);
}

function renderList(items, template) {
  $("list").innerHTML = items.length
    ? items.map(template).join("")
    : `<div class="empty">没有匹配结果。</div>`;
}

function render() {
  const data = state.data;
  $("bookId").textContent = `${data.book_id} · ${data.core_learning_goal}`;
  if (state.view === "pages") renderPages();
  if (state.view === "lines") renderLines();
  if (state.view === "techniques") renderTechniques();
  if (state.view === "constraints") renderConstraints();
}

async function init() {
  const response = await fetch("/app/data/book_knowledge.json");
  state.data = await response.json();
  renderStats(state.data);
  renderTypeFilter(state.data);
  render();
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
    button.classList.add("active");
    state.view = button.dataset.view;
    render();
  });
});

$("searchInput").addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});

$("typeFilter").addEventListener("change", (event) => {
  state.type = event.target.value;
  render();
});

init().catch((error) => {
  $("list").innerHTML = `<div class="empty">加载失败：${error.message}</div>`;
});
