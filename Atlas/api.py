"""
ATLAS Yönlendirici API - Ana Giriş Noktası
-----------------------------------------
Bu dosya, ATLAS mimarisinin dış dünyaya açılan ana kapısıdır. FastAPI kullanarak
hem standart hem de akış (streaming) formatında sohbet arayüzü sağlar.

Temel Sorumluluklar:
1. Sohbet İsteklerini Yönetme: Standart (/chat) ve Akış (/chat/stream) endpoint'leri.
2. Güvenlik Denetimi: SafetyGate entegrasyonu ile giriş güvenliği.
3. Orkestrasyon: Niyet sınıflandırma ve iş planı (DAG) oluşturma süreçlerini tetikleme.
4. Yürütme ve Sentez: DAG yürütücü ve sentezleyici ile nihai yanıtın oluşturulması.
5. İzlenebilirlik: Her işlemin detaylı kaydını (RDR) tutma ve sunma.
6. Altyapı Görevleri: Veritabanı canlılık sinyali (heartbeat) ve statik dosya sunumu.
"""

import os
import time
import asyncio
import json
import logging
import traceback
from datetime import datetime
from typing import Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile, Request, Response, Depends, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import hashlib
import asyncio
from Atlas.memory.semantic_cache import semantic_cache
from Atlas.memory.text_normalize import normalize_text_for_dedupe
from Atlas.config import ENABLE_SEMANTIC_CACHE

# --- FAZ-Y: Single-flight protection for cache stampede mitigation ---
# Bounded lock map to prevent memory leaks
_cache_locks = {}  # {lock_key: asyncio.Lock}
_cache_lock_manager = asyncio.Lock()
MAX_LOCK_MAP_SIZE = 1000  # Staff: Prevent unconstrained growth

async def get_cache_lock(user_id: str, query: str) -> asyncio.Lock:
    """Gets a lock for a specific user+query pattern. Cleans up old locks if full."""
    normalized = normalize_text_for_dedupe(query)
    lock_key = f"{user_id}:{hashlib.md5(normalized.encode()).hexdigest()[:16]}"
    
    async with _cache_lock_manager:
        if lock_key not in _cache_locks:
            # Memory leak protection: if map is too big, clear it
            # Staff: Fixed-size buffer approach for MVP
            if len(_cache_locks) >= MAX_LOCK_MAP_SIZE:
                _cache_locks.clear() 
                logger.info("Cache lock map cleared to prevent memory leak.")
            
            _cache_locks[lock_key] = asyncio.Lock()
        return _cache_locks[lock_key]

logger = logging.getLogger("api")

# Döngüsel içe aktarmayı (circular import) önlemek için burada tanımlanmıştır
from Atlas import rdr
from Atlas.auth import create_session_token, decode_session_token, verify_credentials

app = FastAPI(
    title="ATLAS Router Sandbox",
    description="4-Tier Intent Classification + Model Routing Test Environment",
    version="1.0.0"
)

# CORS Ayarları: Farklı kökenlerden gelen isteklere izin verir
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Modelleri: İstek ve yanıt yapılarını doğrular
class ChatRequest(BaseModel):
    """Kullanıcıdan gelen sohbet isteğinin yapısı."""
    message: str
    session_id: str
    user_id: Optional[str] = None
    use_mock: bool = False
    style: Optional[dict] = None
    mode: Optional[str] = "standard"
    debug_trace: bool = False

class LoginRequest(BaseModel):
    username: str
    password: str




class ChatResponse(BaseModel):
    response: str
    session_id: str
    rdr: dict
    debug_trace: Optional[dict] = None

def serialize_neo4j_value(v):
    """Neo4j'den gelen datetime ve diğer karmaşık nesneleri JSON uyumlu hale getirir."""
    from neo4j.time import DateTime
    if isinstance(v, DateTime):
        return v.isoformat()
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, list):
        return [serialize_neo4j_value(i) for i in v]
    if isinstance(v, dict):
        return {k: serialize_neo4j_value(val) for k, val in v.items()}
    return v

class NotificationAckRequest(BaseModel):
    session_id: str
    notification_id: str

