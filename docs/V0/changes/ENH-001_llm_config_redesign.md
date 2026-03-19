# ENH-001: LLM 配置重构 — 自由字段 + 协议选择 + dotfile 持久化

## 依赖
- P0-03（现有 LLM Config API）
- P0-09（现有 LLM Config 前端）

## 目的
现有配置以 provider 三选一为核心，模型列表硬编码，灵活性不足。重构为"所有字段自由输入、仅协议需要选择"的模式，同时将配置持久化到用户目录 dotfile，解决每次重启都要重新输入的问题。

## 一、新配置模型

### 1.1 协议枚举（替代 ProviderEnum）

```python
class ProtocolEnum(str, Enum):
    openai_chat = "openai_chat"            # POST {base_url}/chat/completions
    openai_responses = "openai_responses"  # POST {base_url}/responses
    anthropic_messages = "anthropic_messages"  # POST {base_url}/messages
```

### 1.2 Profile 模型（替代 LLMConfig）

```python
class LLMProfile(BaseModel):
    name: str                          # 用户自定义名称，如 "My GPT-4o"
    protocol: ProtocolEnum             # 唯一需要选择的字段
    base_url: str                      # API 端点，如 https://api.openai.com/v1
    api_key: str | None = None         # 可为空（本地模型）
    model: str                         # 模型标识符，完全自由输入
    temperature: float = 0.7           # 0-2
    max_tokens: int = 4096             # 最大输出 token
```

### 1.3 完整配置模型

```python
class MaelstromConfig(BaseModel):
    profiles: dict[str, LLMProfile]    # key = profile slug
    active_profile: str = "default"    # 当前生效的 profile key
    embedding: EmbeddingConfig         # embedding 独立配置

class EmbeddingConfig(BaseModel):
    model: str = "text-embedding-3-small"
    api_key: str | None = None         # 为空时 fallback 到 active profile 的 api_key
    base_url: str | None = None
```

### 1.4 字段映射（旧 → 新）

| 旧字段 | 新字段 | 变化 |
|--------|--------|------|
| `provider` | `protocol` | 枚举值变更 |
| `model_name` | `model` | 字段名简化 |
| `base_url` | `base_url` | 从可选变为必填 |
| `api_key` | `api_key` | 不变 |
| `temperature` | `temperature` | 不变 |
| `max_tokens` | `max_tokens` | 不变 |
| `embedding_model` | `embedding.model` | 移入子对象 |
| `embedding_api_key` | `embedding.api_key` | 移入子对象 |
| — | `name` | 新增 |
| — | `profiles` / `active_profile` | 新增多 profile 支持 |

## 二、Dotfile 持久化

### 2.1 文件路径

三平台统一：`Path.home() / ".maelstrom" / "config.json"`

| 系统 | 实际路径 |
|------|---------|
| Windows | `C:\Users\{user}\.maelstrom\config.json` |
| macOS | `/Users/{user}/.maelstrom/config.json` |
| Linux | `/home/{user}/.maelstrom/config.json` |

### 2.2 config.json 示例

```json
{
  "profiles": {
    "default": {
      "name": "My GPT-4o",
      "protocol": "openai_chat",
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-xxx",
      "model": "gpt-4o",
      "temperature": 0.7,
      "max_tokens": 4096
    },
    "claude": {
      "name": "Anthropic Claude",
      "protocol": "anthropic_messages",
      "base_url": "https://api.anthropic.com/v1",
      "api_key": "sk-ant-xxx",
      "model": "claude-sonnet-4-20250514",
      "temperature": 0.7,
      "max_tokens": 4096
    }
  },
  "active_profile": "default",
  "embedding": {
    "model": "text-embedding-3-small",
    "api_key": null,
    "base_url": null
  }
}
```

### 2.3 安全措施

1. **文件权限**：创建时设 `0o600`（owner read/write only）；Windows 上通过 `icacls` 限制为当前用户
2. **项目 .gitignore**：追加 `.maelstrom/` 防止误提交
3. **GET 接口脱敏**：返回 api_key 时替换为 `sk-***{后4位}`，前端不回显完整 key
4. **写入时机**：仅用户在 Settings 页面点击保存时写入，不自动写

### 2.4 读写流程

```
后端启动:
  config_path = Path.home() / ".maelstrom" / "config.json"
  if config_path.exists():
      读取 JSON → 解析为 MaelstromConfig → 加载到内存
  else:
      内存保持空配置（无 profile）

用户通过 Settings 页面保存:
  → 更新内存中的 MaelstromConfig
  → 序列化写入 config.json
  → 设置文件权限 600
  → 返回脱敏后的配置

用户通过 Settings 页面输入新 api_key:
  → 前端发送完整 key
  → 后端存入内存 + 写入文件
  → 返回脱敏 key（前端显示 sk-***xxxx）
```

## 三、API 变更

