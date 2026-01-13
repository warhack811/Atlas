import abc
import logging
from typing import List, Type, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class JobConfig:
    """Job çalışma yapılandırması."""
    interval_minutes: Optional[int] = None
    interval_seconds: Optional[int] = None
    interval_hours: Optional[int] = None
    jitter: int = 10  # 1GB RAM kısıtı için çakışma önleyici
    is_leader_only: bool = True  # Sadece liderde mi çalışmalı?

class BaseJob(abc.ABC):
    """Tüm arka plan görevleri için temel sınıf."""
    name: str
    config: JobConfig

    @abc.abstractmethod
    async def run(self, *args, **kwargs):
        """Görevi icra eder."""
        pass

class TaskRegistry:
    """Sistemdeki tüm görevleri tutan ve yöneten kayıt defteri."""
    _jobs: List[Type[BaseJob]] = []

    @classmethod
    def register(cls, job_class: Type[BaseJob]):
        """Bir görevi kaydeder."""
        if job_class not in cls._jobs:
            cls._jobs.append(job_class)
            logger.debug(f"Task Registry: {job_class.__name__} kaydedildi.")
        return job_class

    @classmethod
    def get_all_jobs(cls) -> List[Type[BaseJob]]:
        """Kayıtlı tüm görev sınıflarını döner."""
        return cls._jobs

def register_job(cls):
    """Job sınıfları için decorator."""
    return TaskRegistry.register(cls)