class MemoryForgetRequest(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    scope: str  # "predicate" | "item" | "all"
    predicate: Optional[str] = None
    item_id: Optional[str] = None

class PolicyUpdateRequest(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    memory_mode: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    max_notifications_per_day: Optional[int] = None
    notification_mode: Optional[str] = None

class TaskDoneRequest(BaseModel):
    session_id: str
    task_id: str

class PurgeTestDataRequest(BaseModel):
    user_id_prefix: str = "test_"

class MemoryCorrectionRequest(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    target_type: str # "fact" | "signal"
    predicate: str
    subject_id: Optional[str] = None
    fact_id: Optional[str] = None
    new_value: Optional[str] = None
    mode: str # "replace" | "retract"
    reason: Optional[str] = None



@app.on_event("startup")
async def startup_event():
    """Uygulama başladığında çalışacak görevler."""
    # STARTUP LOGGING FIX: Ensure logs are visible in terminal
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout,
        force=True
    )
    logger.info("ATLAS API Starting up... logging configured.")
    
    from Atlas.scheduler import start_scheduler
    await start_scheduler()


# --- AUTH & SESSION ---

async def get_current_user(atlas_session: Optional[str] = Cookie(None)):
    """Cookie'den kullanıcı bilgisini çözer."""
    if not atlas_session:
        return None
    user_data = decode_session_token(atlas_session)
    return user_data

@app.post("/api/auth/login")
async def login(request: LoginRequest, response: Response):
    role = verify_credentials(request.username, request.password)
    if not role:
        raise HTTPException(status_code=401, detail="Hatalı kullanıcı adı veya şifre")
    
    token = create_session_token(request.username, role)
    # HttpOnly Cookie set et (7 gün)
    response.set_cookie(
        key="atlas_session",
        value=token,
        httponly=True,
        max_age=604800,
        expires=604800,
        path="/",
        samesite="lax",
        secure=False  # Local test için False, prod'da HTTPS varsa True yapılabilir
    )
    return {"message": "Giriş başarılı", "username": request.username, "role": role}

@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(key="atlas_session", path="/")
    return {"message": "Çıkış yapıldı"}

@app.get("/api/auth/me")
async def get_me(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Oturum açılmamış")
    return {"username": user["username"], "role": user["role"]}


# --- CHAT ENDPOINTS ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    """Standart blok yanıt üreten ana sohbet endpoint'i."""
    from Atlas.memory import SessionManager, MessageBuffer
    import Atlas.orchestrator as orchestrator
    import Atlas.dag_executor as dag_executor
    import Atlas.synthesizer as synthesizer
    
    start_time = time.time()
    
    # 0. ERİŞİM KONTROLÜ: INTERNAL_ONLY modunda whitelist kontrolü
    # Öncelik: login > body > session_id
    logged_in_username = user["username"] if user else None
    user_id = (logged_in_username or request.user_id or request.session_id).lower()
    
    from Atlas.config import is_user_whitelisted, INTERNAL_ONLY
    if not is_user_whitelisted(user_id):
        logger.warning(f"INTERNAL_ONLY: Erişim reddedildi - user_id: {user_id}")
        raise HTTPException(
            status_code=403, 
            detail="Bu API şu anda sadece yetkili kullanıcılara açıktır. (INTERNAL_ONLY mode)"
        )
    
    # 1. GÜVENLİK DENETİMİ: Girdide zararlı içerik veya hassas veri (PII) kontrolü
    from Atlas.safety import safety_gate
    is_safe, sanitized_text, issues, used_model = await safety_gate.check_input_safety(request.message)
    safety_ms = int((time.time() - start_time) * 1000)
    
    if not is_safe:
        record = rdr.RDR.create(request.message)
        record.safety_passed = False
        record.safety_model = used_model
        record.safety_ms = safety_ms
        record.injection_blocked = True
        record.safety_issues = [{"type": "INJECTION", "details": i.details} for i in issues]
        rdr.save_rdr(record)
        
        return ChatResponse(
            response="[GÜVENLİK ENGELİ] Mesajınız güvenlik politikaları gereği engellendi.",
            session_id=request.session_id,
            rdr=record.to_dict()
        )
    
    safety_info = {
        "passed": is_safe,
        "issues": [{"type": i.type, "details": i.details} for i in issues],
        "pii_redacted": any(i.type == "PII" for i in issues)
    }
        
    user_message = sanitized_text
    
    try:
        session_id = request.session_id
        # user_id yukarıda erişim kontrolünde zaten belirlenmişti (priority: login > body > session_id)
        # Ancak burada tekrar atanması gerekebilir eğer yerel kapsamda kullanılıyorsa
        logged_in_username = user["username"] if user else None
        user_id = (logged_in_username or request.user_id or session_id).lower()
        
        # RC-2: Kullanıcı-Session eşleşmesini sağla
        from Atlas.memory.neo4j_manager import neo4j_manager
        await neo4j_manager.ensure_user_session(user_id, session_id)
        
        # RC-3: Transcript Persistence (User Turn)
        await neo4j_manager.append_turn(user_id, session_id, "user", user_message)
        
        MessageBuffer.add_user_message(session_id, user_message)
        
        # RC-1/RC-2/RC-9: AtlasRequestContext Pattern
        from Atlas.memory.request_context import AtlasRequestContext
        from Atlas.memory.trace import ContextTrace
        from Atlas.config import DEBUG
        
        # Persona seçimi (Default: friendly)
        persona_name = (request.style.get("persona") if request.style else None) or "friendly"
        
        trace = None
        if DEBUG and request.debug_trace:
            trace = ContextTrace(request_id=f"trace_{int(time.time())}", user_id=user_id, session_id=session_id)
        
        # Create unified request context (fetches identity from Neo4j ONCE)
        request_context = await AtlasRequestContext.create(
            request_id=f"req_{int(time.time())}",
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            persona=persona_name,
            trace=trace
        )
        
        # Legacy ContextBuilder bridge (for backward compatibility with orchestrator)
        from Atlas.memory.context import ContextBuilder
        cb = ContextBuilder(session_id, user_id=user_id).with_system_prompt(request_context.system_prompt)
        cb.with_neo4j_context(request_context.neo4j_context_str)
        
        # --- PHASE 0.5: Y.5 SEMANTIC CACHE CHECK (Staff Refined) ---
        cache_hit = False
        cache_metadata = {"hit": False, "latency_ms": 0, "similarity": 0.0}
        
        if ENABLE_SEMANTIC_CACHE:
            cache_lock = await get_cache_lock(user_id, user_message)
            async with cache_lock:
                try:
                    cache_res = await semantic_cache.get_with_meta(user_id, user_message)
                    if cache_res["response"]:
                        cache_hit = True
                        cache_metadata["hit"] = True
                        cache_metadata["latency_ms"] = cache_res["latency_ms"]
                        cache_metadata["similarity"] = cache_res["similarity"]
                        
                        # Staff: Persist turn even on hit to keep history coherent
                        await neo4j_manager.append_turn(user_id, session_id, "assistant", cache_res["response"])
                        
                        # Assembler for cached response
                        record_cached = rdr.RDR.create(user_message)
                        record_cached.metadata["cache"] = cache_metadata
                        record_cached.metadata["llm_skipped"] = True
                        record_cached.metadata["orchestrator_skipped"] = True
                        rdr.save_rdr(record_cached)
                        
                        logger.info(f"CACHE HIT: user={user_id}, sim={cache_metadata['similarity']:.3f}, ms={cache_metadata['latency_ms']}")
                        return ChatResponse(
                            response=cache_res["response"],
                            session_id=session_id,
                            rdr=record_cached.to_dict()
                        )
                except Exception as e:
                    logger.warning(f"Semantic cache failure (degrading): {e}")
            cache_metadata["latency_ms"] = cache_metadata.get("latency_ms", 0)
        
        record = rdr.RDR.create(user_message)
        if request_context.neo4j_context_str:
            record.full_context_injection = f"[MEMORY V3]: {request_context.neo4j_context_str}"
        
        # 1. PLANLAMA (ORKESTRASYON): Kullanıcı niyetini anlar ve bir iş planı oluşturur
        from Atlas import orchestrator
        classify_start = time.time()
        plan = await orchestrator.orchestrator.plan(
            session_id, 
            user_message,
            user_id=user_id,
            use_mock=request.use_mock,
            context_builder=cb
        )
            
        classify_ms = int((time.time() - classify_start) * 1000)
        record.intent = plan.active_intent
        record.classification_ms = classify_ms
        record.safety_ms = safety_ms
        record.orchestrator_reasoning = plan.reasoning
        
        # Kullanıcı dostu düşünce adımı ekle
        orchestrator_thought = {"title": "Analiz ve Planlama", "content": plan.user_thought or "İsteğiniz analiz ediliyor..."}
        record.reasoning_steps.append(orchestrator_thought)

        from Atlas.time_context import time_context
        
        record.time_context = time_context.get_context_injection()
        record.rewritten_query = plan.rewritten_query if plan.rewritten_query else user_message
        record.user_facts_dump = []  # Artık Neo4j graf belleği kullanılıyor
        record.full_context_injection = time_context.inject_time_context("", user_message) 
        record.orchestrator_prompt = plan.orchestrator_prompt
        
        # 2. YÜRÜTME (EXECUTION): Planlanan görevleri (araç kullanımı, LLM çağrıları) çalıştırır
        from Atlas import dag_executor
        exec_start = time.time()
        # Pass request_context for identity propagation
        raw_results = await dag_executor.dag_executor.execute_plan(plan, session_id, user_message, request_context=request_context)
        exec_ms = int((time.time() - exec_start) * 1000)
        
        # 3. HARMANLAMA (SENTEZ): Uzmanlardan gelen ham çıktıları tutarlı bir yanıta dönüştürür
        from Atlas import synthesizer
        synth_start = time.time()
        # Pass request_context for identity injection in synthesis
        response_text, synth_model, synth_prompt, synth_metadata = await synthesizer.synthesizer.synthesize(
            raw_results, session_id, plan.active_intent, user_message, mode=request.mode, current_topic=plan.detected_topic, request_context=request_context
        )

        synth_ms = int((time.time() - synth_start) * 1000)
        
        # --- PHASE 3.5: Y.5 CACHE SET ---
        if ENABLE_SEMANTIC_CACHE and not cache_hit:
            try:
                await semantic_cache.set(user_id, user_message, response_text)
            except Exception as e:
                logger.warning(f"Cache set failed: {e}")
        
        record.synthesizer_model = synth_model
        record.synthesizer_prompt = synth_prompt
        record.style_used = True
        record.style_persona = synth_metadata.get("persona", "")
        record.style_preset = synth_metadata.get("mode", "")
            
        # 4. KALİTE DENETİMİ: Oluşturulan yanıtın dil ve format kurallarına uygunluğunu ölçer
        from Atlas.quality import quality_gate
        quality_start = time.time()
        is_passed, issues = quality_gate.check_quality(response_text, plan.active_intent)
        quality_ms = int((time.time() - quality_start) * 1000)
        
        record.quality_passed = is_passed
        from dataclasses import asdict
        record.quality_issues = [asdict(i) for i in issues]
        
        MessageBuffer.add_assistant_message(session_id, response_text)
        
        # RC-3: Transcript Persistence (Assistant Turn)
        from Atlas.memory.neo4j_manager import neo4j_manager
        await neo4j_manager.append_turn(user_id, session_id, "assistant", response_text)
        
        # RC-3/4: Episodic Memory Trigger (Her 20 turn'de bir)
        await _maybe_trigger_episodic_memory(user_id, session_id)
        
        record.dag_execution_ms = exec_ms
        record.synthesis_ms = synth_ms
        record.quality_ms = quality_ms
        
        if trace:
            record.metadata["memory_tiers"] = trace.active_tiers

        # Metadata Injection
        record.metadata["cache"] = cache_metadata
        record.metadata["retrieval_ms"] = int((time.time() - start_time) * 1000) # Simplified
        record.total_ms = int((time.time() - start_time) * 1000)
        record.generation_ms = record.total_ms # Geriye dönük uyumluluk için
        record.safety_passed = safety_info["passed"]
        record.safety_model = used_model
        record.safety_issues = safety_info["issues"]
        record.pii_redacted = safety_info["pii_redacted"]
        
        rdr.save_rdr(record)
        
        # Arka planda bilgi çıkarımı yaparak graf veritabanını günceller
        # FAZ-Y: background_tasks None kontrolü (test ortamı resilience)
        from Atlas.memory.extractor import extract_and_save as extract_and_save_task
        if background_tasks:
            background_tasks.add_task(extract_and_save_task, user_message, user_id, record.request_id)
        else:
            # Fallback for tests/environments without FastAPI BackgroundTasks
            asyncio.create_task(extract_and_save_task(user_message, user_id, record.request_id))

        return ChatResponse(
            response=response_text,
            session_id=session_id,
            rdr=record.to_dict(),
            debug_trace=serialize_neo4j_value(trace.to_dict()) if trace else None
        )
    except Exception as e:
        logger.error(f"Sohbet hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))





    # --- SESSION MANAGEMENT ENDPOINTS ---

@app.get("/api/sessions")
async def list_sessions(user=Depends(get_current_user)):
    """Kullanıcının geçmiş sohbet oturumlarını listeler."""
    if not user:
        return {"sessions": []}
    
    uid = user["username"]
    from Atlas.memory.neo4j_manager import neo4j_manager
    
    # Sessionları ve son aktivite zamanını çek
    query = """
    MATCH (u:User {id: $uid})-[:HAS_SESSION]->(s:Session)
    OPTIONAL MATCH (s)-[:HAS_TURN]->(t:Turn)
    WITH s, max(t.created_at) as last_msg_time, count(t) as msg_count
    ORDER BY COALESCE(last_msg_time, s.created_at) DESC
    RETURN s.id as id, 
           COALESCE(s.title, 'Yeni Sohbet') as title, 
           toString(COALESCE(last_msg_time, s.created_at)) as date,
           msg_count
    """
    try:
        results = await neo4j_manager.query_graph(query, {"uid": uid})
        # Neo4j results are records, need to extract values
        # Assuming query_graph returns list of dicts if using the helper, 
        # but let's be safe and serialize
        formatted_sessions = []
        for r in results:
            # Check if r is a Record object or dict
            # Atlas neo4j_manager.query_graph usually returns list of dicts via `data()`
            formatted_sessions.append(r)
            
        return {"sessions": formatted_sessions}
    except Exception as e:
        logger.error(f"Session list error: {e}")
        return {"sessions": []}

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, user=Depends(get_current_user)):
    """Belirli bir sohbet oturumunu siler."""
    if not user:
        raise HTTPException(status_code=401, detail="Oturum silmek için giriş yapmalısınız.")
    
    uid = user["username"]
    from Atlas.memory.neo4j_manager import neo4j_manager
    success = await neo4j_manager.delete_session(uid, session_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Oturum silinemedi.")
    
    return {"status": "success", "message": f"Session {session_id} silindi."}

@app.delete("/api/sessions")
async def clear_all_sessions(user=Depends(get_current_user)):
    """Kullanıcının tüm sohbet oturumlarını temizler."""
    if not user:
        raise HTTPException(status_code=401, detail="Oturumları temizlemek için giriş yapmalısınız.")
    
    uid = user["username"]
    from Atlas.memory.neo4j_manager import neo4j_manager
    success = await neo4j_manager.delete_all_sessions(uid)
    
    if not success:
        raise HTTPException(status_code=500, detail="Oturumlar temizlenemedi.")
    
    return {"status": "success", "message": "Tüm oturumlar silindi."}

# --- IMPORTS FOR STREAM CHAT ---
from Atlas import safety, rdr
from Atlas.memory import SessionManager, MessageBuffer
from Atlas import orchestrator, dag_executor, synthesizer
from Atlas.memory.neo4j_manager import neo4j_manager
from Atlas.memory.request_context import AtlasRequestContext
from Atlas.memory.trace import ContextTrace

@app.post("/api/chat/stream")
async def stream_chat(request: ChatRequest, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    """
    Yapay zeka yanıtını akan metin (stream) olarak döndürür.
    """
    
    async def event_generator():
        """Süreç adımlarını ve metin parçalarını ileten jeneratör."""
        
        try:
            record = rdr.RDR.create(request.message)
        except Exception as e:
            print(f"[DEBUG] CRITICAL SETUP ERROR: {e}", flush=True)
            yield f"data: {json.dumps({'type': 'error', 'content': f'System Error: {e}'}, default=str)}\n\n"
            return

        try:
            start_time = time.time()
            
            session_id = request.session_id
            logged_in_username = user["username"] if user else None
            user_id = (logged_in_username or request.user_id or session_id).lower()
            
            print("[DEBUG] Step 1: ensure_user_session", flush=True)
            # RC-2: Kullanıcı-Session eşleşmesini sağla
            await neo4j_manager.ensure_user_session(user_id, session_id)
            
            print("[DEBUG] Step 2: append_turn", flush=True)
            # RC-3: Transcript Persistence (User Turn)
            await neo4j_manager.append_turn(user_id, session_id, "user", request.message)
            
            MessageBuffer.add_user_message(session_id, request.message)

            print("[DEBUG] Step 3: check_input_safety", flush=True)
            safety_start = time.time()
            is_safe, sanitized_text, issues, used_model = await safety.safety_gate.check_input_safety(request.message)
            safety_ms = int((time.time() - safety_start) * 1000)
            
            record.safety_passed = is_safe
            record.safety_model = used_model
            record.safety_ms = safety_ms
            record.safety_issues = [{"type": i.type, "details": i.details} for i in issues]
            record.pii_redacted = any(i.type == "PII" for i in issues)

            if not is_safe:
                yield f"data: {json.dumps({'type': 'error', 'content': '[GÜVENLİK ENGELİ] Güvenlik engeli.'}, default=str)}\n\n"
                rdr.save_rdr(record)
                yield f"data: {json.dumps({'type': 'done', 'rdr': record.to_dict()}, default=str)}\n\n"
                return

            classify_start = time.time()
            # 1. Bellek ve Bağlam Hazırlığı - AtlasRequestContext Pattern
            
            persona_name = (request.style.get("persona") if request.style else None) or "friendly"
            
            trace = None
            from Atlas.config import DEBUG
            if DEBUG and request.debug_trace:
                trace = ContextTrace(request_id=f"trace_{int(time.time())}", user_id=user_id, session_id=session_id)
            
            print("[DEBUG] Step 4: AtlasRequestContext.create", flush=True)
            # Create unified request context (fetches identity from Neo4j ONCE)
            request_context = await AtlasRequestContext.create(
                request_id=f"req_{int(time.time())}",
                user_id=user_id,
                session_id=session_id,
                user_message=request.message,
                persona=persona_name,
                trace=trace
            )
            
            # Legacy ContextBuilder bridge (for backward compatibility with orchestrator)
            from Atlas.memory.context import ContextBuilder
            cb = ContextBuilder(session_id, user_id=user_id).with_system_prompt(request_context.system_prompt)
            cb.with_neo4j_context(request_context.neo4j_context_str)
            
            # 2. Orkestrasyon: Niyet analizi ve DAG planı oluşturma
            plan = await orchestrator.orchestrator.plan(session_id, request.message, user_id=user_id, use_mock=request.use_mock, context_builder=cb)
            classify_ms = int((time.time() - classify_start) * 1000)
            
            record.intent = plan.active_intent
            record.orchestrator_model = plan.orchestrator_model
            record.classification_ms = classify_ms
            record.orchestrator_prompt = plan.orchestrator_prompt
            record.orchestrator_reasoning = plan.reasoning
            
            # Kullanıcı dostu düşünce adımı ekle ve stream et
            orchestrator_thought = {"title": "Analiz ve Planlama", "content": plan.user_thought or "İsteğiniz analiz ediliyor..."}
            record.reasoning_steps.append(orchestrator_thought)
            yield f"data: {json.dumps({'type': 'thought', 'step': orchestrator_thought}, default=str)}\n\n"
            
            if request_context.neo4j_context_str:
                record.full_context_injection = f"[NEO4J MEMORY]: {request_context.neo4j_context_str}"
            
            yield f"data: {json.dumps({'type': 'plan', 'intent': plan.active_intent, 'model': plan.orchestrator_model}, default=str)}\n\n"

            exec_start = time.time()
            raw_results = []
            # Pass request_context to dag_executor for downstream propagation
            async for event in dag_executor.dag_executor.execute_plan_stream(plan, session_id, request.message, request_context=request_context):

                if event["type"] == "thought":
                    # Dinamik başlık belirle (Task ID veya tipinden)
                    task_id = event.get("task_id", "")
                    task = next((t for t in plan.tasks if t.id == task_id), None)
                    
                    title = "Operasyonel Adım"
                    if task:
                        if task.type == "tool":
                            title = f"🛠️ {task.tool_name.replace('_', ' ').title()}"
                        elif task.type == "generation":
                            spec_titles = {"logic": "🧠 Mantıksal Analiz", "coding": "💻 Kod Yapılandırma", "search": "🔍 Bilgi Tarama", "tr_creative": "🎭 Yaratıcı Yazım"}
                            title = spec_titles.get(task.specialist, "⚙️ Derin Düşünce")
                    
                    thought_step = {"title": title, "content": event["thought"]}
                    record.reasoning_steps.append(thought_step)
                    yield f"data: {json.dumps({'type': 'thought', 'step': thought_step}, default=str)}\n\n"
                elif event["type"] == "task_result":
                    raw_results.append(event["result"])
            
            exec_ms = int((time.time() - exec_start) * 1000)
            
            record.dag_execution_ms = exec_ms
            record.task_details = [
                {"id": r.get("task_id") or r.get("id"), "model": r.get("model"), "status": "success", "result": r.get("output") or r.get("response"), "duration_ms": r.get("duration_ms", 0)}
                for r in raw_results
            ]
            
            # Sentezleme adımı için düşünce ekle (Havuzdan rastgele seç)
            from Atlas.reasoning_pool import get_random_synthesis_thought
            synth_thought = {"title": "✨ Final Sentez", "content": get_random_synthesis_thought()}
            record.reasoning_steps.append(synth_thought)
            yield f"data: {json.dumps({'type': 'thought', 'step': synth_thought}, default=str)}\n\n"
            
            yield f"data: {json.dumps({'type': 'tasks_done'}, default=str)}\n\n"

            full_response = ""
            synth_start = time.time()
            async for data in synthesizer.synthesizer.synthesize_stream(
                raw_results, session_id, plan.active_intent, request.message, mode=request.mode, current_topic=plan.detected_topic, request_context=request_context
            ):
                if data["type"] == "metadata":
                    record.synthesizer_model = data["model"]
                    record.synthesizer_prompt = data["prompt"]
                    record.style_persona = data["persona"]
                    record.style_preset = data["mode"]
                elif data["type"] == "chunk":
                    chunk = data["content"]
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, default=str)}\n\n"
            
            if not full_response:
                error_msg = "Sentezleyici boş yanıt döndürdü."
                logger.error(error_msg)
                yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, default=str)}\n\n"
                
            synth_ms = int((time.time() - synth_start) * 1000)
            record.synthesis_ms = synth_ms

            MessageBuffer.add_assistant_message(session_id, full_response)
            
            if trace:
                record.metadata["memory_tiers"] = trace.active_tiers
            
            # RC-3: Transcript Persistence (Assistant Turn)
            await neo4j_manager.append_turn(user_id, session_id, "assistant", full_response)
            
            # RC-3: Episodic Memory Trigger (Her 20 turn'de bir)
            count = await neo4j_manager.count_turns(user_id, session_id)
            if count > 0 and count % 20 == 0:
                await neo4j_manager.create_episode(
                    user_id, session_id, 
                    f"Sohbet akış özeti (Turn {count-19}-{count}) - [STUB]", 
                    count-19, count
                )

            record.total_ms = int((time.time() - start_time) * 1000)
            record.generation_ms = record.total_ms

            # Arka planda bilgi çıkarımı yaparak graf veritabanını günceller
            # FAZ-Y: background_tasks None kontrolü
            from Atlas.memory.extractor import extract_and_save as extract_and_save_task
            if background_tasks:
                background_tasks.add_task(extract_and_save_task, request.message, user_id, record.request_id)
            else:
                asyncio.create_task(extract_and_save_task(request.message, user_id, record.request_id))

            rdr.save_rdr(record)
            yield f"data: {json.dumps({'type': 'done', 'rdr': record.to_dict(), 'debug_trace': serialize_neo4j_value(trace.to_dict()) if trace else None}, default=str)}\n\n"

        except Exception as e:
            import traceback
            logger.error(f"Akış hatası: {e}\n{traceback.format_exc()}")
            error_msg = str(e)
            record.technical_errors.append({
                "timestamp": datetime.now().isoformat(),
                "error": error_msg,
                "traceback": traceback.format_exc()
            })
            rdr.save_rdr(record)
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, default=str)}\n\n"
            # Hata durumunda da RDR'yi gönder ki kullanıcı ne olduğunu görsün
            yield f"data: {json.dumps({'type': 'done', 'rdr': record.to_dict()}, default=str)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/rdr/{request_id}")
