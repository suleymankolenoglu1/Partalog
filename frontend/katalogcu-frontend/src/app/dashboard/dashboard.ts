import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CatalogService, DashboardStats } from '../core/services/catalog.service'; // Yolu kendi projenize göre düzeltin

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css'
})
export class DashboardComponent implements OnInit {
  
  private catalogService = inject(CatalogService);

  stats: DashboardStats | null = null;
  isLoading = true;

  ngOnInit() {
    this.loadStats();
  }

  loadStats() {
    this.isLoading = true;
    this.catalogService.getDashboardStats().subscribe({
      next: (data) => {
        this.stats = data;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Dashboard verisi çekilemedi:', err);
        this.isLoading = false;
      }
    });
  }

  // Statüye göre renk sınıfı döndüren yardımcı fonksiyon
  getStatusClass(status: string): string {
    switch (status) {
      case 'Published': return 'badge-ok';    // Yeşil
      case 'Processing': return 'badge-wait'; // Turuncu/Sarı
      case 'Draft': return 'badge-gray';      // Gri
      default: return 'badge-gray';
    }
  }

  // Statü metnini Türkçeye çeviren yardımcı fonksiyon
  getStatusLabel(status: string): string {
    switch (status) {
      case 'Published': return 'YAYINDA';
      case 'Processing': return 'İŞLENİYOR';
      case 'Draft': return 'TASLAK';
      case 'Pending': return 'ONAY BEKLİYOR';
      default: return status;
    }
  }
}