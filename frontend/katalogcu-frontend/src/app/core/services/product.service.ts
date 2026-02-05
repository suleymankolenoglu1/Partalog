import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment.development';
import { Observable } from 'rxjs';

// 🔥 GÜNCELLENDİ: Backend'den gelen yeni alanlar eklendi
export interface Product {
  id?: string;
  code: string;          // Parça Kodu
  name: string;          // Parça Adı
  oemNo?: string;        // ✨ YENİ: OEM Numarası
  category?: string;     // Kategori (Motor, Fren vb.)
  price: number;
  stockQuantity: number;
  imageUrl?: string;     // ✨ YENİ: Parça Görseli
  description?: string;
  
  // İlişkisel Veriler
  catalogName?: string;  // ✨ YENİ: Tabloda "Hangi Katalog" sütunu için
  catalogId?: string;
  pageNumber?: string;
  refNo?: number;
}

@Injectable({
  providedIn: 'root'
})
export class ProductService {
  private http = inject(HttpClient);
  private apiUrl = environment.apiUrl;

  // 1. Tüm Parçaları Getir (Admin Envanter Sayfası İçin)
  getProducts(): Observable<Product[]> {
    return this.http.get<Product[]>(`${this.apiUrl}/products`);
  }

  // 2. Belirli Bir Kataloğa Ait Parçaları Getir (Vitrin / PublicView İçin)
  getProductsByCatalog(catalogId: string): Observable<Product[]> {
    return this.http.get<Product[]>(`${this.apiUrl}/products/catalog/${catalogId}`);
  }

  // 3. Yeni Parça Ekle
  // Partial<Product> kullanarak ID gibi zorunlu olmayan alanları es geçebiliyoruz
  createProduct(product: Partial<Product>): Observable<Product> {
    return this.http.post<Product>(`${this.apiUrl}/products`, product);
  }

  // 4. Parça Sil
  deleteProduct(id: string): Observable<any> {
    return this.http.delete(`${this.apiUrl}/products/${id}`);
  }

  // 5. Excel Import
  importExcel(file: File, catalogId: string): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    
    // Eğer genel stok yüklemesi yapılıyorsa catalogId boş olabilir
    if (catalogId) {
      formData.append('catalogId', catalogId);
    }

    return this.http.post(`${this.apiUrl}/products/import`, formData);
  }
}