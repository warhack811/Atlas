from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging
from Atlas.memory.neo4j_manager import neo4j_manager
from Atlas.memory.text_normalize import normalize_text_for_dedupe

logger = logging.getLogger(__name__)

class ContextStrategy(ABC):
    @abstractmethod
    async def get_context(self, user_id: str, session_id: str, message: str, **kwargs) -> str:
        pass

class TemporalContextStrategy(ContextStrategy):
    """
    Extracts date ranges from the message and retrieves relevant facts from that period.
    """
    async def get_context(self, user_id: str, session_id: str, message: str, **kwargs) -> str:
        from Atlas.memory.context import extract_date_range

        date_range = extract_date_range(message)
        if not date_range:
            return ""

        start_dt, end_dt = date_range
        logger.info(f"Temporal Match: {start_dt} - {end_dt}")

        try:
            temporal_facts = await neo4j_manager.get_facts_by_date_range(user_id, start_dt, end_dt)
            if temporal_facts:
                context = f"\n[ZAMAN FİLTRESİ]: Kullanıcının belirttiği tarih aralığındaki ({start_dt.date()} - {end_dt.date()}) kayıtlar:\n"
                for f in temporal_facts[:10]:
                    context += f"- {f['subject']} {f['predicate']} {f['object']} (Tarih: {f.get('ts','')})\n"
                return context + "\n"
        except Exception as e:
            logger.error(f"Temporal strategy error: {e}")

        return ""

class EpisodicContextStrategy(ContextStrategy):
    """
    Retrieves relevant past episodes based on vector similarity.
    """
    async def get_context(self, user_id: str, session_id: str, message: str, **kwargs) -> str:
        budget = kwargs.get("budget", 1000)
        mode = kwargs.get("mode", "STANDARD")
        embedder = kwargs.get("embedder")
        all_context_texts = kwargs.get("dedupe_pool", [])

        if mode == "OFF" or budget <= 0 or not embedder:
            return ""

        query = """
        MATCH (u:User {id: $uid})-[:HAS_SESSION]->(s:Session)-[:HAS_EPISODE]->(e:Episode {status: "READY"})
        WHERE s.id <> $sid
        RETURN e.summary as summary, e.embedding as embedding, e.kind as kind,
               e.start_turn_index as start, e.end_turn_index as end, e.id as id
        LIMIT 10
        """
        try:
            results = await neo4j_manager.query_graph(query, {"uid": user_id, "sid": session_id})
            if not results:
                return ""

            scored_episodes = []
            query_emb = await embedder.embed(message)

            # Simple cosine similarity
            from Atlas.memory.context import calculate_cosine_similarity

            for res in results:
                score = 0.0
                if res.get("embedding"):
                    score = calculate_cosine_similarity(query_emb, res.get("embedding"))
                if res.get("kind") == "CONSOLIDATED":
                    score *= 1.1
                scored_episodes.append((score, res))

            scored_episodes.sort(key=lambda x: x[0], reverse=True)

            selected_ep_lines = []
            curr_ep_size = 0

            # Helper for dedupe
            from Atlas.memory.context import is_duplicate

            for score, ep in scored_episodes:
                line = f"- {ep['summary']} (Turn {ep.get('start', 0)}-{ep.get('end', 0)})"

                if is_duplicate(line, all_context_texts):
                    continue

                if curr_ep_size + len(line) + 1 <= budget:
                    selected_ep_lines.append(line)
                    curr_ep_size += len(line) + 1
                    all_context_texts.append(line)

            if selected_ep_lines:
                return "\n".join(selected_ep_lines)

        except Exception as e:
            logger.error(f"Episodic strategy error: {e}")

        return ""

class SemanticContextStrategy(ContextStrategy):
    """
    Retrieves semantic memory (Identity, Hard Facts, Soft Signals) V3 style.
    """
    async def get_context(self, user_id: str, session_id: str, message: str, **kwargs) -> str:
        from Atlas.memory.context import build_memory_context_v3
        stats = kwargs.get("stats")
        intent = kwargs.get("intent", "MIXED")
        trace = kwargs.get("trace")

        try:
            return await build_memory_context_v3(
                user_id,
                message,
                session_id=session_id,
                stats=stats,
                intent=intent,
                trace=trace
            )
        except Exception as e:
            logger.error(f"Semantic strategy error: {e}")
            return ""
