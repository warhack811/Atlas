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
from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger("api")

# Döngüsel içe aktarmayı (circular import) önlemek için burada tanımlanmıştır
from Atlas import rdr

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
    from Atlas.memory.neo4j_manager import neo4j_manager
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
    from Atlas.scheduler import start_scheduler
    await start_scheduler()
    
    # Arka plan görevlerini ve veritabanı canlılık sinyalini başlat
    asyncio.create_task(keep_alive_pulse())


@app.on_event("shutdown")
async def shutdown_event():
    """Uygulama kapandığında çalışacak görevler."""
    from Atlas.scheduler import stop_scheduler
    stop_scheduler()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """Standart blok yanıt üreten ana sohbet endpoint'i."""
    from Atlas.memory import SessionManager, MessageBuffer
    import Atlas.orchestrator as orchestrator
    import Atlas.dag_executor as dag_executor
    import Atlas.synthesizer as synthesizer
    
    start_time = time.time()
    
    # 0. GÜVENLİK DENETİMİ: Girdide zararlı içerik veya hassas veri (PII) kontrolü
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
        session = SessionManager.get_or_create(request.session_id)
        session_id = session.id
        MessageBuffer.add_user_message(session_id, user_message)
        
        # GRAF VERİTABANI BAĞLAMI: FAZ6 - v3 context packaging
        from Atlas.memory.context import ContextBuilder, build_memory_context_v3
        cb = ContextBuilder(session_id)
        
        # FAZ6: Yeni v3 context packaging kullan
        neo4j_context = await build_memory_context_v3(session_id, user_message)
        cb.with_neo4j_context(neo4j_context)
        
        record = rdr.RDR.create(user_message)
        if neo4j_context:
            record.full_context_injection = f"[MEMORY V3]: {neo4j_context}"
        
        # 1. PLANLAMA (ORKESTRASYON): Kullanıcı niyetini anlar ve bir iş planı oluşturur
        from Atlas import orchestrator
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
        raw_results = await dag_executor.dag_executor.execute_plan(plan, session_id, user_message)
        exec_ms = int((time.time() - exec_start) * 1000)
        
        # 3. HARMANLAMA (SENTEZ): Uzmanlardan gelen ham çıktıları tutarlı bir yanıta dönüştürür
        from Atlas import synthesizer
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
        from Atlas.quality import quality_gate
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
        record.safety_model = used_model
        record.safety_issues = safety_info["issues"]
        record.pii_redacted = safety_info["pii_redacted"]
        
        rdr.save_rdr(record)
        
        # Arka planda bilgi çıkarımı yaparak graf veritabanını günceller
        # FAZ2: source_turn_id (request_id) iz sürme için extractor'a gönderiliyor
        from Atlas.memory.extractor import extract_and_save as extract_and_save_task
        background_tasks.add_task(extract_and_save_task, user_message, session_id, record.request_id)

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
    from Atlas.memory import SessionManager, MessageBuffer
    from Atlas import orchestrator, dag_executor, synthesizer

    async def event_generator():
        """Süreç adımlarını ve metin parçalarını ileten jeneratör."""
        from Atlas import rdr, safety
        record = rdr.RDR.create(request.message)

        try:
            start_time = time.time()
            from Atlas.memory import SessionManager, MessageBuffer
            from Atlas import orchestrator, dag_executor, synthesizer
            
            session = SessionManager.get_or_create(request.session_id)
            session_id = session.id
            MessageBuffer.add_user_message(session_id, request.message)

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
            # 1. Bellek ve Bağlam Hazırlığı - FAZ6: v3 context packaging
            from Atlas.memory.context import ContextBuilder, build_memory_context_v3
            cb = ContextBuilder(session_id)
            
            # FAZ6: Yeni v3 context packaging kullan
            graph_context = await build_memory_context_v3(session_id, request.message)
            cb.with_neo4j_context(graph_context)
            
            # 2. Orkestrasyon: Niyet analizi ve DAG planı oluşturma
            plan = await orchestrator.orchestrator.plan(session_id, request.message, use_mock=request.use_mock, context_builder=cb)
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
            
            if graph_context:
                record.full_context_injection = f"[NEO4J MEMORY]: {graph_context}"
            
            yield f"data: {json.dumps({'type': 'plan', 'intent': plan.active_intent, 'model': plan.orchestrator_model}, default=str)}\n\n"

            exec_start = time.time()
            raw_results = []
            async for event in dag_executor.dag_executor.execute_plan_stream(plan, session_id, request.message):
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
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, default=str)}\n\n"
            
            synth_ms = int((time.time() - synth_start) * 1000)
            record.synthesis_ms = synth_ms

            MessageBuffer.add_assistant_message(session_id, full_response)
            record.total_ms = int((time.time() - start_time) * 1000)
            record.generation_ms = record.total_ms
            # Arka planda bilgi çıkarımı yaparak graf veritabanını günceller
            # FAZ2: source_turn_id (request_id) iz sürme için extractor'a gönderiliyor
            from Atlas.memory.extractor import extract_and_save as extract_and_save_task
            background_tasks.add_task(extract_and_save_task, request.message, session_id, record.request_id)

            rdr.save_rdr(record)
            yield f"data: {json.dumps({'type': 'done', 'rdr': record.to_dict()}, default=str)}\n\n"

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
    """Sistem sağlığı ve API anahtarı durumlarını döndürür."""
    from Atlas.key_manager import KeyManager
    return {
        "status": "ok",
        "available_keys": KeyManager.get_available_count(),
        "key_stats": KeyManager.get_stats()
    }


@app.get("/api/arena/leaderboard")
async def get_arena_leaderboard():
    from Atlas.benchmark.store import arena_store
    results = arena_store.get_results()
    return {"results": results}


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