async def get_rdr_by_id(request_id: str):
    """Belirli bir işlem ID'sine ait teknik detay kaydını getirir."""
    record = rdr.get_rdr(request_id)
    if not record:
        raise HTTPException(status_code=404, detail="RDR bulunamadı")
    return record.to_dict()


@app.get("/api/rdr")
async def get_recent_rdrs(limit: int = 10):
    records = rdr.get_recent_rdrs(limit)
    return [r.to_dict() for r in records]


@app.post("/api/upload")
async def upload_image(session_id: str, file: UploadFile = File(...)):
    """Görsel yükleme ve analiz endpoint'i."""
    try:
        # Importları ve hazırlıkları try içine taşıyarak başlangıç hatalarını da yakalıyoruz
        from Atlas.vision_engine import analyze_image
        from Atlas.safety import safety_gate
        from Atlas.memory import MessageBuffer, SessionManager
        
        logger.info(f"[UPLOAD] Başladı: {file.filename}, Session: {session_id}")
        
        session = SessionManager.get_or_create(session_id)
        session_id = session.id
        
        content = await file.read()
        logger.info(f"[UPLOAD] Dosya okundu: {len(content)} byte")
        
        if not content:
            return {"status": "error", "message": "Boş dosya gönderildi."}

        # 1. Görsel Analizi
        logger.info("[UPLOAD] Vision Engine çağrılıyor...")
        analysis_text = await analyze_image(content)
        logger.info(f"[UPLOAD] Analiz bitti: {analysis_text[:50]}...")
        
        # 2. Güvenlik Denetimi
        logger.info("[UPLOAD] Güvenlik kontrolü başlatılıyor...")
        is_safe, sanitized_text, issues, used_model = await safety_gate.check_input_safety(analysis_text)
        logger.info(f"[UPLOAD] Güvenlik bitti. Geçti mi: {is_safe} ({used_model})")
        
        # 3. Belleğe Kayıt
        system_note = f"[BAĞLAM - GÖRSEL ANALİZİ ({file.filename})]: {sanitized_text}"
        MessageBuffer.add_user_message(session_id, system_note)
        
        return {
            "status": "success",
            "filename": file.filename,
            "analysis": sanitized_text,
            "safety_passed": is_safe,
            "used_model": used_model
        }

    except ImportError as ie:
        logger.error(f"[UPLOAD] Import Hatası: {ie}")
        return {"status": "error", "message": f"Sistem bileşeni eksik: {str(ie)}", "traceback": traceback.format_exc()}
    except Exception as e:
        err_msg = f"Yükleme hatası detayı: {e}"
        logger.error(f"[UPLOAD] {err_msg}\n{traceback.format_exc()}")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }


