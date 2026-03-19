# P0-08: Next.js 项目骨架 + shadcn/ui

## 依赖
- 无

## 目的
搭建 Maelstrom V0 前端项目基础结构，配置 Next.js App Router + shadcn/ui + Tailwind CSS，建立页面布局和导航框架。

## 执行方法
1. 使用 `pnpm create next-app` 初始化项目（TypeScript, App Router, Tailwind CSS, ESLint）
2. 运行 `npx shadcn@latest init` 配置 shadcn/ui
3. 安装基础 shadcn 组件：Button, Input, Card, Dialog, Form, Select, Slider, Tabs, Badge, Popover, ScrollArea, Separator
4. 创建页面结构：
   ```
   app/
   ├── layout.tsx          # 全局布局：Sidebar + 主内容区
   ├── page.tsx            # 首页 → 重定向到 /gap
   ├── gap/page.tsx        # Gap Engine 页（占位）
   ├── chat/page.tsx       # QA Chat 页（占位）
   ├── settings/page.tsx   # LLM 配置页（占位）
   └── sessions/page.tsx   # 会话列表（占位）
   ```
5. 创建布局组件：
   - `components/layout/Sidebar.tsx` — 侧边栏导航（Gap Engine / QA Chat / Settings / Sessions）
   - `components/layout/Header.tsx` — 顶栏（当前页标题 + 状态指示）
6. 配置 API 代理（next.config.js rewrites → FastAPI 后端）
7. 安装 `swr` 或 `@tanstack/react-query` 用于数据获取
8. 配置 ESLint + Prettier

## 验收条件
- `pnpm dev` 启动无报错
- 所有页面路由可访问（/gap, /chat, /settings, /sessions）
- Sidebar 导航切换页面正常
- shadcn/ui 组件可正常渲染（Button, Card 等）
- Tailwind CSS 样式生效
- API 代理配置正确（前端请求 /api/* 转发到后端）

## Unit Test
- `test_layout_renders`: 验证全局 layout 渲染 Sidebar 和主内容区
- `test_sidebar_navigation`: 验证 Sidebar 包含 4 个导航链接且 href 正确
- `test_page_routes`: 验证 /gap, /chat, /settings, /sessions 页面组件存在
- `test_shadcn_components`: 验证 Button, Card 等组件可正常 import 和渲染
- `test_redirect_home`: 验证首页重定向到 /gap
