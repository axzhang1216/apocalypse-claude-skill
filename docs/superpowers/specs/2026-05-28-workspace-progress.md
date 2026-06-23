# Apocalypse Workspace 3D Graph — 进度总结

**Date:** 2026-05-28
**Status:** 核心功能已跑通，Code Review 进行中

---

## 完成的工作

### 1. Spec 文档
- `docs/superpowers/specs/2026-05-27-workspace-3d-graph-design.md` — 完整设计 spec
- 数据模型、API 端点、3D 可视化映射规则、SKILL 流程都已定义

### 2. Multica Issue
- **ZAR-36**（已完成 status:done）— Apocalypse Workspace 3D 宇宙可视化功能实现
  - 分配给 Claude设计师
  - 产出了 6 个文件改动（`workspace.html`、`workspace_init.py`、`server.py`、`SKILL.md`、`dashboard.html`、`install.sh`）
- **ZAR-43**（进行中 status:todo）— Code Review & 后续完善
  - 分配给 Claude代码检查
  - 包含初版 4 个 bug 的根因+临时修法、未验证功能清单

### 3. 数据已初始化
- `~/.claude/apocalypse/workspace.json` 已生成
- **34 个 projects，87 个 sessions** 全部分析完毕
- API `GET /api/workspace/status` 返回 `{"initialized": true, "project_count": 34, "session_count": 87}`

### 4. 3D 可视化已跑通（经过 4 轮 hotfix）
浏览器测试通过（http://localhost:7749/workspace.html）：
- ✅ 宇宙视图：34 个发光球体（绿/黄/灰按 last_active）
- ✅ 点击 project 球体进入 Solar System 视图（相机动画过渡）
- ✅ Solar System 视图：恒星（按 outcome 着色）+ 行星（key_tools）
- ✅ 点击恒星弹出右侧 Panel（user_goal、summary、outcome、key_tools、ts）
- ✅ "← Universe" 返回按钮

---

## 设计师初版的 4 个 bug + 临时修法

发现这些 bug 是因为浏览器打开 workspace.html 后黑屏。用 chrome-devtools MCP 调试出根因：

### Bug 1: importmap + 跨域 CDN 阻断
**症状**：`Failed to resolve module specifier "three"`，Chrome ORB 阻断 jsdelivr。
**修法**：把 `three.module.min.js` 和 `OrbitControls.js` 下载到 `~/.claude/skills/apocalypse/` 同目录，server.py 加 `/three.module.min.js` 和 `/OrbitControls.js` 静态路由，workspace.html 用 `await import('/three.module.min.js')` 动态加载。

### Bug 2: OrbitControls 内部依赖 importmap
**症状**：本地化后 OrbitControls.js 内部 `import { ... } from 'three'` 仍解析失败。
**修法**：丢弃外部 OrbitControls，在 `main()` 里内联了一个 ~30 行简版（拖拽旋转 + 滚轮缩放）。缺失 damping/pan/touch 支持。

### Bug 3: `renderer.domElement.addEventListener` 在顶层执行
**症状**：`Cannot read properties of undefined (reading 'domElement')`，脚本顶层访问 renderer 时它还是 undefined。
**修法**：把 `addEventListener('mousemove'/'click')` 两行从顶层移到 `main()` 里 `initRenderer()` 之后。

### Bug 4: `const clock = new THREE.Clock()` TDZ
**症状**：`Cannot access 'clock' before initialization`，THREE 此时未加载。
**修法**：改成 `let clock;` 顶层声明，`main()` 里赋值。

---

## 还有的小问题（次要）

1. **很多 session 的 summary 是 "Analysis failed"**
   - workspace_init.py 调 Claude Haiku API 解析返回 JSON 时失败的兜底
   - 没影响整体功能但显示不友好
   - 可加 retry 或更鲁棒的 JSON 解析

2. **Code Review 还在跑**
   - ZAR-43 还未完成，Claude代码检查 review 后可能有更多发现

3. **未充分测试的边界**
   - msg_count 小改动后是否正确写入（要重新 init 才能验证）
   - 增量更新模式 `--incremental` 没测试过

---

## 关键文件位置

```
源码（git tracked）：
  E:\BaiduSyncdisk\ClaudeCode_Workspace\apocalypse\skills_apocalypse\
    workspace.html              ← 3D 可视化前端
    workspace_init.py           ← 初始化 harness
    server.py                   ← + /api/workspace 路由
    SKILL.md                    ← + workspace 检查流程
    dashboard.html              ← + Workspace 入口链接
    install.sh                  ← + cp 新文件
    three.module.min.js         ← Three.js 本地副本
    OrbitControls.js            ← OrbitControls 本地副本（实际未用）

安装目录（运行时）：
  ~/.claude/skills/apocalypse/   ← install.sh 复制目标
  ~/.claude/apocalypse/
    workspace.json              ← 初始化数据
    server.pid
    server.log
    events.jsonl

文档：
  docs/superpowers/specs/2026-05-27-workspace-3d-graph-design.md
  docs/superpowers/specs/2026-05-28-workspace-progress.md  ← 本文件
```

---

## 下一步建议

1. **等 ZAR-43 review 完成**，根据 findings 决定是否做第二轮 hotfix
2. **修 "Analysis failed"**：让 workspace_init.py 对 API 返回的 JSON 解析更鲁棒
3. **测试增量更新**：`python workspace_init.py --incremental`
4. **install.sh 改进**：确认 `three.module.min.js` 是否需要 cp 到安装目录（目前手动 cp 过）
5. **跑 verify skill** 做端到端验证（启动 server → 访问 dashboard → 点 Workspace 链接 → 操作 3D 图）