@app.get("/api/health")
async def health():
    """Sistem sağlığı ve altyapı bağlantılarını raporlar (Oracle VM Uyumluluk Testi)."""
    from Atlas.key_manager import KeyManager
    from Atlas.memory.neo4j_manager import neo4j_manager
    from Atlas.memory.qdrant_manager import qdrant_manager
    from Atlas.memory.semantic_cache import semantic_cache
    
    # 1. Ortam Değişkenleri Kontrolü (Sadece varlık kontrolü)
    env_status = {
        "REDIS": "OK" if os.getenv("REDIS_URL") else "MISSING",
        "QDRANT": "OK" if os.getenv("QDRANT_URL") and os.getenv("QDRANT_API_KEY") else "MISSING",
        "NEO4J": "OK" if os.getenv("NEO4J_URI") else "MISSING",
        "GEMINI": "OK" if os.getenv("GOOGLE_API_KEY") else "MISSING",
        "GROQ": "OK" if os.getenv("GROQ_API_KEY") or os.getenv("MODEL_KEYS") else "MISSING"
    }
    
    # 2. Canlı Bağlantı Testleri
    db_status = {"neo4j": "Error", "qdrant": "Error", "redis": "Error"}
    
    try:
        # Neo4j testi
        await neo4j_manager.query_graph("RETURN 1 as test")
        db_status["neo4j"] = "Connected"
    except Exception as e: db_status["neo4j"] = f"Failed: {str(e)}"

    try:
        # Qdrant testi
        q_healthy = await qdrant_manager.health_check()
        db_status["qdrant"] = "Connected" if q_healthy else "Unreachable"
    except: db_status["qdrant"] = "Connection Error"

    try:
        # Redis testi
        if semantic_cache.client:
            await semantic_cache.client.ping()
            db_status["redis"] = "Connected"
        else:
            db_status["redis"] = "Disabled (No URL)"
    except: db_status["redis"] = "Connection Error"

    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "env_check": env_status,
        "connectivity": db_status,
        "key_manager": {
            "available_keys": KeyManager.get_available_count(),
            "active_models": list(KeyManager.get_stats().keys())
        }
    }


