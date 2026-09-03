"""PDF -> structured price extraction via Gemini.

Pipeline per document: pdftotext (poppler, sub-second) -> Gemini with the
extraction skill as system instruction and the enforced JSON schema at
temperature 0 -> deterministic unit normalization. Scanned PDFs (no usable
text layer) are sent to Gemini natively — the model reads documents directly.
"""

import asyncio
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path

from google import genai
from google.genai import types

from .normalize import (
    apply_discounts, normalize_units, null_values, sanity_warnings,
    text_numbers, ungrounded_values,
)

logger = logging.getLogger("price-agent.extractor")

MIN_TEXT_CHARS = 200  # below this the PDF is treated as scanned

TEXT_PROMPT = (
    "Extract the electricity price tables from the following price proposal "
    "text (source file: {filename}) into the required JSON structure.\n\n```\n{text}\n```"
)
SCANNED_PROMPT = (
    "Extract the electricity price tables from this scanned price proposal "
    "document into the required JSON structure."
)


class PriceExtractor:
    def __init__(self, api_key: str, model: str, skill_dir: Path, max_concurrency: int = 5):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.schema = json.loads((skill_dir / "schema.json").read_text(encoding="utf-8"))
        self.semaphore = asyncio.Semaphore(max_concurrency)

    @staticmethod
    def _extract_text(pdf_path: str) -> str:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, text=True, timeout=120,
        )
        return result.stdout or ""

    async def _call_llm(self, contents: list) -> dict:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=self.skill,
                response_mime_type="application/json",
                response_json_schema=self.schema,
                temperature=0,
            ),
        )
        return json.loads(response.text), getattr(response, "usage_metadata", None)

    async def extract(self, pdf_bytes: bytes, filename: str) -> dict:
        """Returns the extracted_tables payload ({filename, producto: [...]}).

        Grounding safety net (text-layer PDFs only): every raw price the model
        reports must literally exist in the source text. If any value is
        ungrounded (probable digit slip), retry the LLM call once; values still
        ungrounded after the retry are nulled and logged — never stored.
        """
        async with self.semaphore:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                tmp.write(pdf_bytes)
                tmp.flush()
                text = await asyncio.to_thread(self._extract_text, tmp.name)

            scanned = len(text.strip()) < MIN_TEXT_CHARS
            if scanned:
                contents = [
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    SCANNED_PROMPT,
                ]
            else:
                contents = [TEXT_PROMPT.format(filename=filename, text=text)]

            started = time.monotonic()
            payload, usage = await self._call_llm(contents)

            if not scanned:
                printed = text_numbers(text)
                bad = ungrounded_values(payload, printed)
                if bad:
                    labels = [f"{b[4]}@{b[3]}" for b in bad]
                    logger.warning("UNGROUNDED [%s] %d values %s — retrying once",
                                   filename, len(bad), labels)
                    payload2, usage2 = await self._call_llm(contents)
                    bad2 = ungrounded_values(payload2, printed)
                    if len(bad2) < len(bad):
                        payload, usage, bad = payload2, usage2, bad2
                    if bad:
                        logger.error("UNGROUNDED-PERSISTENT [%s] nulling %d values: %s",
                                     filename, len(bad),
                                     [(b[4], b[3]) for b in bad])
                        null_values(payload, bad)
            elapsed = round(time.monotonic() - started, 1)

        for note in apply_discounts(payload):
            logger.info("discount [%s] %s", filename, note)
        for note in normalize_units(payload):
            logger.info("unit conversion [%s] %s", filename, note)
        for warning in sanity_warnings(payload):
            logger.warning("SANITY [%s] %s", filename, warning)

        logger.info(
            "extracted [%s] productos=%d mode=%s in=%s out=%s %.1fs",
            filename, len(payload.get("producto", [])),
            "scanned-pdf" if scanned else "text",
            getattr(usage, "prompt_token_count", "?"),
            getattr(usage, "candidates_token_count", "?"), elapsed,
        )
        return payload
