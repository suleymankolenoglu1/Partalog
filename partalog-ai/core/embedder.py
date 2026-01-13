"""
Image Embedder - CLIP ile görsel embedding çıkarma
Parça görsellerini vektöre dönüştürür (görsel arama için).
"""

import open_clip
import torch
import numpy as np
import cv2
from PIL import Image
from typing import List, Union, Tuple
from loguru import logger


class ImageEmbedder: 
    """
    CLIP tabanlı görsel embedding çıkarıcı. 
    Görüntüleri 512 boyutlu vektörlere dönüştürür.
    """
    
    def __init__(
        self,
        model_name: str = "ViT-B-32",
        pretrained: str = "openai"
    ):
        """
        Args:
            model_name: CLIP model adı
            pretrained:  Önceden eğitilmiş ağırlıklar
        """
        self.model_name = model_name
        self.pretrained = pretrained
        
        # Cihaz seçimi
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"CLIP Embedder başlatılıyor (model={model_name}, device={self.device})")
        
        # Modeli yükle
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name,
            pretrained=pretrained
        )
        self.model = self.model.to(self.device)
        self.model.eval()
        
        # Embedding boyutu
        self. embedding_dim = self.model. visual.output_dim
        logger.info(f"CLIP Embedder hazır (embedding_dim={self.embedding_dim})")
    
    def embed_image(self, image: Union[np.ndarray, Image.Image]) -> np.ndarray:
        """
        Tek bir görüntüden embedding çıkar.
        
        Args:
            image: OpenCV (BGR) veya PIL Image
        
        Returns: 
            Normalize edilmiş embedding vektörü (512 boyut)
        """
        # PIL Image'a çevir
        if isinstance(image, np.ndarray):
            # OpenCV BGR -> RGB -> PIL
            if len(image.shape) == 3 and image.shape[2] == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image
            pil_image = Image.fromarray(image_rgb)
        else:
            pil_image = image
        
        # Preprocess
        image_input = self.preprocess(pil_image).unsqueeze(0).to(self.device)
        
        # Embedding çıkar
        with torch.no_grad():
            embedding = self.model. encode_image(image_input)
            
            # Normalize et
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
            
            # NumPy'a çevir
            embedding = embedding.cpu().numpy().flatten()
        
        return embedding
    
    def embed_image_from_bytes(self, image_bytes: bytes) -> np.ndarray:
        """
        Byte array'den embedding çıkar. 
        
        Args:
            image_bytes: Görüntü byte'ları
        
        Returns:
            Embedding vektörü
        """
        # Byte'lardan görüntü oluştur
        nparr = np. frombuffer(image_bytes, np. uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None: 
            raise ValueError("Görüntü okunamadı")
        
        return self.embed_image(image)
    
    def embed_images_batch(
        self,
        images: List[Union[np.ndarray, Image.Image]],
        batch_size: int = 32
    ) -> np.ndarray:
        """
        Birden fazla görüntüden embedding çıkar (batch işleme).
        
        Args: 
            images: Görüntü listesi
            batch_size: Batch boyutu
        
        Returns:
            Embedding matrisi (N x embedding_dim)
        """
        all_embeddings = []
        
        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            
            # PIL'e çevir ve preprocess
            batch_tensors = []
            for img in batch:
                if isinstance(img, np.ndarray):
                    if len(img.shape) == 3 and img.shape[2] == 3:
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    else:
                        img_rgb = img
                    pil_img = Image.fromarray(img_rgb)
                else: 
                    pil_img = img
                
                tensor = self.preprocess(pil_img)
                batch_tensors.append(tensor)
            
            # Stack ve GPU'ya gönder
            batch_input = torch.stack(batch_tensors).to(self.device)
            
            # Embedding çıkar
            with torch.no_grad():
                embeddings = self.model.encode_image(batch_input)
                embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
                embeddings = embeddings. cpu().numpy()
            
            all_embeddings.append(embeddings)
        
        return np.vstack(all_embeddings)
    
    def compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        İki embedding arasındaki benzerliği hesapla (cosine similarity).
        
        Args: 
            embedding1: İlk embedding
            embedding2: İkinci embedding
        
        Returns:
            Benzerlik skoru (0-1)
        """
        # Cosine similarity
        similarity = np.dot(embedding1, embedding2)
        return float(similarity)
    
    def find_similar(
        self,
        query_embedding: np. ndarray,
        embeddings: np.ndarray,
        top_k:  int = 5
    ) -> List[Tuple[int, float]]: 
        """
        En benzer embedding'leri bul.
        
        Args:
            query_embedding: Sorgu embedding'i
            embeddings: Aranacak embedding matrisi
            top_k: Döndürülecek sonuç sayısı
        
        Returns:
            (index, similarity) tuple listesi
        """
        # Tüm benzerlikları hesapla
        similarities = np.dot(embeddings, query_embedding)
        
        # En yüksek k tanesini bul
        top_indices = np. argsort(similarities)[::-1][:top_k]
        
        results = [
            (int(idx), float(similarities[idx]))
            for idx in top_indices
        ]
        
        return results
    
    def get_info(self) -> dict:
        """Embedder bilgilerini döndür."""
        return {
            "model_name": self. model_name,
            "pretrained": self.pretrained,
            "device": self.device,
            "embedding_dim": self.embedding_dim
        }