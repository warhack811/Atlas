"""
ATLAS Yönlendirici - Yanıt Üretici (Generator)
---------------------------------------------
Bu bileşen, seçilen yapay zeka modelleriyle iletişime geçerek nihai yanıtın
üretilmesini sağlar. Hem tekil (standart) hem de akış (streaming) formatında
üretimi destekler.

Temel Sorumluluklar:
1. Model Entegrasyonu: Google Gemini (SDK v1.0) ve Groq (REST) üzerinden model çağrıları.
2. Bağlantı Havuzu (Pooling): HTTP istemcilerini verimli kullanarak ağ gecikmesini azaltma.
3. Bütçe ve Kota Kontrolü: BudgetTracker üzerinden model limitlerini denetleme.
4. Akış Yönetimi: Token'ları üretildiği anda ileterek kullanıcı deneyimini iyileştirme.
5. Hata Yönetimi: KeyManager ile API anahtarı bazlı hata takibi ve raporlama.
"""

import os
import httpx
import json
import logging
from typing import Optional, AsyncGenerator
from dataclasses import dataclass
from google import genai
from google.genai import types

from .config import API_CONFIG
from .time_context import time_context

logger = logging.getLogger(__name__)

# =============================================================================
# BAĞLANTI HAVUZU (CONNECTION POOLING) - Paylaşımlı HTTP İstemcisi
# =============================================================================
class GlobalClient:
    """Merkezi AsyncClient yönetimi (Connection Pooling için)."""
    _client: Optional[httpx.AsyncClient] = None

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(
                timeout=60.0,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
            )
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client:
            await cls._client.aclose()
            cls._client = None


# =============================================================================
# YAPILANDIRILMIŞ SONUÇ (STRUCTURED RESULT)
# =============================================================================
@dataclass
class GeneratorResult:
    ok: bool
    text: str
    error_code: str = ""
    retryable: bool = False
    tokens: int = 0
    model: str = ""

    def __str__(self):
        return self.text


def _beautify_response(text: str) -> str:
    """Varsa beautiful_response eklenti formatını uygula."""
    try:
        from app.plugins.beautiful_response.parser import parse_response
        from app.plugins.beautiful_response.enhancer import enhance_response
        
        structured = parse_response(text)
        enhanced = enhance_response(structured)
        return enhanced if enhanced else text
    except:
        return text


async def generate_response(
    message: str,
    model_id: str,
    intent: str,
    session_id: str = None,
    api_key: Optional[str] = None,
    style_profile: Optional[dict] = None,
    signal_only: bool = False
) -> GeneratorResult:
    """Belirlenen model ve bağlamı kullanarak tekil (blok) yanıt oluşturur."""
    
    # Yerel model (Ollama vb.) kontrolü
    if "local" in model_id.lower():
        return await _generate_local(message, model_id)

    from .key_manager import KeyManager
    current_key = api_key or KeyManager.get_best_key(model_id=model_id)
    
    if not current_key:
        return GeneratorResult(ok=False, text=f"{model_id} için anahtar bulunamadı", error_code="MOCK", retryable=True, model=model_id)
    
    from .budget_tracker import budget_tracker
    budget_ok, budget_error = budget_tracker.check_budget(model_id)
    if not budget_ok:
        return GeneratorResult(ok=False, text=budget_error, error_code="BUDGET", retryable=False, model=model_id)
    
    from .prompts import INTENT_SYSTEM_PROMPTS, COT_SUPPRESSION_PROMPT
    intent_to_category = {"coding": "coding", "debug": "coding", "creative": "creative", "analysis": "analysis"}
    category = intent_to_category.get(intent, "general")
    system_prompt = INTENT_SYSTEM_PROMPTS.get(category, INTENT_SYSTEM_PROMPTS["general"])
    
    # Düşünce zinciri (CoT) modellerinde ara düşünceleri gizleme promptu ekle
    if "qwen" in model_id.lower() or "deepseek" in model_id.lower():
        system_prompt += "\n" + COT_SUPPRESSION_PROMPT

    # Oturum geçmişi varsa bağlamı oluştur, yoksa sadece güncel mesajı kullan
    if session_id:
        from .memory import ContextBuilder
        messages = ContextBuilder(session_id).with_system_prompt(system_prompt).build(message, history_limit=5, signal_only=signal_only)
    else:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}]
    
    try:
        if "gemini" in model_id.lower():
            return await _call_gemini(model_id, current_key, messages)
        else:
            return await _call_groq(model_id, current_key, messages, intent)
    except Exception as e:
        KeyManager.report_error(current_key, error_msg=str(e), model_id=model_id)
        return GeneratorResult(ok=False, text=str(e), error_code="EXCEPTION", retryable=True, model=model_id)