# --- FAZ 7: Bildirim ve Görev Yönetimi ---

@app.get("/api/notifications")
async def get_notifications(session_id: str, user_id: Optional[str] = None):
    """Kullanıcının bekleyen bildirimlerini getirir (FAZ7/RC-2)."""
    uid = user_id if user_id else session_id
    from Atlas.memory.neo4j_manager import neo4j_manager
    await neo4j_manager.ensure_user_session(uid, session_id)
    
    from Atlas.observer import observer
    notifications = await observer.get_notifications(uid)
    # RC-1: JSON serialization safety
    safe_notifications = serialize_neo4j_value(notifications)
    return {"notifications": safe_notifications, "user_id": uid}

@app.post("/api/notifications/ack")
async def acknowledge_notification(request: NotificationAckRequest, user_id: Optional[str] = None):
    """Bildirimi okundu olarak işaretler (FAZ7/RC-2)."""
    uid = user_id if user_id else request.session_id
    from Atlas.memory.neo4j_manager import neo4j_manager
    success = await neo4j_manager.acknowledge_notification(uid, request.notification_id)
    return {"status": "success" if success else "error", "user_id": uid}

@app.get("/api/tasks")
async def get_tasks(session_id: str, user_id: Optional[str] = None):
    """Kullanıcının açık görevlerini listeler (FAZ7/RC-2)."""
    uid = user_id if user_id else session_id
    from Atlas.memory.neo4j_manager import neo4j_manager
    await neo4j_manager.ensure_user_session(uid, session_id)
    
    from Atlas.memory.prospective_store import list_open_tasks
    tasks = await list_open_tasks(uid)
    # RC-1: JSON serialization safety
    safe_tasks = serialize_neo4j_value(tasks)
    return {"tasks": safe_tasks, "user_id": uid}

