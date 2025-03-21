from dataclasses import dataclass
from typing import List, Optional

@dataclass
class KnowledgeBaseConfig:
    """Konfiguracja dla Knowledge Base"""
    index_name: str = "iot-knowledge"
    embedding_dimension: int = 1536  # dla modeli Bedrock
    vector_field_name: str = "content_vector"
    metadata_fields: List[str] = ("device_id", "timestamp", "sensor_type")

    # Konfiguracja wyszukiwania
    search_size: int = 10
    min_score: float = 0.7

    # Konfiguracja indeksu
    index_settings = {
        "index": {
            "knn": True,
            "knn.space_type": "cosinesimil"
        }
    }

    # Mapowanie pól
    index_mapping = {
        "properties": {
            "content": {"type": "text"},
            "content_vector": {
                "type": "knn_vector",
                "dimension": embedding_dimension,
            },
            "device_id": {"type": "keyword"},
            "timestamp": {"type": "date"},
            "sensor_type": {"type": "keyword"}
        }
    }