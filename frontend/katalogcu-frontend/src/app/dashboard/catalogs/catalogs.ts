import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CatalogService, Catalog, Folder } from '../../core/services/catalog.service';

@Component({
  selector: 'app-catalogs',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './catalogs.html',
  styleUrl: './catalogs.css'
})
export class CatalogsComponent implements OnInit {
  private catalogService = inject(CatalogService);

  isLoading = true;
  isProcessing = false; // AI işlemi sırasında kilit

  // --- Veri Havuzu ---
  allCatalogs: Catalog[] = [];
  allFolders: Folder[] = [];

  // --- Görünüm Durumu (State) ---
  // DİKKAT: Backend GUID kullandığı için ID tipi 'string' oldu.
  currentFolderId: string | null = null; 
  breadcrumbs: { id: string | null, name: string }[] = [{ id: null, name: 'Ana Dizin' }];

  // Ekranda gösterilenler
  visibleFolders: Folder[] = [];
  visibleCatalogs: Catalog[] = [];

  // ✨ Sürükle Bırak için
  draggedCatalogId: string | null = null;

  ngOnInit() {
    this.loadData();
  }

  loadData() {
    this.isLoading = true;

    // 1. Klasörleri Çek (API: GET /api/folders)
    this.catalogService.getFolders().subscribe({
      next: (folders) => {
        this.allFolders = folders;
        
        // 2. Katalogları Çek (API: GET /api/catalogs)
        this.catalogService.getCatalogs().subscribe({
          next: (catalogs) => {
            this.allCatalogs = catalogs;
            this.updateFolderCounts();
            this.refreshView();
            this.isLoading = false;
          },
          error: (err) => {
            console.error('Katalog hatası:', err);
            this.isLoading = false;
          }
        });
      },
      error: (err) => {
        console.error('Klasör hatası:', err);
        this.isLoading = false;
      }
    });
  }

  // --- KLASÖR İŞLEMLERİ ---

  createFolder() {
    const folderName = prompt("Yeni Klasör Adı:");
    if (!folderName) return;

    // Backend: POST /api/folders
    this.catalogService.createFolder(folderName).subscribe({
      next: (newFolder) => {
        this.allFolders.push(newFolder); // Listeye ekle
        this.refreshView();
      },
      error: (err) => alert("Klasör oluşturulamadı: " + err.message)
    });
  }

  // 🔥 YENİ: KLASÖR SİLME
  deleteFolder(folder: Folder, event: Event) {
    event.stopPropagation(); // Klasörün içine girmeyi engelle
    
    if (!confirm(`"${folder.name}" klasörünü ve görünümünü silmek istiyor musun? (İçindeki kataloglar Ana Dizin'e düşer.)`)) return;

    // Backend: DELETE /api/folders/{id}
    this.catalogService.deleteFolder(folder.id).subscribe({
      next: () => {
        // Listeden çıkar
        this.allFolders = this.allFolders.filter(f => f.id !== folder.id);
        
        // Eğer silinen klasörün içindeki kataloglar varsa, onları "Ana Dizin"e (null) çek
        // (Backend zaten FolderId'yi null yaptı, biz de UI'da güncelleyelim)
        this.allCatalogs.forEach(c => {
            if (c.folderId === folder.id) c.folderId = null; // veya undefined
        });

        this.updateFolderCounts();
        this.refreshView();
      },
      error: (err) => alert("Silme başarısız: " + err.message)
    });
  }

  enterFolder(folder: Folder) {
    this.currentFolderId = folder.id;
    this.breadcrumbs.push({ id: folder.id, name: folder.name });
    this.refreshView();
  }

  navigateToBreadcrumb(index: number) {
    this.breadcrumbs = this.breadcrumbs.slice(0, index + 1);
    this.currentFolderId = this.breadcrumbs[this.breadcrumbs.length - 1].id;
    this.refreshView();
  }

  // --- GÖRÜNÜM GÜNCELLEME ---

  refreshView() {
    // 1. Hangi Klasörleri Göstereceğiz?
    if (this.currentFolderId === null) {
      // Ana Dizindeysek: Tüm klasörleri göster
      this.visibleFolders = this.allFolders;
    } else {
      // Bir klasörün içindeysek: Alt klasör yok (Backend yapısı düz olduğu için)
      this.visibleFolders = [];
    }

    // 2. Hangi Katalogları Göstereceğiz?
    // Catalog.folderId ile CurrentFolderId eşleşmeli (null ise null, doluysa dolu)
    this.visibleCatalogs = this.allCatalogs.filter(c => c.folderId === this.currentFolderId || (this.currentFolderId === null && !c.folderId));
  }

