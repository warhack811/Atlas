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
from typing import Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger("api")

# Döngüsel içe aktarmayı (circular import) önlemek için burada tanımlanmıştır
from . import rdr

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
    session_id: Optional[str] = None
    use_mock: bool = False
    style: Optional[dict] = None
    mode: Optional[str] = "standard"


class ChatResponse(BaseModel):
    response: str
    session_id: str
    rdr: dict


async def keep_alive_pulse():
    """
    Neo4j Bağlantı Canlılığı (Heartbeat).
    Ücretsiz veritabanı oturumlarının (AuraDB) uykuya dalmasını önlemek için 
    düzenli aralıklarla (9 dakika) hafif bir sorgu gönderir.
    """
    from .memory.neo4j_manager import neo4j_manager
    while True:
        try:
            await asyncio.sleep(540) # 9 dakikalık bekleme süresi
            await neo4j_manager.query_graph("RETURN 1 AS heartbeat")
            logger.info("Neo4j Kalp Atışı Sinyali gönderildi.")
        except Exception as e:
            logger.error(f"Kalp atışı başarısız: {e}")


@app.on_event("startup")
async def startup_event():
    """Uygulama başladığında çalışacak görevler."""
    from .scheduler import start_scheduler
    start_scheduler()
    
    # Arka plan görevlerini ve veritabanı canlılık sinyalini başlat
    asyncio.create_task(keep_alive_pulse())


