import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ProductService, Product } from '../../../core/services/product.service';
import { CatalogService, Catalog } from '../../../core/services/catalog.service';

@Component({
  selector: 'app-parts-add',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './parts-add.html',
  styleUrl: './parts-add.css'
})
export class PartsAddComponent implements OnInit {
  private productService = inject(ProductService);
  private catalogService = inject(CatalogService); // Katalogları çekmek ve Resim yüklemek için
  private router = inject(Router);

  catalogs: Catalog[] = [];
  
  // 🔥 YENİ MODEL YAPISI (Interface ile uyumlu)
  model: Product = {
    // id: Opsiyonel olduğu için sildik, backend üretecek
    code: '',
    name: '',
    oemNo: '',         // ✨ Yeni
    category: 'Genel', // Varsayılan kategori
    price: 0,
    stockQuantity: 0,
    description: '',
    catalogId: '',     // Boş bırakılırsa "Genel Stok" olur
    imageUrl: ''       // ✨ Yeni (Resim yüklenince dolacak)
  };

  isLoading = false;
  isUploading = false; // Resim yüklenirken butonu kilitlemek için

  ngOnInit() {
    this.loadCatalogs();
  }

  loadCatalogs() {
    this.catalogService.getCatalogs().subscribe({
      next: (data) => {
        this.catalogs = data;
      },
      error: (err) => console.error('Kataloglar yüklenemedi', err)
    });
  }

  // 🔥 RESİM YÜKLEME FONKSİYONU
  onFileSelected(event: any) {
    const file: File = event.target.files[0];
    if (file) {
      this.isUploading = true;
      
      // CatalogService içindeki uploadImage metodunu kullanıyoruz (Genel dosya yükleyici)
      this.catalogService.uploadImage(file).subscribe({
        next: (response: any) => {
          // Backend'den { url: 'uploads/...' } dönüyor varsayıyoruz
          this.model.imageUrl = response.url; 
          this.isUploading = false;
        },
        error: (err) => {
          console.error('Resim yükleme hatası:', err);
          alert('Resim yüklenirken hata oluştu.');
          this.isUploading = false;
        }
      });
    }
  }

  onSubmit() {
    // Validasyonlar
    if (!this.model.code || !this.model.name) {
      alert('Lütfen Parça Kodu ve Adını giriniz.');
      return;
    }

    this.isLoading = true;

    // Eğer catalogId boş string geldiyse (''), undefined yapalım ki backend null algılasın
    // (veya backend boş string'i yönetiyorsa bu satıra gerek yok)
    if (this.model.catalogId === '') {
       delete this.model.catalogId;
    }

    this.productService.createProduct(this.model).subscribe({
      next: () => {
        alert('Parça başarıyla eklendi!');
        this.router.navigate(['/dashboard/parts']);
      },
      error: (err) => {
        console.error(err);
        alert('Kaydetme sırasında hata oluştu!');
        this.isLoading = false;
      }
    });
  }
}