### 3.1 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 获取完整配置（key 脱敏） |
| PUT | `/api/config` | 更新完整配置（含写文件） |
| GET | `/api/config/profiles` | 列出所有 profile（key 脱敏） |
| POST | `/api/config/profiles` | 创建新 profile |
| PUT | `/api/config/profiles/{slug}` | 更新指定 profile |
| DELETE | `/api/config/profiles/{slug}` | 删除 profile |
| PUT | `/api/config/active` | 切换 active_profile |

### 3.2 脱敏逻辑

```python
def mask_key(key: str | None) -> str | None:
    if not key or len(key) < 8:
        return key
    return key[:3] + "***" + key[-4:]
    # "sk-ant-api03-xxx...abc" → "sk-***-abc"
```

## 四、下游适配

### 4.1 graph nodes（5 个 `_call_llm` 函数）

现有逻辑按 `provider` 分支构造 URL 和 header。改为按 `protocol` 分支：

```python
def _build_request(profile: dict) -> tuple[str, dict, dict]:
    protocol = profile["protocol"]
    base = profile["base_url"].rstrip("/")
    key = profile.get("api_key", "")

    if protocol == "anthropic_messages":
        url = f"{base}/messages"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        body_fmt = "anthropic"
    elif protocol == "openai_responses":
        url = f"{base}/responses"
        headers = {"Authorization": f"Bearer {key}"}
        body_fmt = "openai_responses"
    else:  # openai_chat
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        body_fmt = "openai_chat"

    return url, headers, body_fmt
```

抽成公共函数放 `src/maelstrom/services/llm_client.py`，5 个节点统一调用，消除重复代码。

### 4.2 paperqa_service

paper-qa 内部使用 litellm，需要将 protocol + base_url + model 映射为 litellm 能识别的格式：

```python
if protocol == "openai_chat":
    llm_str = model                    # "gpt-4o"
elif protocol == "anthropic_messages":
    llm_str = f"anthropic/{model}"     # "anthropic/claude-sonnet-4-20250514"
elif protocol == "openai_responses":
    llm_str = model                    # litellm 走 openai 兼容
```

### 4.3 gap_service

`gap_service.py` 中 `llm_config.model_dump()` 改为读取 active profile 并 dump。

## 五、前端变更

### 5.1 LLMConfigForm 重写

- 移除 `PROVIDER_MODELS` 硬编码列表
- `protocol` 用 Select 三选一
- `name`、`base_url`、`api_key`、`model` 全部用 Input 自由输入
- `api_key` 字段：显示脱敏值，聚焦时清空让用户重新输入，失焦且未修改时恢复脱敏值
- 新增 profile 切换下拉 + 新建/删除按钮
- `temperature` 保持 Slider
- `max_tokens` 保持 Input number

### 5.2 前端 TypeScript 类型

```typescript
interface LLMProfile {
  name: string;
  protocol: "openai_chat" | "openai_responses" | "anthropic_messages";
  base_url: string;
  api_key: string | null;
  model: string;
  temperature: number;
  max_tokens: number;
}

interface MaelstromConfig {
  profiles: Record<string, LLMProfile>;
  active_profile: string;
  embedding: {
    model: string;
    api_key: string | null;
    base_url: string | null;
  };
}
```

## 六、涉及文件清单

| 文件 | 操作 |
|------|------|
| `src/maelstrom/schemas/common.py` | 删除 `ProviderEnum`，新增 `ProtocolEnum` |
| `src/maelstrom/schemas/llm_config.py` | 重写为 `LLMProfile` + `MaelstromConfig` + `EmbeddingConfig` |
| `src/maelstrom/services/llm_config_service.py` | 重写：dotfile 读写 + 内存缓存 + 脱敏 |
| `src/maelstrom/services/llm_client.py` | 新建：公共 `_build_request()` + `call_llm()` |
| `src/maelstrom/api/config.py` | 重写路由（profile CRUD + active 切换） |
| `src/maelstrom/services/paperqa_service.py` | 适配新 schema |
| `src/maelstrom/services/gap_service.py` | 适配新 schema |
| `src/maelstrom/graph/nodes/*.py`（5 个） | 删除各自的 `_call_llm`，改用 `llm_client` |
| `frontend/src/components/settings/LLMConfigForm.tsx` | 重写 |
| `.gitignore` | 追加 `.maelstrom/` |

## 验收条件

- Settings 页面可自由输入 name / base_url / api_key / model，protocol 三选一
- 保存后 `~/.maelstrom/config.json` 被创建，文件权限为 600
- 重启后端后配置自动恢复，无需重新输入
- GET 接口返回的 api_key 是脱敏的（`sk-***xxxx`）
- 可创建多个 profile 并切换
- Gap Engine 和 QA Chat 使用 active profile 正常工作
- 三种协议（openai_chat / openai_responses / anthropic_messages）均可正确发送请求
