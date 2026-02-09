import re


class PostProcessor:
    """清洗 LLM 翻译输出的格式问题"""

    def process(self, text: str) -> str:
        text = self._strip_code_fences(text)
        text = self._convert_html_to_markdown(text)
        text = self._normalize_headings(text)
        text = self._clean_whitespace(text)
        return text

    def _strip_code_fences(self, text: str) -> str:
        """移除 ```markdown ... ``` 包裹"""
        # 匹配开头的 ```markdown 或 ```
        text = re.sub(
            r'^\s*```(?:markdown|md)?\s*\n',
            '',
            text,
            count=1,
        )
        # 匹配结尾的 ```
        text = re.sub(
            r'\n\s*```\s*$',
            '',
            text,
            count=1,
        )
        return text

    def _convert_html_to_markdown(self, text: str) -> str:
        """将常见 HTML 标签转为 Markdown"""
        # <br> / <br/> → 换行
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        # <p>...</p> → 段落（前后加空行）
        text = re.sub(
            r'<p>(.*?)</p>',
            r'\n\n\1\n\n',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # <b>/<strong> → **
        text = re.sub(
            r'<(?:b|strong)>(.*?)</(?:b|strong)>',
            r'**\1**',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # <i>/<em> → *
        text = re.sub(
            r'<(?:i|em)>(.*?)</(?:i|em)>',
            r'*\1*',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # <h1>~<h6> → # 标题
        for level in range(1, 7):
            text = re.sub(
                rf'<h{level}>(.*?)</h{level}>',
                rf'\n\n{"#" * level} \1\n\n',
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
        # <li> → 列表项
        text = re.sub(
            r'<li>(.*?)</li>',
            r'- \1',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # 移除 <ul>/<ol> 标签
        text = re.sub(r'</?(?:ul|ol)>', '\n', text, flags=re.IGNORECASE)
        # <table> 简单处理：移除标签保留内容
        text = re.sub(r'</?table[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</?thead[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</?tbody[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<tr[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<t[dh][^>]*>(.*?)</t[dh]>', r' \1 |', text, flags=re.IGNORECASE | re.DOTALL)
        # 移除其他残留 HTML 标签
        text = re.sub(r'</?(?:div|span|section|article|header|footer|nav|aside)[^>]*>', '', text, flags=re.IGNORECASE)
        return text

    def _normalize_headings(self, text: str) -> str:
        """保留原始标题层级，不做降级处理"""
        return text
        # 以下代码已禁用 — 降级标题会破坏文档结构
        lines = text.split('\n')
        result = []
        for line in lines:
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                hashes = match.group(1)
                content = match.group(2)
                # 将 # 和 ## 降级为 ###，保持 ### 及以下不变
                if len(hashes) < 3:
                    line = f"### {content}"
            result.append(line)
        return '\n'.join(result)

    def _clean_whitespace(self, text: str) -> str:
        """清理多余空白"""
        # 行尾空格
        text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
        # 连续 3 个以上空行合并为 2 个
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
