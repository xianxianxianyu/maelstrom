# P0-09: LLM 配置前端页

## 依赖
- P0-08（Next.js 项目骨架）

## 目的
实现 LLM 配置前端页面，让用户可以选择 provider、模型、填写 API key 等参数，保存后即时生效。

## 执行方法
1. 在 `components/settings/LLMConfigForm.tsx` 中实现配置表单：
   - provider: Select 组件（openai / anthropic / local）
   - model_name: Select 组件（根据 provider 动态显示可用模型列表）
   - api_key: Password Input（local provider 时隐藏）
   - base_url: Text Input（仅 local provider 时显示）
   - temperature: Slider（0-2，步长 0.1，默认 0.7）
   - max_tokens: Number Input（默认 4096）
   - embedding_model: Select（text-embedding-3-small 等）
2. 在 `app/settings/page.tsx` 中集成 LLMConfigForm
3. 数据流：
   - 页面加载时 `GET /api/config/llm` 获取当前配置填充表单
   - 用户修改后点击"保存" → `PUT /api/config/llm`
   - 成功后显示 toast 提示"配置已生效"
   - 失败时显示错误信息
4. 使用 shadcn/ui Form 组件 + react-hook-form 做表单校验
5. provider 切换时动态更新 model_name 选项列表

## 验收条件
- 页面加载时正确显示当前 LLM 配置
- provider 切换时 model_name 选项动态更新
- local provider 时 api_key 隐藏，base_url 显示
- 保存成功显示确认提示
- 表单校验：temperature 范围、必填字段
- API 调用失败时显示错误信息

## Unit Test
- `test_form_renders`: 验证表单包含所有配置字段
- `test_provider_switch`: 切换 provider 后 model_name 选项更新
- `test_local_provider_fields`: local provider 时 api_key 隐藏、base_url 显示
- `test_save_config`: mock API，点击保存后验证 PUT 请求发送正确数据
- `test_load_config`: mock API，验证页面加载时 GET 请求并填充表单
- `test_validation_error`: temperature 输入 5 时显示校验错误
