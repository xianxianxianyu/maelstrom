# P0-03: LLM 配置 API（内存态）

## 依赖
- P0-01（Pydantic Schema — LLMConfig model）

## 目的
实现 LLM 配置的内存态存储与 REST API，允许用户在前端动态配置 LLM provider/model/key 等参数，配置变更即时生效，关闭服务自动清除。

## 执行方法
1. 在 `src/maelstrom/services/llm_config_service.py` 中实现：
   - 全局变量 `_llm_config: LLMConfig | None = None`
   - `get_config() -> LLMConfig` — 返回当前配置或默认配置
   - `update_config(config: LLMConfig) -> LLMConfig` — 更新并返回
2. 在 `src/maelstrom/api/config.py` 中实现路由：
   - `GET /api/config/llm` — 返回当前 LLM 配置
   - `PUT /api/config/llm` — 更新 LLM 配置
3. 注册路由到 FastAPI app（`main.py` 中 `include_router`）
4. 默认配置：provider="openai", model_name="gpt-4o", temperature=0.7, max_tokens=4096

## 验收条件
- `GET /api/config/llm` 未配置时返回默认值
- `PUT /api/config/llm` 更新后，`GET` 返回更新后的值
- 无效配置（如 temperature=5）返回 422 校验错误
- 服务重启后配置重置为默认值（内存态验证）

## Unit Test
- `test_get_default_config`: 启动后 GET 返回默认 LLMConfig
- `test_update_config`: PUT 有效配置后 GET 返回更新值
- `test_update_invalid_temperature`: PUT temperature=5 返回 422
- `test_update_partial_fields`: PUT 只修改部分字段，其余保持默认
- `test_config_isolation`: 验证配置为进程级全局状态（两次 GET 返回同一配置）