@app.post("/api/tasks/done")
async def complete_task(request: TaskDoneRequest, user_id: Optional[str] = None):
    """Görevi tamamlandı olarak işaretler (FAZ7/RC-2)."""
    uid = user_id if user_id else request.session_id
    from Atlas.memory.neo4j_manager import neo4j_manager
    from Atlas.memory.prospective_store import mark_task_done
    success = await mark_task_done(uid, request.task_id)
    return {"status": "success" if success else "error", "user_id": uid}

# --- RC-2: Bellek Kontrol Endpoint'leri ---

@app.get("/api/memory")
async def get_memory_status(session_id: str, user_id: Optional[str] = None):
    """Kullanıcının bellek durumunun bir özetini döndürür. (RC-2)"""
    uid = user_id if user_id else session_id
    from Atlas.memory.neo4j_manager import neo4j_manager
    from Atlas.memory.context import build_memory_context_v3
    from Atlas.memory.prospective_store import list_open_tasks
    from Atlas.observer import observer
    
    # 1. Context V3 (Kişisel hafıza özeti)
    context = await build_memory_context_v3(uid, "summary_request", session_id=session_id)
    
    # 2. Son görevler
    tasks = await list_open_tasks(uid)
    
    # 3. Bildirimler
    notifications = await observer.get_notifications(uid)
    
    # 4. Ayarlar
    settings = await neo4j_manager.get_user_settings(uid)
    
    return {
        "user_id": uid,
        "memory_summary": context,
        "tasks": serialize_neo4j_value(tasks[:20]),
        "notifications": serialize_neo4j_value(notifications[:20]),
        "settings": settings
    }

