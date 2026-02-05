import { Component, OnInit, inject } from '@angular/core';
import { CommonModule, Location } from '@angular/common'; // Location servisi burada
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CatalogService, Catalog } from '../core/services/catalog.service';

// Vitrin kartları için arayüz
export interface CatalogGroup {
  pageIndex: number;
  pageNumber: number;
  title: string;
  imageUrl: string;
  partCount: number;
}

@Component({
  selector: 'app-public-catalog-showcase',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  // Dosya isimlerinle uyumlu yollar:
  templateUrl: './public-catalog-showcase.html',
  styleUrls: ['./public-catalog-showcase.css']
})
export class PublicCatalogShowcaseComponent implements OnInit {
  
  // Dependency Injection (inject fonksiyonu ile)
  private route = inject(ActivatedRoute);
  private location = inject(Location); // Geri butonu için gerekli
  private catalogService = inject(CatalogService);

  catalog: Catalog | null = null;
  groups: CatalogGroup[] = [];
  filteredGroups: CatalogGroup[] = [];
  
  isLoading = true;
  searchQuery = '';

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.loadCatalog(id);
    } else {
      this.isLoading = false;
      console.error('Katalog ID bulunamadı.');
    }
  }

  loadCatalog(id: string) {
    this.isLoading = true;
    this.catalogService.getCatalogById(id).subscribe({
      next: (data) => {
        this.catalog = data;
        this.prepareGroups();
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Katalog yüklenirken hata oluştu:', err);
        this.isLoading = false;
      }
    });
  }

  prepareGroups() {
    if (!this.catalog?.pages) return;

    this.groups = this.catalog.pages
      .map((page, index) => {
        // Eğer sayfada hiç parça işaretlenmemişse vitrine koyma
        const hasHotspots = (page.hotspots?.length ?? 0) > 0;
        if (!hasHotspots) return null;

        return {
          pageIndex: index,
          pageNumber: page.pageNumber,
          // Varsa AI başlığını kullan, yoksa varsayılan
          title: page.aiDescription || `Montaj Grubu #${page.pageNumber}`, 
          imageUrl: page.imageUrl,
          partCount: page.hotspots?.length || 0
        };
      })
      .filter(g => g !== null) as CatalogGroup[];

    // Başlangıçta hepsi görünür
    this.filteredGroups = this.groups;
  }

  onSearch() {
    if (!this.searchQuery.trim()) {
      this.filteredGroups = this.groups;
      return;
    }
    
    const query = this.searchQuery.toLowerCase();
    
    this.filteredGroups = this.groups.filter(g => 
      g.title.toLowerCase().includes(query) || 
      g.pageNumber.toString().includes(query)
    );
  }

  goBack() {
    this.location.back();
  }
}