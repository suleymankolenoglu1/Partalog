import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

// 🔥 GÜNCELLENDİ: Backend (ChatController) Response Yapısı
// PublicViewComponent'te kullandığımız 'res.replySuggestion' ve 'res.products' ile eşleşmeli.
export interface AiChatResponse {
  replySuggestion: string; // AI'nın metin cevabı
  products: any[];         // Bulunan parçalar listesi
  debugInfo?: string;      // Varsa debug bilgisi (hangi tool kullanıldı vs.)
}

@Injectable({
  providedIn: 'root'
})
export class AiService {
  private http = inject(HttpClient);
  
  // ⚠️ NOT: Port numarasını CatalogService ile aynı (HTTPS) yaptım.
  // Eğer HTTP kullanıyorsan 'http://localhost:5159/api/chat/ask' yapabilirsin.
  private apiUrl = 'http://localhost:5159/api/chat/ask'; 

  /**
   * AI'ya mesaj, resim ve sohbet geçmişini gönderir.
   * @param text Kullanıcı mesajı
   * @param image Seçilen resim (opsiyonel)
   * @param history Önceki konuşmalar (bağlam için)
   * @param userId Public view kullanıcı kimliği
   */
  sendMessage(text: string, image: File | null, history: any[] = [], userId?: string): Observable<AiChatResponse> {
    const formData = new FormData();
    
    // 1. Metin (Varsa)
    if (text) formData.append('text', text);
    
    // 2. Resim (Varsa)
    if (image) formData.append('image', image);
    
    // 3. Sohbet Geçmişi (JSON String olarak gönderiyoruz)
    // Backend tarafında [FromForm] string history olarak karşılanıp deserialize edilecek.
    formData.append('history', JSON.stringify(history));

    // ✅ userId ekle
    if (userId) formData.append('userId', userId);

    return this.http.post<AiChatResponse>(this.apiUrl, formData);
  }
}