@app.get("/api/history/{session_id}")
async def get_chat_history(session_id: str, user=Depends(get_current_user)):
    """Oturumun tüm konuşma geçmişini döner (UI desteği için)."""
    if not user:
        raise HTTPException(status_code=401, detail="Oturum geçmişi için giriş yapmalısınız.")
    
    uid = user["username"]
    from Atlas.memory.neo4j_manager import neo4j_manager
    
    # Session sahipliğini doğrula
    turns = await neo4j_manager.get_recent_turns(uid, session_id, limit=100)
    return {"session_id": session_id, "history": serialize_neo4j_value(turns)}

@app.post("/api/memory/forget")
async def forget_memory(request: MemoryForgetRequest):
    """
    Kullanıcının belirli bir bilgiyi veya tüm hafızasını 'unutmasını' sağlar. (RC-2/V4.3)
    Strateji: Varsayılan olarak arşivler (superseded), 'hard' parametresi ile kalıcı siler.
    """
    uid = request.user_id if request.user_id else request.session_id
    from Atlas.memory.neo4j_manager import neo4j_manager
    
    # V4.3: request modeline 'hard' flag'i eklenebilir veya varsayılan arşivleme yapılır.
    # Şimdilik plan gereği 'arşivleme' odaklı ilerliyoruz.
    is_hard = getattr(request, 'hard', False) 
    
    try:
        if request.scope == "all":
            # V4.3: delete_all_memory artık Turn, Session ve Episode'ları da temizliyor.
            await neo4j_manager.delete_all_memory(uid)
            message = "Tüm hafıza ve konuşma geçmişi başarıyla temizlendi."
            
        elif request.scope == "predicate" and request.predicate:
            # Belirli bir yüklem (preference vb) bazlı arşivleme
            # NOT: Bu operasyon neo4j_manager içinde özelleştirilmiş bir metod gerektirebilir
            # Ancak MVP olarak Cypher üzerinden V4.3 uyumlu arşivleme yapıyoruz.
            query = """
            MATCH ()-[r:FACT {user_id: $uid}]->() 
            WHERE toUpper(r.predicate) = $pred AND (r.status = 'ACTIVE' OR r.status IS NULL)
            SET r.status = 'SUPERSEDED', r.valid_until = datetime(), r.updated_at = datetime()
            RETURN count(r) as count
            """
            res = await neo4j_manager.query_graph(query, {"uid": uid, "pred": request.predicate.upper()})
            count = res[0]['count'] if res else 0
            message = f"'{request.predicate}' kategorisindeki {count} kayıt arşivlendi."
            
        elif request.scope == "item" and request.item_id:
            # Belirli bir entity (Nesne) bazlı unutma
            count = await neo4j_manager.forget_fact(uid, request.item_id, hard_delete=is_hard)
            action = "silindi" if is_hard else "arşivlendi"
            message = f"'{request.item_id}' ile ilgili {count} kayıt {action}."
            
        else:
            raise HTTPException(status_code=400, detail="Geçersiz forget kapsamı veya eksik parametre.")
            
        return {"success": True, "message": message}
    except Exception as e:
        logger.error(f"API Memory Forget hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/correct")
