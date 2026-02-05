import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CatalogService, Catalog } from '../core/services/catalog.service';
import { CartService } from '../core/services/cart.service';
import { AiService } from '../core/services/ai.service'; 

// 🔥 Yanıt Tipi Tanımı (HTML ile uyumlu olması için)
interface AiResponse {
  replySuggestion: string; // Eskiden 'text' idi
  products: any[];         // Eskiden 'suggestedParts' idi
  debugInfo?: string;      // Yeni eklendi
}

@Component({
  selector: 'app-public-view',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './public-view.html',
  styleUrls: ['./public-view.css']
})
export class PublicViewComponent implements OnInit {
  private catalogService = inject(CatalogService);
  public cartService = inject(CartService); 
  private aiService = inject(AiService);
  private router = inject(Router);

  // --- UI Durum Yönetimi ---
  searchText: string = '';
  isLoading = true;
  isCartOpen = false;
  isSubmitting = false;

  // 🔥 AI Asistan Durumu (HTML'deki yapıyla %100 uyumlu)
  aiState = {
    isActive: false, 
    isLoading: false, 
    response: null as null | AiResponse
  };

  // ✨ Sohbet Geçmişi
  chatHistory: any[] = []; 

  selectedImage: File | null = null;
  selectedImagePreview: string | null = null;

  // --- Müşteri Form Modeli ---
  customerForm = { name: '', phone: '', email: '', note: '' };

  // --- Veri Havuzu ---
  visibleCatalogs: Catalog[] = [];

  ngOnInit() {
    this.loadPublicData();
  }

  loadPublicData() {
    this.isLoading = true;

    this.catalogService.getPublicCatalogs().subscribe({
        next: (catalogs) => {
            this.visibleCatalogs = catalogs; 
            
            // Kapak resmi kontrolü
            this.visibleCatalogs.forEach(c => {
                if (!c.imageUrl && c.pages && c.pages.length > 0) {
                    c.imageUrl = c.pages[0].imageUrl;
                }
            });

            this.isLoading = false;
            console.log('Public Kataloglar:', this.visibleCatalogs);
        },
        error: (err) => { 
            console.error('Public Katalog Hatası:', err); 
            this.isLoading = false; 
        }
    });
  }

  // --- 🔥 GERÇEK AI ENTEGRASYONU ---

  // 1. Dosya Seçimi
  onFileSelected(event: any) {
    const file = event.target.files[0];
    if (file) {
      this.selectedImage = file;
      
      const reader = new FileReader();
      reader.onload = (e: any) => this.selectedImagePreview = e.target.result;
      reader.readAsDataURL(file);

      this.aiState.isActive = true;
    }
  }

  // 2. Görseli Temizle
  clearImage() {
    this.selectedImage = null;
    this.selectedImagePreview = null;
    if (!this.searchText) {
        this.aiState.isActive = false;
        this.aiState.response = null; // Ekranı temizle
    }
  }

  // 3. Normal Arama (Input değiştiğinde)
  onSearchInput() {
    if (!this.searchText && !this.selectedImage) {
        this.aiState.isActive = false;
        // Arama temizlenirse normal kataloğa dön
    }
  }

  // 4. 🔥 AI ARAMASINI BAŞLAT
  startAiSearch() {
    if (!this.searchText && !this.selectedImage) return;

    // UI Durumunu Hazırla
    this.aiState.isActive = true;
    this.aiState.isLoading = true;
    this.aiState.response = null;

    // A. Kullanıcı mesajını geçmişe ekle
    this.chatHistory.push({ role: 'user', content: this.searchText || '(Resim Gönderildi)' });

    // B. GERÇEK İSTEK
    this.aiService.sendMessage(this.searchText, this.selectedImage, this.chatHistory).subscribe({
      next: (res: any) => { 
        this.aiState.isLoading = false;
        
        // 🔥 Backend Yanıtını HTML Yapısına Eşle
        // ChatController'dan dönen JSON: { replySuggestion: "...", products: [...], debugInfo: "..." }
        
        this.aiState.response = {
          // HTML: {{ aiState.response.replySuggestion }}
          replySuggestion: res.replySuggestion || "Sonuçlar aşağıdadır:", 
          
          // HTML: @for(part of aiState.response.products)
          products: (res.products || []).map((part: any) => ({
            id: part.id,
            code: part.code,      // Backend artık direkt 'code' dönüyor
            name: part.name,      // Backend artık direkt 'name' dönüyor
            description: part.description, 
            catalogId: part.catalogId, 
            pageNumber: part.pageNumber || '1',
            price: part.price,
            stockStatus: part.stockStatus || 'Stokta Yok', 
            imageUrl: part.imageUrl
          })),

          // HTML: {{ aiState.response.debugInfo }}
          debugInfo: res.debugInfo
        };

        // C. Asistan cevabını geçmişe ekle (History context'i için)
        this.chatHistory.push({ role: 'assistant', content: res.replySuggestion });

        // D. Sadece Inputu temizle (Görsel kalsın mı? Genelde temizlenir)
        // this.searchText = ''; 
        // this.selectedImage = null;
        // this.selectedImagePreview = null;
        // Not: Kullanıcı tekrar sormak isteyebilir diye görseli hemen silmiyoruz, 
        // ama temizlemek istersen yukarıdaki satırları aç.
      },
      error: (err) => {
        this.aiState.isLoading = false;
        console.error('AI Bağlantı Hatası:', err);
        
        this.aiState.response = {
          replySuggestion: "⚠️ Üzgünüm, şu an teknik bir sorun yaşıyorum. Lütfen daha sonra tekrar deneyin.",
          products: []
        };
      }
    });
  }

  // --- KLASİK İŞLEMLER ---

  submitOrder() {
    if (!this.customerForm.name || !this.customerForm.phone) {
      alert('Lütfen Ad Soyad ve Telefon alanlarını doldurunuz.');
      return;
    }
    
    this.isSubmitting = true;
    
    // Sepeti Backend'e gönder
    this.cartService.submitOrder(this.customerForm).subscribe({
      next: (res: any) => {
        alert(`Siparişiniz başarıyla alındı! \nSipariş No: ${res.orderNumber}`);
        this.cartService.clearCart();
        this.isCartOpen = false;
        this.isSubmitting = false;
        this.customerForm = { name: '', phone: '', email: '', note: '' };
      },
      error: (err) => {
        console.error('Sipariş hatası:', err);
        alert('Sipariş oluşturulurken bir hata oluştu.');
        this.isSubmitting = false;
      }
    });
  }

  openCatalog(catalogId: string) {
    this.router.navigate(['/view', catalogId]); 
  }
}