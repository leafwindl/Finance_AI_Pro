"""LLM 联合分段 + 分类器（含重试和规则降级）。

将纯文本直接发给 LLM，由模型一次性完成：
  1. 语义分段（拆分知识点）
  2. KB 分类（KB01-KB06）
  
失败处理：
  - LLM 网络错误：自动重试（exponential backoff，最多 3 次）
  - LLM 返回格式错误：标记为低置信度，触发人工审核
  - LLM 完全失败：fallback 到规则分段（按段落和缩进切分）

替代原有 pipeline：parse（带结构识别）→ classify。
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import urllib.request
import urllib.error

from .prompts import SEGMENT_CLASSIFY_PROMPT, build_segment_prompt

logger = logging.getLogger("knowledge_parser.segmenter")


@dataclass
class SegmentResult:
    """单个分段结果。"""
    title: str = ""
    content: str = ""
    primary_kb: str = "KB01"
    sub_category: str = ""          # KB01-04 等子类编号
    secondary_kb: list[str] = field(default_factory=list)
    confidence: float = 0.5
    keywords: list[str] = field(default_factory=list)
    needs_review: bool = False
    legal_ref: str = ""


class LLMSegmenter:
    """纯文本 → LLM → 分段 + 分类，失败自动降级到规则分段。"""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        endpoint: str = "https://api.deepseek.com/v1/chat/completions",
        max_retries: int = 3,
        max_chars_per_call: int = 6000,
        enable_fallback: bool = True,
        confidence_threshold: float = 0.6,
    ):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.max_retries = max_retries
        self.max_chars_per_call = max_chars_per_call
        self.enable_fallback = enable_fallback  # 是否启用规则降级
        self.confidence_threshold = confidence_threshold  # 置信度阈值，低于此值标记为需要审核

    def ping(self) -> bool:
        try:
            payload = json.dumps({
                "model": self.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            }).encode("utf-8")
            req = urllib.request.Request(
                self.endpoint, data=payload,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            return True
        except Exception as e:
            logger.warning("LLM 连通性检查失败: %s", e)
            return False

    def segment(self, text: str, source_name: str = "") -> list[SegmentResult]:
        """对纯文本进行分段 + 分类。

        长文本自动分批处理。
        失败时自动 fallback 到规则分段。
        """
        if not text.strip():
            return []

        all_results: list[SegmentResult] = []
        chunks = self._split_text(text)

        for i, chunk in enumerate(chunks):
            chunk_name = f"{source_name}[part{i+1}]" if len(chunks) > 1 else source_name
            try:
                results = self._segment_one_with_fallback(chunk, chunk_name)
                all_results.extend(results)
            except Exception as e:
                logger.error("分段失败（包括 fallback）(%s): %s", chunk_name, e)
                # 最后的防线：返回空，但不中断整个流程
                continue

        return all_results

    def classify_chunk(self, text: str, source_name: str = "") -> SegmentResult:
        """只分类一个已切好的 chunk，不允许 LLM 改变 chunk 边界。"""
        if not text.strip():
            return SegmentResult(content=text, needs_review=True)
        if not self.api_key:
            fallback = self._fallback_segment_by_rules(text, source_name)
            return fallback[0] if fallback else SegmentResult(content=text, needs_review=True)
        try:
            results = self._segment_one_llm(text, source_name)
            if results:
                result = results[0]
                result.content = text
                return result
        except Exception as exc:
            logger.warning("chunk 分类失败 (%s): %s，使用规则降级", source_name, exc)

        fallback = self._fallback_segment_by_rules(text, source_name)
        if fallback:
            fallback[0].content = text
            return fallback[0]
        return SegmentResult(content=text, needs_review=True)

    def _segment_one_with_fallback(self, text: str, source_name: str) -> list[SegmentResult]:
        """单段分段（带 fallback）。
        
        优先用 LLM，LLM 失败则 fallback 到规则分段。
        """
        try:
            # 尝试用 LLM
            results = self._segment_one_llm(text, source_name)
            if results:
                logger.info("LLM 分段成功 (%s): %d 个结果", source_name, len(results))
                return results
            else:
                logger.warning("LLM 返回空结果 (%s)，使用规则 fallback", source_name)
        except Exception as e:
            logger.warning("LLM 分段失败 (%s): %s，使用规则 fallback", source_name, e)

        # Fallback 到规则分段
        if self.enable_fallback:
            logger.info("启用规则分段 fallback (%s)", source_name)
            return self._fallback_segment_by_rules(text, source_name)
        else:
            logger.error("LLM 分段失败且未启用 fallback (%s)", source_name)
            raise RuntimeError(f"LLM 分段失败且未启用 fallback: {source_name}")

    def _split_text(self, text: str) -> list[str]:
        """将长文本按字符数拆分，尽量在段落边界断。"""
        if len(text) <= self.max_chars_per_call:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.max_chars_per_call, len(text))
            # 尝试在双换行处断开
            if end < len(text):
                break_point = text.rfind("\n\n", start, end)
                if break_point > start + self.max_chars_per_call // 2:
                    end = break_point + 2
            chunks.append(text[start:end])
            start = end
        return chunks

    def _segment_one_llm(self, text: str, source_name: str) -> list[SegmentResult]:
        """用 LLM 对单段文本做分段+分类（不含 fallback）。"""
        user_msg = build_segment_prompt(text, source_name)
        response = self._call_api_with_retry(user_msg)
        return self._parse_response(response, source_name=source_name)

    def _call_api_with_retry(self, user_input: str) -> str:
        """调用 LLM API，带 exponential backoff 重试。
        
        重试策略：
        - 第 0 次：立即重试
        - 第 1 次：等待 2 秒
        - 第 2 次：等待 4 秒
        - 第 3 次：等待 8 秒
        """
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": SEGMENT_CLASSIFY_PROMPT},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }).encode("utf-8")

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    self.endpoint, data=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"]["content"]
                    tokens = data.get("usage", {}).get("total_tokens", 0)
                    logger.info("LLM API 调用成功 (第 %d 次尝试, %d tokens)", attempt, tokens)
                    return content
            except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError, TimeoutError) as e:
                last_error = e
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt  # exponential backoff: 1, 2, 4, 8...
                    logger.warning(
                        "LLM API 调用失败 (第 %d 次尝试), %d 秒后重试: %s",
                        attempt, wait_time, type(e).__name__
                    )
                    time.sleep(wait_time)
                else:
                    logger.error("LLM API 调用失败 (已重试 %d 次): %s", self.max_retries, e)

        raise RuntimeError(f"LLM API 调用失败（已重试 {self.max_retries} 次）: {last_error}")

    def _parse_response(self, raw: str, source_name: str = "") -> list[SegmentResult]:
        """解析 LLM 响应，计算置信度，标记低置信度为需审核。
        
        置信度计算规则：
        - 基础分数：从 LLM 返回的 confidence
        - JSON 格式错误：-0.3
        - 必填字段缺失：-0.2
        - KB 分类异常：-0.1
        - KB02（法规）强制标记需审核
        """
        # 提取 JSON 数组
        start = raw.find("[")
        end = raw.rfind("]")
        json_str = None
        json_parse_success = True
        
        if start >= 0 and end > start:
            json_str = raw[start:end + 1]
        else:
            logger.warning("LLM 响应未找到 JSON 数组: %s", raw[:200])
            json_parse_success = False

        items = []
        try:
            if json_str:
                items = json.loads(json_str)
            else:
                items = []
        except json.JSONDecodeError as e:
            logger.warning("LLM 返回非标准 JSON (%s): %s", source_name, str(e)[:100])
            json_parse_success = False

        results = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                logger.warning("LLM 返回项不是字典，跳过: %s", type(item))
                continue

            # 计算置信度
            confidence = float(item.get("confidence", 0.5))
            
            # 调整置信度
            if not json_parse_success:
                confidence -= 0.3
                logger.debug("JSON 格式错误，置信度 -0.3")
            
            # 检查必填字段
            if not item.get("title") or not item.get("content"):
                confidence -= 0.2
                logger.debug("缺少必填字段 (title/content)，置信度 -0.2")
            
            # 检查 KB 分类有效性
            primary_kb = item.get("primary_kb", "KB01")
            if not re.match(r"^KB0[1-6]$", primary_kb):
                confidence -= 0.1
                logger.debug("主 KB 分类异常: %s，置信度 -0.1", primary_kb)
                primary_kb = "KB01"  # 降级到默认
            
            # 约束置信度范围 [0, 1]
            confidence = max(0.0, min(1.0, confidence))
            
            # 判断是否需要审核
            needs_review = (
                item.get("needs_review", False)
                or primary_kb == "KB02"  # KB02（法规）强制审核
                or confidence < self.confidence_threshold  # 低置信度强制审核
                or not json_parse_success  # JSON 格式错误强制审核
            )

            results.append(SegmentResult(
                title=item.get("title", f"自动分段 {idx+1}"),
                content=item.get("content", ""),
                primary_kb=primary_kb,
                sub_category=item.get("sub_category", ""),
                secondary_kb=item.get("secondary_kb", []),
                confidence=confidence,
                keywords=item.get("keywords", []),
                needs_review=needs_review,
                legal_ref=item.get("legal_ref", ""),
            ))

            if needs_review:
                logger.info(
                    "标记为需审核 (%s): KB=%s, confidence=%.2f, reason=%s",
                    source_name, primary_kb, confidence,
                    f"primary_kb={'KB02'}, confidence<{self.confidence_threshold}, json_error"
                    if primary_kb == "KB02" or confidence < self.confidence_threshold or not json_parse_success
                    else "用户标记"
                )

        return results

    def _fallback_segment_by_rules(self, text: str, source_name: str) -> list[SegmentResult]:
        """规则分段 fallback：按段落和缩进切分。
        
        策略：
        1. 按空行分割段落
        2. 清理过短的段落（<20 字）
        3. 每个段落生成一个 SegmentResult，KB 分类设为 KB01（需手工审核）
        4. 置信度设为 0.3（低置信度，标记需审核）
        """
        if not text.strip():
            return []

        # 按双换行分割（段落）
        paragraphs = re.split(r"\n\n+", text.strip())
        
        results = []
        for para_idx, para in enumerate(paragraphs):
            para = para.strip()
            
            # 从段落首行提取标题
            lines = para.split("\n")
            first_line = lines[0].strip()
            
            # 如果首行像标题（< 50 字）则作为标题，否则用前 50 字
            if len(first_line) < 50 and not first_line.endswith("。"):
                title = first_line
            else:
                title = para[:50] + ("..." if len(para) > 50 else "")
            
            results.append(SegmentResult(
                title=title,
                content=para,
                primary_kb="KB01",  # 默认分类为 KB01
                sub_category="",
                secondary_kb=[],
                confidence=0.3,  # 低置信度
                keywords=[],
                needs_review=True,  # 强制标记为需审核（规则分段）
                legal_ref="",
            ))
            
            logger.debug("规则分段 (%s) [para %d]: %s (%.0f 字)", source_name, para_idx, title[:30], len(para))

        if results:
            logger.info("规则分段完成 (%s): %d 个段落", source_name, len(results))
        else:
            logger.warning("规则分段无结果 (%s): 文本过短或格式异常", source_name)

        return results
