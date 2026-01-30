import json
import re

def summarize_tool_output(tool_name: str, raw_output: str, max_chars: int = 500) -> str:
    """
    Tool çıktısını özetleyerek token tasarrufu sağlar.
    """
    if len(raw_output) < max_chars:
        return raw_output

    try:
        data = json.loads(raw_output)
        if isinstance(data, list):
            # Liste ise sadece ilk 3 öğeyi al
            return json.dumps(data[:3], ensure_ascii=False)
        elif isinstance(data, dict):
            # Dict ise sadece önemli anahtarları al (basit bir heuristik)
            priority_keys = ["title", "snippet", "link", "content", "summary"]
            filtered = {k: v for k, v in data.items() if k in priority_keys}
            return json.dumps(filtered, ensure_ascii=False)
    except:
        pass

    # JSON değilse regex ile temizle veya kırp
    return raw_output[:max_chars] + "..."
