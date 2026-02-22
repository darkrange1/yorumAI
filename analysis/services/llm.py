import logging
import os
from typing import Any

from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)


class VertexExpressLLM:
    def __init__(self, api_key: str, model: str):
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Vertex Express için 'google-genai' paketi gerekli.") from exc

        self._client = genai.Client(vertexai=True, api_key=api_key)
        self._model = model

    def generate_text(self, prompt_text: str) -> str:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt_text,
            config=types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                )
            ),
        )

        text = getattr(response, "text", None)
        if text:
            return str(text).strip()

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if not parts:
                continue
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    return str(part_text).strip()

        raise ValueError("Vertex Express yanıtından metin çıkarılamadı.")


def invoke_llm_with_prompt(prompt: PromptTemplate, llm: Any, payload: dict[str, Any]) -> str:
    if isinstance(llm, VertexExpressLLM):
        rendered_prompt = prompt.format(**payload)
        return llm.generate_text(rendered_prompt)

    chain = prompt | llm | StrOutputParser()
    return chain.invoke(payload)


def get_llm():
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    vertex_express_api_key = os.getenv("VERTEX_EXPRESS_API_KEY", "").strip()
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "").strip()
    configured = [
        bool(gemini_api_key),
        bool(vertex_express_api_key),
        bool(ollama_base_url),
    ]
    if sum(configured) > 1:
        logger.warning(
            "Birden fazla LLM sağlayıcısı tanımlı. Öncelik sırası: GEMINI_API_KEY > VERTEX_EXPRESS_API_KEY > OLLAMA_BASE_URL"
        )

    if gemini_api_key:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            temperature=0.0,
            google_api_key=gemini_api_key,
        )

    if vertex_express_api_key:
        return VertexExpressLLM(
            api_key=vertex_express_api_key,
            model=os.getenv("VERTEX_EXPRESS_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")),
        )

    if ollama_base_url:
        from langchain_community.chat_models import ChatOllama

        return ChatOllama(
            base_url=ollama_base_url,
            model=os.getenv("OLLAMA_MODEL", "llama3.1"),
            temperature=0.0,
        )

    return None

