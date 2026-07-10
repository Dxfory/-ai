# 工笔花鸟白描临摹 MVP PRD

## 1. 新定位

本阶段不做完整国画平台，不做山水、人物、机构班级、公开素材库，也不以 AI 生成国画为卖点。

MVP 只做一个最小闭环：

用户上传一张工笔花鸟参考图 -> 系统生成白描线稿 -> 用户下载或保存白描稿。

## 2. 为什么收束到工笔花鸟

- 当前只聚焦白描线稿生成，先把“原画转可临摹线稿”做稳定。
- 白描线稿是最明确的 AI 能力目标，可以持续训练和评估。
- 山水皴法问题更复杂，步骤不如花鸟直观，先后置。
- 用户自带图片，系统默认只做个人临摹分析，可以先不建立公开素材库。
- 更适合熟人小规模内测，能快速收集过程图、成品图和真实反馈。

## 3. 用户流程

### 3.1 上传参考图

用户上传一张图片。第一版限制为：

- 单花、单鸟、单枝叶、花鸟局部优先。
- 图片清晰，主体占画面较大。
- 只做个人学习分析，不公开展示，不进入训练集，除非用户单独授权。

### 3.2 生成白描线稿

系统从原图提取可临摹的白描稿。

第一版不追求完美模型，先用图像处理和可调参数实现：

- 灰度化
- 对比度增强
- 边缘提取
- 杂线过滤
- 线条加深
- 生成可下载 PNG

用户可调：

- 线条强度
- 细节保留程度
- 是否保留叶脉/花瓣纹理/羽毛纹理

### 3.3 白描下载

系统展示：

- 原画预览
- 白描稿预览
- 白描稿下载入口

第一版反馈以“拿到一张可用线稿”为主，不再展示后续教学步骤。

## 4. MVP 输出

当前只输出一张白描稿 PNG。

## 5. 后端接口计划

### 已有接口

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
- `POST /api/v1/assets/`
- `GET /api/v1/assets/`
- `GET /api/v1/assets/{asset_id}`

### 下一批接口

- `POST /api/v1/uploads/reference`：上传用户参考图。
- `POST /api/v1/line-drafts/generate`：生成白描线稿。
- `GET /api/v1/line-drafts/{draft_id}`：查看白描结果。
- `POST /api/v1/practice-sessions/`：创建一次临摹练习。
- `GET /api/v1/practice-sessions/{session_id}`：查看练习步骤。
- `POST /api/v1/practice-steps/{step_id}/submission`：上传单步作业。
- `POST /api/v1/practice-steps/{step_id}/overlay`：生成叠图对照。

## 6. 数据表计划

### 已有表

- `artworks`
- `courses`
- `steps`
- `submissions`
- `error_profiles`
- `assets`

### 下一批表

- `reference_uploads`：用户上传的参考图。
- `line_drafts`：白描线稿版本和参数。
- `practice_sessions`：一次完整临摹。
- `practice_step_runs`：每一步的状态、上传图、叠图结果。
- `feedback_notes`：轻量提示和用户反馈。

## 7. 版权与授权边界

第一版不建立公开素材库，不主动提供图片。

用户上传图片默认规则：

- 仅用于用户本次个人学习分析。
- 不公开展示。
- 不进入训练集。
- 不用于商业素材库。
- 若后续用于训练或案例展示，需要单独授权。

已有 `assets` 表保留，但从主流程降级为后置能力，用于未来团队自有示范图、授权图片和内测样本管理。

## 8. 内测计划

第一轮找 5-10 个熟人用户，优先非专业绘画背景。

每人完成一张简单工笔花鸟局部：

- 一朵花
- 一片叶组
- 一只小鸟
- 一段枝叶

收集数据：

- 原图
- 生成白描稿
- 每一步上传图
- 用户是否看得懂步骤
- 用户是否能独立继续
- 用户认为最难的一步
- 最终作品
- 用户口头/文字反馈

## 9. MVP 验收标准

- 用户能上传参考图并得到一张可下载白描稿。
- 系统能生成 6 个工笔花鸟步骤页。
- 用户能在每一步上传照片。
- 系统能展示参考图和用户作业的透明叠图。
- 用户能选择继续或重画。
- 至少 5 个内测用户能完成一张作品。
- 团队能收集每步过程图和反馈，用于后续线稿/纠错优化。

## 10. 后置能力

- 山水皴法临摹。
- 人物白描。
- 公开版权素材库。
- 机构/班级/老师后台。
- 复杂 AI 评分。
- 真实照片转工笔白描。
- AI 生成图转工笔白描。

这些能力不进入当前 MVP。
