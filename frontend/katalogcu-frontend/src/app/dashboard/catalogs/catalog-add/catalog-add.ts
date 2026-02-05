import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CatalogService } from '../../../core/services/catalog.service';
@Component({
  selector: 'app-catalog-add',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './catalog-add.html',
  styleUrl: './catalog-add.css'
})
export class CatalogAddComponent implements OnInit {
  private catalogService = inject(CatalogService);
  private router = inject(Router);
  private route = inject(ActivatedRoute); 

  model = {
    name: '',
    description: '',
    imageUrl: '', 
    pdfUrl: '',
    status: 'Processing'
    // userId'yi kaldırdık çünkü Backend bunu Token'dan (Auth) alıyor.
  };

  // 🔥 GÜNCELLEME: Hedef Klasör ID'si artık string (GUID)
  targetFolderId: string | null = null;

  isUploadingImage = false;
  isUploadingPdf = false;
  isLoading = false;

  ngOnInit() {
    // Sayfa açılınca URL'deki "folderId" parametresini oku
    // Örnek URL: /dashboard/catalogs/new?folderId=550e8400-e29b...
    const folderIdParam = this.route.snapshot.queryParams['folderId'];
    
    if (folderIdParam) {
      this.targetFolderId = folderIdParam; // Artık Number() çevrimi yapmıyoruz
      console.log("📂 Bu katalog şu klasörün içine eklenecek:", this.targetFolderId);
    }
  }

  // 1. KAPAK RESMİ YÜKLEME
  onImageSelected(event: any) {
    const file: File = event.target.files[0];
    if (file) {
      this.isUploadingImage = true;
      this.catalogService.uploadImage(file).subscribe({
        next: (res) => {
          this.model.imageUrl = res.url;
          this.isUploadingImage = false;
        },
        error: (err) => {
          console.error(err);
          alert('Resim yüklenemedi!');
          this.isUploadingImage = false;
        }
      });
    }
  }

  // 2. PDF YÜKLEME
  onPdfSelected(event: any) {
    const file: File = event.target.files[0];
    
    // Frontend PDF Kontrolü
    if (file && file.type !== 'application/pdf') {
        alert('Lütfen sadece PDF dosyası seçin!');
        return;
    }

    if (file) {
      this.isUploadingPdf = true;
      this.catalogService.uploadImage(file).subscribe({ // Backend'de genel dosya yükleme servisi var
        next: (res) => {
          this.model.pdfUrl = res.url;
          this.isUploadingPdf = false;
        },
        error: (err) => {
          console.error(err);
          alert('PDF yüklenemedi!');
          this.isUploadingPdf = false;
        }
      });
    }
  }

  onSubmit() {
    // Validasyon
    if (!this.model.name || !this.model.pdfUrl) {
        alert('Lütfen katalog adını girin ve bir PDF dosyası yükleyin.');
        return;
    }

    this.isLoading = true;

    // 1. ADIM: Kataloğu Oluştur (Ana Dizin'e düşer)
    this.catalogService.createCatalog(this.model).subscribe({
      next: (createdCatalog) => {
        
        // 2. ADIM: Eğer URL'den gelen bir hedef klasör varsa, oraya taşı
        if (this.targetFolderId) {
            this.catalogService.moveCatalog(createdCatalog.id, this.targetFolderId).subscribe({
                 next: () => this.finalizeProcess(),
                 error: (err) => {
                     console.error("Taşıma hatası:", err);
                     // Taşıma başarısız olsa bile katalog oluştu, o yüzden işlemi bitiriyoruz
                     // Sadece kullanıcıya bilgi verebiliriz veya sessizce geçebiliriz.
                     this.finalizeProcess(); 
                 }
            });
        } else {
            // Hedef klasör yoksa direkt bitir
            this.finalizeProcess(); 
        }
      },
      error: (err) => {
        console.error(err);
        alert('Katalog oluşturulurken bir hata oluştu: ' + (err.error?.message || err.message));
        this.isLoading = false;
      }
    });
  }

  // İşlem bitince yapılacaklar
  finalizeProcess() {
      // Kullanıcıya başarı mesajı verip listeye dönüyoruz
      // alert('Katalog başarıyla oluşturuldu!'); // Kullanıcı deneyimi için alert yerine direkt yönlendirme daha şık olabilir
      this.isLoading = false;
      this.router.navigate(['/dashboard/catalogs']);
  }
  
  // Yardımcı metod: Dosya adını temiz göstermek için
  getFileName(url: string): string {
      if (!url) return '';
      return url.split('/').pop() || 'Dosya';
  }
}