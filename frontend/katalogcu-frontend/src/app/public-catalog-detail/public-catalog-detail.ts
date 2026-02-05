import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CatalogService, Catalog, CatalogPage } from '../core/services/catalog.service';
import { ProductService, Product } from '../core/services/product.service';

@Component({
  selector: 'app-public-catalog-detail',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './public-catalog-detail.html',
  styles: [`
    .no-select { user-select: none; }
    /* Kart Animasyonu */
    .slide-up { animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
    @keyframes slideUp {
      from { transform: translate(-50%, 100%); opacity: 0; }
      to { transform: translate(-50%, 0); opacity: 1; }
    }
  `]
})
export class PublicCatalogDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private catalogService = inject(CatalogService);
  private productService = inject(ProductService);

  catalog: Catalog | null = null;
  allProducts: Product[] = [];

  activePage: CatalogPage | null = null;
  activePageIndex: number = 0;
  isLoading = true;

  selectedPartLabel: string | null = null;
  selectedProductId: string | null = null;

  transform = { x: 0, y: 0, scale: 1 };
  isDragging = false;
  startX = 0;
  startY = 0;

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.loadCatalog(id);
      this.loadProducts(id);
    }
  }

  loadCatalog(id: string) {
    this.isLoading = true;
    this.catalogService.getCatalogById(id).subscribe({
      next: (data) => {
        this.catalog = data;
        if (this.catalog.pages && this.catalog.pages.length > 0) this.selectPage(0);
        this.isLoading = false;
      },
      error: (err) => { console.error(err); this.isLoading = false; }
    });
  }

  loadProducts(catalogId: string) {
    this.productService.getProductsByCatalog(catalogId).subscribe({
      next: (data) => {
        this.allProducts = data;
      },
      error: (err) => console.error("Ürünler yüklenemedi", err)
    });
  }

  // ✨ GÜNCELLENDİ: Seçili ürünü bulma mantığı
  get selectedProduct(): Product | undefined {
    // 1. Önce ID ile bulmaya çalış
    if (this.selectedProductId) {
      return this.allProducts.find(p => p.id === this.selectedProductId);
    }
    // 2. ID yoksa Label (RefNo) ile bulmaya çalış (Yedek Plan)
    if (this.selectedPartLabel) {
      return this.allProducts.find(p => p.refNo?.toString() === this.selectedPartLabel);
    }
    return undefined;
  }

  // ✨ GÜNCELLENDİ: Çift Kayıtları Temizleyen Liste
  get currentPageProducts(): Product[] {
    if (!this.activePage) return [];

    let rawList: Product[] = [];
    const hasHotspots = (this.activePage.hotspots?.length ?? 0) > 0;

    // A. Ham listeyi al
    if (hasHotspots) {
      rawList = this.allProducts; // Teknik resimse hepsi
    } else {
      const pageNum = this.activePage.pageNumber.toString();
      rawList = this.allProducts.filter(p => p.pageNumber?.toString() === pageNum);
    }

    // B. Çiftleri Temizle (DISTINCT)
    // RefNo'su aynı olanlardan sadece birini alıyoruz.
    const uniqueMap = new Map<string, Product>();
    rawList.forEach(p => {
      // Anahtar: RefNo varsa onu kullan, yoksa ID
      const key = p.refNo ? `ref-${p.refNo}` : `id-${p.id}`;
      if (!uniqueMap.has(key)) {
        uniqueMap.set(key, p);
      }
    });

    // C. Sırala ve Döndür
    return Array.from(uniqueMap.values()).sort((a, b) => {
      const refA = a.refNo || 999999;
      const refB = b.refNo || 999999;
      return refA - refB;
    });
  }

  selectPage(index: number) {
    if (!this.catalog?.pages) return;
    this.activePageIndex = index;
    this.activePage = this.catalog.pages[index];
    this.selectedPartLabel = null; 
    this.selectedProductId = null;
    this.resetZoom();
  }

  nextPage() {
    if (!this.catalog?.pages) return;
    if (this.activePageIndex < this.catalog.pages.length - 1) this.selectPage(this.activePageIndex + 1);
  }

  prevPage() {
    if (this.activePageIndex > 0) this.selectPage(this.activePageIndex - 1);
  }

  // --- ✨ AKILLI ETKİLEŞİM ---

  onHotspotClick(label: string, productId?: string) {
    this.selectedPartLabel = label;
    
    // Eğer hotspot'a ürün bağlanmışsa onu seç
    if (productId) {
      this.selectedProductId = productId;
    } 
    // Bağlanmamışsa, Label ile RefNo eşleşmesi yapıp ID'yi bulmaya çalış (Auto-Match)
    else {
      const matchedProduct = this.allProducts.find(p => p.refNo?.toString() === label);
      this.selectedProductId = matchedProduct?.id || null;
    }

    // Listede kaydır
    const targetId = this.selectedProductId;
    if (targetId) {
      setTimeout(() => {
        const element = document.getElementById(`product-row-${targetId}`);
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 50);
    }
  }

  onProductClick(product: Product) {
    this.selectedProductId = product.id || null;
    
    // Ürüne tıklayınca resimdeki kutuyu yak
    if (this.activePage?.hotspots) {
        // ID ile eşleşen var mı?
        let matchingSpot = this.activePage.hotspots.find(h => h.productId === product.id);
        
        // ID yoksa RefNo ile eşleşen var mı?
        if (!matchingSpot && product.refNo) {
           matchingSpot = this.activePage.hotspots.find(h => h.label === product.refNo?.toString());
        }

        if (matchingSpot) {
            this.selectedPartLabel = matchingSpot.label;
        } else {
            this.selectedPartLabel = null;
        }
    }
  }

  // --- ZOOM & PAN ---
  zoomIn() { this.transform.scale = Math.min(this.transform.scale + 0.2, 5); }
  zoomOut() { this.transform.scale = Math.max(this.transform.scale - 0.2, 0.5); }
  resetZoom() { this.transform = { x: 0, y: 0, scale: 1 }; }

  onWheel(event: WheelEvent) {
    event.preventDefault();
    if (event.deltaY < 0) this.zoomIn(); else this.zoomOut();
  }

  startDrag(event: MouseEvent) {
    this.isDragging = true;
    this.startX = event.clientX - this.transform.x;
    this.startY = event.clientY - this.transform.y;
  }

  onDrag(event: MouseEvent) {
    if (!this.isDragging) return;
    event.preventDefault();
    this.transform.x = event.clientX - this.startX;
    this.transform.y = event.clientY - this.startY;
  }

  endDrag() { this.isDragging = false; }
  
  get visibleParts() { return this.activePage?.hotspots || []; }
}