  updateFolderCounts() {
    this.allFolders.forEach(folder => {
      // Bu klasöre ait katalog sayısı
      const count = this.allCatalogs.filter(c => c.folderId === folder.id).length;
      folder.itemCount = count;
    });
  }

  // --- SÜRÜKLE & BIRAK (DRAG & DROP) ---

  onDragStart(event: DragEvent, catalogId: string) {
    this.draggedCatalogId = catalogId;
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
  }

  onDrop(event: DragEvent, targetFolder: Folder) {
    event.preventDefault();
    if (!this.draggedCatalogId) return;

    const catId = this.draggedCatalogId;
    const targetFolderId = targetFolder.id;

    // Backend'de güncelleme yapılması lazım (Catalog Update endpoint'i)
    // Serviste updateCatalog metodunu kullanıyoruz
    const catalog = this.allCatalogs.find(c => c.id === catId);
    if (!catalog) return;

    // Eski halini yedekle (hata olursa geri almak için)
    const oldFolderId = catalog.folderId;

    // UI'da hemen güncelle (Hız hissi için optimistic update)
    catalog.folderId = targetFolderId;
    this.updateFolderCounts();
    this.refreshView();
    this.draggedCatalogId = null;

    // Backend'e haber ver
    // (Burada moveCatalog veya updateCatalog metodu backend'e Catalog nesnesini göndermeli)
    this.catalogService.moveCatalog(catId, targetFolderId).subscribe({
      error: (err) => {
        console.error("Taşıma hatası:", err);
        // Hata olursa geri al
        catalog.folderId = oldFolderId;
        this.updateFolderCounts();
        this.refreshView();
        alert("Katalog taşınamadı.");
      }
    });
  }

  // --- YARDIMCI / STATUS ---

  getStatusText(status: string): string {
    const s = status?.toLowerCase();
    const map: any = { 
        'published': 'Yayında', 
        'processing': 'İşleniyor', 
        'uploading': 'Yükleniyor',
        'readytoprocess': 'Analiz Bekliyor',
        'ai_completed': 'Analiz Tamamlandı',
        'error': 'Hata',
        'draft': 'Taslak' 
    };
    return map[s] || 'Taslak';
  }

  getStatusClass(status: string): string {
    const s = status?.toLowerCase();
    if (s === 'published') return 'bg-green-100 text-green-700 border-green-200';
    if (s === 'ai_completed') return 'bg-teal-100 text-teal-700 border-teal-200';
    if (s === 'processing' || s === 'uploading') return 'bg-blue-100 text-blue-700 border-blue-200 animate-pulse';
    if (s === 'readytoprocess') return 'bg-purple-100 text-purple-700 border-purple-200';
    if (s === 'error') return 'bg-red-100 text-red-700 border-red-200';
    return 'bg-gray-100 text-gray-600 border-gray-200';
  }

  deleteCatalog(id: string, event: Event) {
    event.stopPropagation();
    if (confirm('Bu kataloğu silmek istediğinize emin misiniz?')) {
      this.catalogService.deleteCatalog(id).subscribe({
        next: () => {
          this.allCatalogs = this.allCatalogs.filter(c => c.id !== id);
          this.updateFolderCounts();
          this.refreshView();
        },
        error: (err) => alert('Silme işlemi başarısız.')
      });
    }
  }

  startAiAnalysis(catalog: Catalog, event: Event) {
    event.stopPropagation();
    
    if(!confirm(`${catalog.name} için AI analizi başlatılacak. Onaylıyor musun?`)) return;

    this.isProcessing = true;
    catalog.status = 'Processing'; 

    this.catalogService.startAiProcess(catalog.id).subscribe({
        next: () => {
            alert('AI Analizi Başlatıldı! Arka planda devam ediyor.');
            this.isProcessing = false;
            // Status backend'den Processing olarak döndü, polling veya refresh gerekebilir ama şimdilik böyle kalsın
        },
        error: (err) => {
            console.error(err);
            alert('Hata: ' + (err.error?.message || err.message));
            this.isProcessing = false;
            catalog.status = 'Error';
        }
    });
  }
}