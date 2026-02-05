
import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ProductService } from '../../../core/services/product.service';
import { CatalogService, Catalog } from '../../../core/services/catalog.service';

@Component({
  selector: 'app-parts-import',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './parts-import.html',
  styleUrl: './parts-import.css'
})
export class PartsImportComponent implements OnInit {
  private productService = inject(ProductService);
  private catalogService = inject(CatalogService);
  private router = inject(Router);

  catalogs: Catalog[] = [];
  selectedCatalogId = '';
  
  selectedFile: File | null = null;
  isUploading = false;

  ngOnInit() {
    // Hangi kataloğa yükleneceğini seçmek için katalogları getir
    this.catalogService.getCatalogs().subscribe(data => {
      this.catalogs = data;
    });
  }

  onFileSelected(event: any) {
    this.selectedFile = event.target.files[0];
  }

  onUpload() {
    if (!this.selectedFile || !this.selectedCatalogId) {
      alert('Lütfen bir katalog ve Excel dosyası seçin.');
      return;
    }

    this.isUploading = true;

    this.productService.importExcel(this.selectedFile, this.selectedCatalogId).subscribe({
      next: (res) => {
        alert(res.message);
        this.router.navigate(['/dashboard/parts']); // Listeye dön
      },
      error: (err) => {
        console.error(err);
        alert('Yükleme başarısız! Excel formatını kontrol edin.');
        this.isUploading = false;
      }
    });
  }
}