@app.on_event("shutdown")
async def shutdown_event():
    """Uygulama kapandığında çalışacak görevler."""
    from .scheduler import stop_scheduler
    stop_scheduler()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """Standart blok yanıt üreten ana sohbet endpoint'i."""
    from .memory import SessionManager, MessageBuffer
    
    start_time = time.time()
    
    # 0. GÜVENLİK DENETİMİ: Girdide zararlı içerik veya hassas veri (PII) kontrolü
    from .safety import safety_gate
    is_safe, sanitized_text, issues = await safety_gate.check_input_safety(request.message)
    safety_ms = int((time.time() - start_time) * 1000)
    
    if not is_safe:
        record = rdr.RDR.create(request.message)
        record.safety_passed = False
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
        session = SessionManager.get_or_create(request.session_id)
        session_id = session.id
        MessageBuffer.add_user_message(session_id, user_message)
        
        # GRAF VERİTABANI BAĞLAMI: Kullanıcı geçmişini ve ilişkili bilgileri Neo4j'den getirir
        from .memory.context import ContextBuilder
        cb = ContextBuilder(session_id)
        neo4j_context = await cb.get_neo4j_context(session_id, user_message)
        cb.with_neo4j_context(neo4j_context)
        
        record = rdr.RDR.create(user_message)
        
        # 1. PLANLAMA (ORKESTRASYON): Kullanıcı niyetini anlar ve bir iş planı oluşturur
        from . import orchestrator
        classify_start = time.time()
        plan = await orchestrator.orchestrator.plan(
            session_id, 
            user_message, 
            use_mock=request.use_mock,
            context_builder=cb
        )
            
        classify_ms = int((time.time() - classify_start) * 1000)
        record.intent = plan.active_intent
        record.classification_ms = classify_ms
        record.safety_ms = safety_ms

        from .time_context import time_context
        
        record.time_context = time_context.get_context_injection()
        record.rewritten_query = plan.rewritten_query if plan.rewritten_query else user_message
        record.user_facts_dump = []  # Artık Neo4j graf belleği kullanılıyor
        record.full_context_injection = time_context.inject_time_context("", user_message) 
        record.orchestrator_prompt = plan.orchestrator_prompt
        
        # 2. YÜRÜTME (EXECUTION): Planlanan görevleri (araç kullanımı, LLM çağrıları) çalıştırır
        from . import dag_executor
        exec_start = time.time()
        raw_results = await dag_executor.dag_executor.execute_plan(plan, session_id, user_message)
        exec_ms = int((time.time() - exec_start) * 1000)
        
        # 3. HARMANLAMA (SENTEZ): Uzmanlardan gelen ham çıktıları tutarlı bir yanıta dönüştürür
        from . import synthesizer
        synth_start = time.time()
        response_text, synth_model, synth_prompt, synth_metadata = await synthesizer.synthesizer.synthesize(
            raw_results, session_id, plan.active_intent, user_message, mode=request.mode
        )
        synth_ms = int((time.time() - synth_start) * 1000)
        
        record.synthesizer_model = synth_model
        record.synthesizer_prompt = synth_prompt
        record.style_used = True
        record.style_persona = synth_metadata.get("persona", "")
        record.style_preset = synth_metadata.get("mode", "")
            
        # 4. KALİTE DENETİMİ: Oluşturulan yanıtın dil ve format kurallarına uygunluğunu ölçer
        from .quality import quality_gate
        quality_start = time.time()
        is_passed, issues = quality_gate.check_quality(response_text, plan.active_intent)
        quality_ms = int((time.time() - quality_start) * 1000)
        
        record.quality_passed = is_passed
        from dataclasses import asdict
        record.quality_issues = [asdict(i) for i in issues]
        
        MessageBuffer.add_assistant_message(session_id, response_text)
        
        record.dag_execution_ms = exec_ms
        record.synthesis_ms = synth_ms
        record.quality_ms = quality_ms
        record.total_ms = int((time.time() - start_time) * 1000)
        record.generation_ms = record.total_ms # Geriye dönük uyumluluk için
        record.safety_passed = safety_info["passed"]
        record.safety_issues = safety_info["issues"]
        record.pii_redacted = safety_info["pii_redacted"]
        
        rdr.save_rdr(record)
        
        # Arka planda bilgi çıkarımı yaparak graf veritabanını günceller
        from .memory.extractor import extract_and_save as extract_and_save_task
        background_tasks.add_task(extract_and_save_task, user_message, session_id)

        return ChatResponse(
            response=response_text,
            session_id=session_id,
            rdr=record.to_dict()
        )
    except Exception as e:
        logger.error(f"Sohbet hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, background_tasks: BackgroundTasks):
    """SSE (Server-Sent Events) kullanarak akış formatında yanıt üretir."""
    from .memory import SessionManager, MessageBuffer
    from . import orchestrator, dag_executor, synthesizer

    async def event_generator():
        """Süreç adımlarını ve metin parçalarını ileten jeneratör."""
        start_time = time.time()
        session = SessionManager.get_or_create(request.session_id)
        session_id = session.id
        MessageBuffer.add_user_message(session_id, request.message)

        from . import rdr, safety
        record = rdr.RDR.create(request.message)

        try:
            safety_start = time.time()
            is_safe, sanitized_text, issues = await safety.safety_gate.check_input_safety(request.message)
            safety_ms = int((time.time() - safety_start) * 1000)
            
            record.safety_passed = is_safe
            record.safety_ms = safety_ms
            record.safety_issues = [{"type": i.type, "details": i.details} for i in issues]
            record.pii_redacted = any(i.type == "PII" for i in issues)

            if not is_safe:
                yield f"data: {json.dumps({'type': 'error', 'content': '[GÜVENLİK ENGELİ] Güvenlik engeli.'})}\n\n"
                return

            classify_start = time.time()
            plan = await orchestrator.orchestrator.plan(session_id, request.message, use_mock=request.use_mock)
            classify_ms = int((time.time() - classify_start) * 1000)
            
            record.intent = plan.active_intent
            record.classification_ms = classify_ms
            record.orchestrator_prompt = plan.orchestrator_prompt
            yield f"data: {json.dumps({'type': 'plan', 'intent': plan.active_intent})}\n\n"

            exec_start = time.time()
            raw_results = await dag_executor.dag_executor.execute_plan(plan, session_id, request.message)
            exec_ms = int((time.time() - exec_start) * 1000)
            
            record.dag_execution_ms = exec_ms
            record.task_details = [
                {"id": r.get("task_id") or r.get("id"), "model": r.get("model"), "status": "success", "result": r.get("output") or r.get("response"), "duration_ms": r.get("duration_ms", 0)}
                for r in raw_results
            ]
            yield f"data: {json.dumps({'type': 'tasks_done'})}\n\n"

            full_response = ""
            synth_start = time.time()
            async for data in synthesizer.synthesizer.synthesize_stream(
                raw_results, session_id, plan.active_intent, request.message, mode=request.mode
            ):
                if data["type"] == "metadata":
                    record.synthesizer_model = data["model"]
                    record.synthesizer_prompt = data["prompt"]
                    record.style_persona = data["persona"]
                    record.style_preset = data["mode"]
                elif data["type"] == "chunk":
                    chunk = data["content"]
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            
            synth_ms = int((time.time() - synth_start) * 1000)
            record.synthesis_ms = synth_ms

            MessageBuffer.add_assistant_message(session_id, full_response)
            record.total_ms = int((time.time() - start_time) * 1000)
            record.generation_ms = record.total_ms
            record.response_length = len(full_response)
            
            from .memory.extractor import extract_and_save as extract_and_save_task
            background_tasks.add_task(extract_and_save_task, request.message, session_id)

            rdr.save_rdr(record)
            yield f"data: {json.dumps({'type': 'done', 'rdr': record.to_dict()})}\n\n"

        except Exception as e:
            logger.error(f"Akış hatası: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

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
    from .vision_engine import analyze_image
    from .safety import safety_gate
    from .memory import MessageBuffer, SessionManager
    
    try:
        session = SessionManager.get_or_create(session_id)
        session_id = session.id
        content = await file.read()
        analysis_text = await analyze_image(content)
        is_safe, sanitized_text, issues = await safety_gate.check_input_safety(analysis_text)
        
        # Analiz sonucunu sistem notu olarak mesaj geçmişine enjekte et
        system_note = f"[BAĞLAM - GÖRSEL ANALİZİ ({file.filename})]: {sanitized_text}"
        MessageBuffer.add_user_message(session_id, system_note)
        
        return {
            "status": "success",
            "filename": file.filename,
            "analysis": sanitized_text,
            "safety_passed": is_safe
        }
    except Exception as e:
        logger.error(f"Yükleme hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    """Sistem sağlığı ve API anahtarı durumlarını döndürür."""
    from .key_manager import KeyManager
    return {
        "status": "ok",
        "available_keys": KeyManager.get_available_count(),
        "key_stats": KeyManager.get_stats()
    }


@app.get("/api/arena/leaderboard")
async def get_arena_leaderboard():
    from .benchmark.store import arena_store
    results = arena_store.get_results()
    return {"results": results}


@app.get("/api/arena/questions")
async def get_arena_questions():
    from .benchmark.store import arena_store
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
