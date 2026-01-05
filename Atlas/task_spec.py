"""
ATLAS Yönlendirici - Görev Spesifikasyonu (Task Specification)
--------------------------------------------------------------
Bu bileşen, karmaşık kullanıcı taleplerinin asenkron olarak yürütülecek
küçük görev parçalarına (tasks) bölünmesini ve bu görevler arasındaki
bağımlılıkları tanımlar.

Temel Sorumluluklar:
1. Görev Modelleme: Her bir görevin niyetini, girdisini ve kısıtlamalarını tanımlama.
2. Yürütme Planı (DAG): Görevlerin paralel veya ardışık çalışacağı grafik yapısını oluşturma.
3. Durum Takibi: Görevlerin anlık çalışma durumunu (pending, running, failed vb.) yönetme.
4. Özet Raporlama: Planın tamamlanma oranını ve başarı istatistiklerini hesaplama.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime


class TaskStatus(str, Enum):
    """Görev durumları."""
    PENDING = "pending"       # Beklemede
    RUNNING = "running"       # Çalışıyor
    COMPLETED = "completed"   # Tamamlandı
    FAILED = "failed"         # Başarısız
    SKIPPED = "skipped"       # Atlandı (bağımlılık başarısız)
    TIMEOUT = "timeout"       # Zaman aşımı


class Task(BaseModel):
    """Tek bir görev tanımı."""
    id: str = Field(..., description="Benzersiz görev ID'si")
    intent: str = Field(..., description="Görev niyeti (coding, research, summarize, vb.)")
    input: str = Field(..., description="Görev girdisi / kullanıcı talebi")
    expected_output: Optional[str] = Field(None, description="Beklenen çıktı türü")
    constraints: Dict[str, Any] = Field(default_factory=dict, description="Kısıtlamalar (ton, uzunluk, vb.)")
    depends_on: List[str] = Field(default_factory=list, description="Bağımlı olduğu görev ID'leri")
    tool_needs: List[str] = Field(default_factory=list, description="Gerekli araçlar")
    priority: int = Field(default=1, description="Öncelik (1=en yüksek)")
    timeout_seconds: int = Field(default=30, description="Zaman aşımı (saniye)")
    
    # Çalışma zamanı bilgileri
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Görev durumu")
    result: Optional[str] = Field(None, description="Görev sonucu")
    error: Optional[str] = Field(None, description="Hata mesajı")
    started_at: Optional[datetime] = Field(None, description="Başlangıç zamanı")
    completed_at: Optional[datetime] = Field(None, description="Bitiş zamanı")
    tokens_used: int = Field(default=0, description="Kullanılan token sayısı")
    model_used: Optional[str] = Field(None, description="Kullanılan model")


class ExecutionPlan(BaseModel):
    """Yürütme planı."""
    parallel_groups: List[List[str]] = Field(
        default_factory=list, 
        description="Paralel çalışacak görev grupları sırasıyla"
    )
    timeouts: Dict[str, int] = Field(
        default_factory=dict, 
        description="Görev bazlı zaman aşımı (saniye)"
    )
    budgets: Dict[str, int] = Field(
        default_factory=dict, 
        description="Bütçe limitleri (tokens, vb.)"
    )


class AnswerPlan(BaseModel):
    """Cevap formatı planı."""
    format: str = Field(default="prose", description="Çıktı formatı (prose, numbered_list, markdown)")
    sections: List[str] = Field(default_factory=list, description="Bölümler")
    merge_strategy: str = Field(default="sequential", description="Birleştirme stratejisi")


class TaskSpec(BaseModel):
    """
    Tam görev spesifikasyonu.
    Intent Classifier'ın çıktısı, DAG Executor'ın girdisi.
    """
    tasks: List[Task] = Field(..., description="Görev listesi")
    execution_plan: ExecutionPlan = Field(default_factory=ExecutionPlan, description="Yürütme planı")
    answer_plan: AnswerPlan = Field(default_factory=AnswerPlan, description="Cevap planı")
    
    # Meta bilgiler
    original_message: str = Field(default="", description="Orijinal kullanıcı mesajı")
    created_at: datetime = Field(default_factory=datetime.now, description="Oluşturma zamanı")
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """ID ile görev al."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None
    
    def get_completed_count(self) -> int:
        """Tamamlanan görev sayısı."""
        return sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
    
    def get_failed_count(self) -> int:
        """Başarısız görev sayısı."""
        return sum(1 for t in self.tasks if t.status in [TaskStatus.FAILED, TaskStatus.TIMEOUT])
    
    def is_complete(self) -> bool:
        """Tüm görevler tamamlandı mı?"""
        return all(t.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED, TaskStatus.TIMEOUT] 
                   for t in self.tasks)
    
    def get_summary(self) -> Dict[str, Any]:
        """Özet istatistikler."""
        return {
            "total": len(self.tasks),
            "completed": self.get_completed_count(),
            "failed": self.get_failed_count(),
            "pending": sum(1 for t in self.tasks if t.status == TaskStatus.PENDING),
            "skipped": sum(1 for t in self.tasks if t.status == TaskStatus.SKIPPED)
        }


class TaskSpecBuilder:
    """TaskSpec oluşturucu (basit mesajlar için)."""
    
    @staticmethod
    def from_single_intent(
        message: str, 
        intent: str, 
        timeout: int = 30
    ) -> TaskSpec:
        """Tek bir niyet içeren basit mesajlar için hızlıca TaskSpec oluşturur."""
        task = Task(
            id="task_1",
            intent=intent,
            input=message,
            timeout_seconds=timeout
        )
        return TaskSpec(
            tasks=[task],
            original_message=message,
            execution_plan=ExecutionPlan(parallel_groups=[["task_1"]])
        )
    
    @staticmethod
    def from_multi_intent(
        message: str,
        intents: List[Dict[str, Any]]
    ) -> TaskSpec:
        """
        Çoklu niyetli mesaj için TaskSpec oluştur.
        
        Args:
            message: Orijinal mesaj
            intents: [{"intent": "coding", "input": "...", "depends_on": []}, ...]
        """
        tasks = []
        for i, intent_data in enumerate(intents):
            task = Task(
                id=f"task_{i+1}",
                intent=intent_data.get("intent", "general"),
                input=intent_data.get("input", message),
                depends_on=intent_data.get("depends_on", []),
                timeout_seconds=intent_data.get("timeout", 30)
            )
            tasks.append(task)
        
        # Bağımlılıklara göre paralel grupları oluştur
        # (DAG Executor'da topological sort yapılacak)
        return TaskSpec(
            tasks=tasks,
            original_message=message
        )
