# 国画临摹 AI 教练 MVP PRD

## 1. MVP 定位

国画临摹 AI 教练的 MVP 不做 AI 生成国画，也不先做机构班级 SaaS。第一阶段只验证一个个人学习闭环：

范本接入 -> 权利状态确认 -> 画法/画种确认 -> 画材清单 -> 步骤课程 -> 作业提交 -> AI 初评 -> 内部质检 -> 错误样本沉淀。

## 2. 第一阶段必做范围

### 2.1 用户端

- 首页：展示花鸟、山水、人物三条轨道，但只开放花鸟和山水 MVP 入口。
- 作品接入页：支持上传图片、从版权素材库选择。
- 范本详情页：展示作品图、版权状态、画种、画法、材料清单。
- 课程页：展示步骤导航、每步目标、自检清单、常见错误。
- 练习页：上传单步作业，展示 AI 初评和修改建议。
- 学习档案页：展示常错点和最近练习记录的雏形。

### 2.2 内部端

- 版权素材管理：新增、筛选、查看资产权利状态。
- 质检台：查看 AI 初评，修正文案，标记错误类型，决定是否入训练/评测池。

## 3. 数据边界

任何进入公开课程库或训练池的范本必须具备以下字段：

- `source_name`
- `source_url`
- `license_type`
- `display_allowed`
- `train_allowed`
- `commercial_allowed`
- `derivative_allowed`
- `attribution_text`
- `risk_level`

没有明确权利状态的图片只能进入用户私有临时分析，不得进入公开展示、课程模板、训练集或商业材料。

## 4. 后端接口计划

### 4.1 已有接口

- `GET /health`
- `POST /api/v1/artworks/`
- `GET /api/v1/artworks/`
- `GET /api/v1/artworks/{artwork_id}`
- `POST /api/v1/courses/generate`
- `GET /api/v1/courses/{course_id}`
- `GET /api/v1/courses/{course_id}/materials`
- `POST /api/v1/submissions/`
- `GET /api/v1/submissions/{submission_id}`
- `POST /api/v1/submissions/{submission_id}/feedback`

### 4.2 第一阶段新增接口

- `POST /api/v1/assets/`：创建版权素材记录。
- `GET /api/v1/assets/`：按风险等级、展示权限、训练权限筛选素材。
- `GET /api/v1/assets/{asset_id}`：查看单个素材的权利状态。

### 4.3 后续接口

- `POST /api/v1/uploads/artwork`：上传范本图。
- `POST /api/v1/uploads/submission`：上传作业图。
- `POST /api/v1/artworks/{artwork_id}/identify-method`：识别或确认工笔/写意。
- `POST /api/v1/submissions/{submission_id}/grade`：生成 AI 初评。
- `POST /api/v1/qc/reviews`：内部质检记录。
- `POST /api/v1/error-cases`：沉淀错误样本。

## 5. MVP 课程模板

### 5.1 工笔花鸟

构图定位 -> 勾线 -> 分染 -> 罩染 -> 复勾调整。

核心反馈：结构偏移、线条粗细不匀、分染过渡生硬、罩染压线、复勾过重。

### 5.2 写意花鸟

构图定位 -> 调色 -> 画花叶鸟主体 -> 穿枝干 -> 调整画面。

核心反馈：不敢下笔、反复涂抹、颜色单一、枝干脱节、缺乏留白。

### 5.3 写意山水

构图定位 -> 勾勒轮廓 -> 淡墨皴擦逐次加重 -> 画树/房屋 -> 点苔点 -> 染色/调整。

核心反馈：水分过多、行笔太快、中锋不稳、飞白被回填、皴擦方向不顺山势。

## 6. 关键验收标准

- 版权素材入库字段完整，缺少权利状态的素材不能被标记为绿色池。
- 三类课程模板能稳定生成步骤、材料、自检清单和常见错误。
- 作业反馈第一版必须给出错误原因和下一步修改动作，而不只是评分。
- 内部质检能保留 AI 初评、专家修正和错误标签。
- 后端测试全部通过。

## 7. 当前第一步交付

本次第一步先落地版权素材后端地基：

- 新增 `assets` 数据表。
- 新增资产创建、筛选、详情 API。
- 同步 PostgreSQL schema。
- 补充后端测试。

这个顺序优先于前端和 AI，是因为版权状态会决定作品能否展示、训练、商用和进入课程库，属于项目 Day 1 硬约束。