async def correct_memory(request: MemoryCorrectionRequest):
    """
    Kullanıcı geri bildirimi ile hafızayı düzeltir. (RC-11)
    """
    uid = request.user_id if request.user_id else request.session_id
    from Atlas.memory.neo4j_manager import neo4j_manager
    from Atlas.memory.predicate_catalog import get_catalog
    
    # 1. Policy Control
    mode = await neo4j_manager.get_user_memory_mode(uid)
    if mode == "OFF":
        raise HTTPException(
            status_code=403, 
            detail="Kişisel hafıza kapalıyken düzeltme yapılamaz. Lütfen önce hafıza modunu açın."
        )
    
    # 2. Predicate Validation
    catalog = get_catalog()
    if request.predicate.upper() not in catalog.by_key:
        raise HTTPException(
            status_code=400, 
            detail=f"Geçersiz bilgi tipi: {request.predicate}. Katalogda bulunamadı."
        )
    
    # 3. Apply Correction
    count = await neo4j_manager.correct_memory(
        uid, 
        request.target_type, 
        request.predicate, 
        request.new_value, 
        request.mode, 
        reason=request.reason,
        subject_id=request.subject_id,
        fact_id=request.fact_id
    )
    
    if count == 0 and request.mode == "retract":
        raise HTTPException(status_code=404, detail="Düzeltilecek uygun kayıt bulunamadı.")
    
    return {
        "success": True, 
        "updated_count": count,
        "message": f"Memory correction applied ({request.mode})."
    }

@app.post("/api/policy")
async def update_policy(request: PolicyUpdateRequest):
    """Kullanıcının bellek ve bildirim politikalarını günceller. (RC-2)"""
    uid = request.user_id if request.user_id else request.session_id
    from Atlas.memory.neo4j_manager import neo4j_manager
    
    # Sadece None olmayan alanları güncelle
    patch = {k: v for k, v in request.dict().items() if v is not None and k not in ["session_id", "user_id"]}
    
    new_settings = await neo4j_manager.set_user_settings(uid, patch)
    return {"success": True, "settings": new_settings}


@app.get("/api/arena/leaderboard")
async def get_arena_leaderboard():
    from Atlas.benchmark.store import arena_store
    results = arena_store.get_results()
    return {"results": results}

@app.post("/api/admin/purge_test_data")
async def purge_test_data(request: PurgeTestDataRequest):
    """
    Test verilerini temizler (SADECE DEBUG modunda).
    User, Session, Turn, Episode, Task ve Notification node'larını siler.
    Shared Entity node'larını simez.
    """
    from Atlas.config import DEBUG
    if not DEBUG:
        raise HTTPException(status_code=403, detail="Bu işlem sadece DEBUG modunda yapılabilir.")
    
    from Atlas.memory.neo4j_manager import neo4j_manager
    query = """
    MATCH (u:User) WHERE u.id STARTS WITH $prefix
    OPTIONAL MATCH (u)-[:HAS_SESSION|HAS_TASK|HAS_NOTIFICATION|HAS_ANCHOR]->(n)
    OPTIONAL MATCH (n)-[:HAS_TURN|HAS_EPISODE]->(m)
    DETACH DELETE u, n, m
    """
    try:
        await neo4j_manager.query_graph(query, {"prefix": request.user_id_prefix})
        return {"success": True, "message": f"Users starting with '{request.user_id_prefix}' purged."}
    except Exception as e:
        logger.error(f"Purge hatası: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/arena/questions")
async def get_arena_questions():
    from Atlas.benchmark.store import arena_store
    return arena_store.get_questions()


# Statik dosya ve kullanıcı arayüzü (UI) sunumu
UI_PATH = Path(__file__).parent / "ui"

@app.get("/arena", response_class=HTMLResponse)
async def arena():
    arena_path = UI_PATH / "arena.html"
    return FileResponse(arena_path) if arena_path.exists() else HTMLResponse("Arena UI not found")

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = UI_PATH / "index.html"
    return FileResponse(index_path) if index_path.exists() else HTMLResponse("Index UI not found")

if UI_PATH.exists():
    app.mount("/static", StaticFiles(directory=str(UI_PATH)), name="static")
    # Phase 1: Modular CSS/JS file serving
    css_path = UI_PATH / "css"
    js_path = UI_PATH / "js"
    if css_path.exists():
        app.mount("/css", StaticFiles(directory=str(css_path)), name="css")
    if js_path.exists():
        app.mount("/js", StaticFiles(directory=str(js_path)), name="js")


async def _maybe_trigger_episodic_memory(user_id: str, session_id: str):
    """
    Her 10 konuşma turunda bir PENDING episod oluşturur. (Kademeli Hafıza Optimizasyonu)
    """
    from Atlas.memory.neo4j_manager import neo4j_manager
    count = await neo4j_manager.count_turns(user_id, session_id)
    if count > 0 and count % 10 == 0:
        logger.info(f"TieredMemory: Episodic PENDING trigger for session {session_id} (count: {count})")
        # Son 10 mesajı kapsayan bir episode oluştur
        # 0-tabanlı index uyumu (Turn 0-9 için start=0, end=9)
        await neo4j_manager.create_episode_pending(
            user_id, session_id, 
            count-10, count-1
        )
