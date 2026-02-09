"""图片处理工具 — 从 Markdown 中提取 base64 图片，替换为相对路径"""
import base64 as b64mod
import re

_B64_PATTERN = re.compile(
    r'!\[([^\]]*)\]\(data:image/(png|jpeg|jpg|gif|webp);base64,([A-Za-z0-9+/=\s]+)\)'
)


def extract_base64_images(markdown: str) -> tuple[str, dict[str, bytes]]:
    """
    从 markdown 中提取 base64 图片，替换为 ./images/fig_N.ext 相对路径。

    Returns:
        (new_markdown, images_dict) — images_dict: {filename: bytes}
    """
    images: dict[str, bytes] = {}
    counter = [0]

    def _replace(m):
        counter[0] += 1
        alt = m.group(1)
        ext = m.group(2)
        if ext == "jpeg":
            ext = "jpg"
        data_str = m.group(3).replace("\n", "").replace(" ", "")
        try:
            img_bytes = b64mod.b64decode(data_str)
        except Exception:
            return m.group(0)  # 解码失败，保留原样
        name = f"fig_{counter[0]}.{ext}"
        images[name] = img_bytes
        return f"![{alt}](./images/{name})"

    new_md = _B64_PATTERN.sub(_replace, markdown)
    return new_md, images
