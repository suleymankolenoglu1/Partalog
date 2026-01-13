"""
Vector Store - ChromaDB ile vektör veritabanı
Parça embedding'lerini saklar ve benzerlik araması yapar.
"""

import chromadb
from chromadb.config import Settings
import numpy as np
from typing import List, Dict, Optional, Any
from loguru import logger


class VectorStore: 
    """
    ChromaDB tabanlı vektör veritabanı. 
    Parça embedding'lerini saklar ve görsel arama için kullanılır.
    """
    
    def __init__(
        self,
        persist_directory: str,
        collection_name: str = "part_embeddings"
    ):
        """
        Args: 
            persist_directory: Veritabanı dizini
            collection_name: Koleksiyon adı
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        
        logger.info(f"Vector Store başlatılıyor (dir={persist_directory})")
        
        # ChromaDB client oluştur
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Koleksiyon al veya oluştur
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Parça görselleri embedding'leri"}
        )
        
        logger.info(f"Vector Store hazır (koleksiyon:  {collection_name}, kayıt:  {self.collection.count()})")
    
    def add(
        self,
        id: str,
        embedding: np.ndarray,
        metadata: Dict[str, Any] = None
    ) -> None:
        """
        Tek bir embedding ekle.
        
        Args:
            id: Benzersiz ID (part_id)
            embedding: Embedding vektörü
            metadata: Ek bilgiler (part_number, catalog_id vs.)
        """
        self.collection.add(
            ids=[id],
            embeddings=[embedding. tolist()],
            metadatas=[metadata] if metadata else None
        )
        logger.debug(f"Eklendi: {id}")
    
    def add_batch(
        self,
        ids: List[str],
        embeddings:  np.ndarray,
        metadatas: List[Dict[str, Any]] = None
    ) -> None:
        """
        Toplu embedding ekle.
        
        Args: 
            ids: ID listesi
            embeddings: Embedding matrisi (N x dim)
            metadatas: Metadata listesi
        """
        self.collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            metadatas=metadatas
        )
        logger.debug(f"Toplu eklendi:  {len(ids)} kayıt")
    
    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        where: Dict = None
    ) -> List[Dict]: 
        """
        Benzerlik araması yap.
        
        Args:
            query_embedding:  Sorgu embedding'i
            top_k: Döndürülecek sonuç sayısı
            where: Filtreleme koşulları
        
        Returns:
            Eşleşen sonuçlar listesi
        """
        results = self.collection. query(
            query_embeddings=[query_embedding. tolist()],
            n_results=top_k,
            where=where,
            include=["metadatas", "distances"]
        )
        
        # Sonuçları formatla
        matches = []
        
        if results and results['ids'] and len(results['ids'][0]) > 0:
            for i, (id_, distance) in enumerate(zip(
                results['ids'][0],
                results['distances'][0]
            )):
                # Distance -> Similarity (ChromaDB L2 distance kullanıyor)
                # L2 distance:  0 = aynı, 2 = tam zıt (normalized vektörler için)
                # Similarity = 1 - (distance / 2)
                similarity = 1 - (distance / 2)
                
                metadata = {}
                if results['metadatas'] and len(results['metadatas'][0]) > i:
                    metadata = results['metadatas'][0][i] or {}
                
                matches.append({
                    "id":  id_,
                    "similarity": round(similarity, 4),
                    "distance": round(distance, 4),
                    "metadata":  metadata
                })
        
        return matches
    
    def get(self, id: str) -> Optional[Dict]:
        """
        ID ile kayıt getir.
        
        Args:
            id: Kayıt ID'si
        
        Returns:
            Kayıt veya None
        """
        result = self.collection. get(
            ids=[id],
            include=["embeddings", "metadatas"]
        )
        
        if result and result['ids']:
            return {
                "id":  result['ids'][0],
                "embedding":  result['embeddings'][0] if result['embeddings'] else None,
                "metadata": result['metadatas'][0] if result['metadatas'] else None
            }
        
        return None
    
    def delete(self, id: str) -> None:
        """Kayıt sil."""
        self. collection.delete(ids=[id])
        logger.debug(f"Silindi: {id}")
    
    def delete_batch(self, ids: List[str]) -> None:
        """Toplu silme."""
        self.collection. delete(ids=ids)
        logger.debug(f"Toplu silindi:  {len(ids)} kayıt")
    
    def update(
        self,
        id: str,
        embedding: np. ndarray = None,
        metadata: Dict[str, Any] = None
    ) -> None:
        """Kayıt güncelle."""
        update_data = {"ids": [id]}
        
        if embedding is not None: 
            update_data["embeddings"] = [embedding.tolist()]
        
        if metadata is not None:
            update_data["metadatas"] = [metadata]
        
        self.collection. update(**update_data)
        logger.debug(f"Güncellendi: {id}")
    
    def count(self) -> int:
        """Toplam kayıt sayısı."""
        return self.collection. count()
    
    def get_stats(self) -> Dict: 
        """Veritabanı istatistikleri."""
        return {
            "collection_name": self.collection_name,
            "total_records": self.collection.count(),
            "persist_directory": self. persist_directory
        }
    
    def clear(self) -> None:
        """Tüm kayıtları sil."""
        # Koleksiyonu sil ve yeniden oluştur
        self. client.delete_collection(self.collection_name)
        self.collection = self.client. get_or_create_collection(
            name=self.collection_name,
            metadata={"description":  "Parça görselleri embedding'leri"}
        )
        logger.info("Vector Store temizlendi")