import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms'; // 🔥 HTML'de ngModel kullandığımız için şart
import { ShowcaseMedia } from '../../core/services/catalog.service'; // Interface'i import ettik

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule], 
  templateUrl: './settings.html',
  styleUrl: './settings.css'
})
export class SettingsComponent {

  // Aktif sekme (Type güvenliği için string literal kullandık)
  activeTab: 'general' | 'security' | 'notifications' | 'showcase' = 'general';

  // --- VITRIN (SHOWCASE) VERİLERİ ---

  // Mevcut Vitrin Listesi (Başlangıçta boş görünmesin diye örnek veri koyduk)
  showcaseItems: ShowcaseMedia[] = [
    {
      id: '1',
      type: 'image',
      url: 'https://images.unsplash.com/photo-1486262715619-01b80250e0dc?auto=format&fit=crop&q=80&w=1600',
      title: '2026 Yeni Motor Serisi',
      subtitle: 'Performans ve dayanıklılık bir arada.'
    }
  ];

  // Yeni eklenecek medya için geçici obje (Forma bağlı)
  newMedia: Partial<ShowcaseMedia> = {
    type: 'image',
    title: '',
    subtitle: '',
    url: ''
  };

  // --- FONKSİYONLAR ---

  // Sekme Değiştirme
  setActiveTab(tabName: 'general' | 'security' | 'notifications' | 'showcase') {
    this.activeTab = tabName;
  }

  // Dosya Seçme Simülasyonu 
  // (Backend olmadan dosyayı tarayıcıda önizlemek için)
  onFileSelected(event: any) {
    const file = event.target.files[0];
    if (file) {
      // Dosyadan geçici bir URL oluşturuyoruz
      const fakeUrl = URL.createObjectURL(file);
      
      this.newMedia.url = fakeUrl;
      // Dosya tipine göre video mu resim mi karar veriyoruz
      this.newMedia.type = file.type.includes('video') ? 'video' : 'image';
    }
  }

  // Listeye Ekleme
  addMedia() {
    if (!this.newMedia.url) return;

    // Yeni öğeyi listenin en başına ekle (unshift)
    this.showcaseItems.unshift({
      id: Date.now().toString(), // Benzersiz ID
      type: this.newMedia.type || 'image',
      url: this.newMedia.url!,
      title: this.newMedia.title,
      subtitle: this.newMedia.subtitle
    });

    // Ekleme bitince formu temizle
    this.newMedia = { type: 'image', title: '', subtitle: '', url: '' };
  }

  // Listeden Silme
  deleteMedia(id: string) {
    this.showcaseItems = this.showcaseItems.filter(item => item.id !== id);
  }

  // Genel Kayıt
  saveSettings() {
    // Gerçek uygulamada burada servise data gönderilir
    console.log('Kaydedilen Vitrin Verisi:', this.showcaseItems);
    alert('Tüm ayarlar ve vitrin düzenlemeleri başarıyla kaydedildi!');
  }
}