async def generate_stream(
    message: str,
    model_id: str,
    intent: str,
    session_id: str = None,
    api_key: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """Token'ları üretildiği anda döndüren asenkron akış (streaming) üretimi."""
    from .key_manager import KeyManager
    from .prompts import INTENT_SYSTEM_PROMPTS, COT_SUPPRESSION_PROMPT
    
    current_key = api_key or KeyManager.get_best_key(model_id=model_id)
    if not current_key:
        yield "Hata: API anahtarı bulunamadı"
        return

    intent_to_category = {"coding": "coding", "debug": "coding", "creative": "creative", "analysis": "analysis"}
    category = intent_to_category.get(intent, "general")
    system_prompt = INTENT_SYSTEM_PROMPTS.get(category, INTENT_SYSTEM_PROMPTS["general"])
    
    if "qwen" in model_id.lower() or "deepseek" in model_id.lower():
        system_prompt += "\n" + COT_SUPPRESSION_PROMPT

    if session_id:
        from .memory import ContextBuilder
        messages = ContextBuilder(session_id).with_system_prompt(system_prompt).build(message, history_limit=5)
    else:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}]

    try:
        if "gemini" in model_id.lower():
            async for chunk in _stream_gemini(model_id, current_key, messages):
                yield chunk
        else:
            async for chunk in _stream_groq(model_id, current_key, messages, intent):
                yield chunk
    except Exception as e:
        yield f"Akış Hatası: {str(e)}"


async def _call_groq(model_id: str, api_key: str, messages: list, intent: str) -> GeneratorResult:
    from .config import INTENT_TEMPERATURE
    from .key_manager import KeyManager
    
    temperature = INTENT_TEMPERATURE.get(intent, API_CONFIG["default_temperature"])
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": API_CONFIG.get("max_tokens", 2048),
        "response_format": {"type": "json_object"} if intent == "analysis" else None
    }
    if "qwen" in model_id.lower() or "deepseek" in model_id.lower():
        payload["reasoning_format"] = "hidden"

    client = await GlobalClient.get_client()
    response = await client.post(
        f"{API_CONFIG['groq_api_base']}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload
    )
        
    if response.status_code == 200:
        KeyManager.report_success(api_key, model_id=model_id)
        data = response.json()
        raw_response = data["choices"][0]["message"].get("content", "").strip()
        return GeneratorResult(ok=True, text=_beautify_response(raw_response), model=model_id)
    
    KeyManager.report_error(api_key, status_code=response.status_code, model_id=model_id)
    return GeneratorResult(ok=False, text=f"Groq Hatası {response.status_code}", retryable=True, model=model_id)


async def _call_gemini(model_id: str, api_key: str, messages: list) -> GeneratorResult:
    """Modern SDK v1.0 (google-genai) kullanarak Gemini modellerini çağırır."""
    from .key_manager import KeyManager
    
    client = genai.Client(api_key=api_key)
    
    # Yeni SDK formatına dönüştür
    contents = []
    system_instruction = None
    for m in messages:
        if m["role"] == "system":
            system_instruction = m["content"]
        else:
            role = "user" if m["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

    try:
        response = await client.aio.models.generate_content(
            model=model_id,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7
            )
        )
        KeyManager.report_success(api_key, model_id=model_id)
        return GeneratorResult(ok=True, text=response.text, model=model_id)
    except Exception as e:
        KeyManager.report_error(api_key, error_msg=str(e), model_id=model_id)
        return GeneratorResult(ok=False, text=str(e), error_code="API_ERROR", retryable=True, model=model_id)


async def _stream_gemini(model_id: str, api_key: str, messages: list):
    """Gemini modelleri için asenkron akış (streaming) desteği."""
    client = genai.Client(api_key=api_key)
    
    contents = []
    system_instruction = None
    for m in messages:
        if m["role"] == "system":
            system_instruction = m["content"]
        else:
            role = "user" if m["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

    try:
        async for chunk in await client.aio.models.generate_content_stream(
            model=model_id,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_instruction)
        ):
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"Gemini Akış Hatası: {str(e)}"


async def _stream_groq(model_id: str, api_key: str, messages: list, intent: str):
    from .config import INTENT_TEMPERATURE
    temperature = INTENT_TEMPERATURE.get(intent, API_CONFIG["default_temperature"])
    payload = {"model": model_id, "messages": messages, "temperature": temperature, "stream": True}
    
    client = await GlobalClient.get_client()
    async with client.stream("POST", f"{API_CONFIG['groq_api_base']}/chat/completions",
                          headers={"Authorization": f"Bearer {api_key}"}, json=payload) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]": break
                try:
                    delta = json.loads(data_str)["choices"][0].get("delta", {})
                    if "content" in delta: yield delta["content"]
                except: continue


async def _generate_local(message: str, model_id: str) -> GeneratorResult:
    try:
        payload = {"model": "llama3", "prompt": message, "stream": False}
        client = await GlobalClient.get_client()
        response = await client.post("http://localhost:11434/api/generate", json=payload, timeout=30.0)
        if response.status_code == 200:
            return GeneratorResult(ok=True, text=response.json().get("response", ""), model="local")
    except: pass
    return GeneratorResult(ok=False, text="Hizmet dışı.", error_code="FINAL_ERROR", model="local")
