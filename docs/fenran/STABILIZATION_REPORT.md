# 分染教学模块稳定化报告

日期：2026-07-16

## 1. 修改与新增文件

修改：

- `backend/services/fenran.py`
- `backend/routes/fenran.py`
- `backend/schemas.py`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `.env.example`
- `tests/test_fenran_training.py`
- `tests/test_fenran_registration_gate.py`

新增：

- `backend/services/fenran_canvas.py`
- `backend/services/fenran_generation.py`
- `backend/services/fenran_plan.py`
- `backend/services/fenran_masks.py`
- `backend/services/fenran_validation.py`
- `backend/services/fenran_cache.py`
- `tests/test_fenran_stabilization.py`
- `tests/test_fenran_plan.py`
- `tests/test_fenran_validation.py`
- `tests/test_fenran_cache.py`
- `tests/test_fenran_pipeline.py`
- `tests/test_fenran_api_contract.py`
- `tests/test_fenran_frontend_contract.py`

白描生成、白描后处理、教材处理脚本、配准编辑器核心坐标逻辑和原图文件没有改动。

## 2. 旧流程与新流程

旧流程是一次 image 调用，要求模型同时生成颜色、步骤、数量和页面布局，成功条件只有“返回图片”。新流程先加载审批后的 registered_baimiao，建立动态 canonical canvas，再按可选底色、第一遍分染、加深分染、正叶整体罩染汁绿顺序逐阶段调用。每阶段保存完整图、恢复图、确定性合成图和校验结果。

## 3. Canonical canvas

canonical size 等于审批后的 registered_baimiao 自然像素尺寸，且要求原画相同尺寸。模型可以使用 `1024x1024`、`1024x1536` 或 `1536x1024` 临时画布，但所有输入使用同一 `content_box` 放置，模型输出再从同一 `content_box` 恢复。横图、竖图和方图不再共用固定输出尺寸。

## 4. 阶段与 Prompt

- `stage_00_base_color`：可选，默认关闭。
- `stage_01_first_fenran`：分染，花青加淡墨。
- `stage_02_deepen_fenran`：分染，只使用花青，第一输入是阶段一。
- `stage_03_sap_green_glaze`：罩染，正叶整体罩染汁绿，第一输入是阶段二。

模型每次只生成一张完整单幅阶段图，不负责教学排版、文字或多面板布局。旧的一次性 Prompt 和最终黑线机械覆盖路径已从主流程移除。

## 5. 完整性保护与校验

subject mask 由审批白描线和相对四角纸色的原画色差区域确定，有色宣纸不会自动覆盖整张 mask。模型结果只进入主体 mask，mask 外逐像素恢复上一阶段。校验包含画布尺寸、主体 bbox IoU、中心偏移、主体尺寸变化、主体覆盖、白描结构线保留率、背景变化比例、阶段变化比例和平均色差。

默认阈值：IoU `0.90`、中心偏移 `0.02`、尺寸变化 `0.04`、主体覆盖 `0.92`、结构线保留率 `0.35`、主体外变化 `0.01`、最低评分 `0.80`。任一阶段连续失败最多三次后返回 `review_required`，不会将残缺图标为 ready。

## 6. API、fallback 与缓存

多图上传支持任意数量输入。`FENRAN_ALLOW_SINGLE_REFERENCE_FALLBACK` 默认 `false`，关闭时多图错误直接抛出 provider error，不偷偷变更请求模式。缓存键包含原画 hash、registered_baimiao hash、registration id、底色开关、计划版本、Prompt 版本、模型、尺寸、API base、校验阈值、运行安全配置、教学目标和 renderer 版本。缓存命中还会检查最终图与阶段文件存在；`force_regenerate=true` 才重新调用。

路由错误语义：registration 未审批为 `409`，配置错误为 `400`，完整性校验耗尽为 `422`，provider 错误为 `502`。

## 7. 前端

前端新增底色开关、强制重新生成开关和阶段列表。每阶段显示标题、技法、颜料、完整阶段图、校验状态与评分，图片按自身比例使用 `width: 100%`、`height: auto`、`object-fit: contain`。配准编辑器仍使用原有共享 renderedRect 与 canonical 点击反算逻辑。

## 8. 测试结果

运行：

```powershell
python -m pytest -q
node --check frontend/app.js
```

新鲜最终验证：`python -m pytest -q` 为 `89 passed, 4 warnings`；`python -m compileall -q backend` 和 `node --check frontend/app.js` 均以 0 退出。

## 9. 仍存在的限制

传统图像指标不能证明每片花瓣、叶片、枝干或昆虫的语义拓扑完全正确；因此严重结构变化仍需配准审核。当前 mask 不是实例级分割，局部非刚性注册也仍由现有人工审批链路负责。上一轮配准基线仍是保守的人工审核候选，控制点非刚性变形与拓扑识别尚未完成，本任务按冻结边界未重写该部分。模型供应商需要支持 OpenAI-compatible 多图 image edit 接口。
