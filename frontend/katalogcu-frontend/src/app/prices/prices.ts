import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-prices',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './prices.html',
  styleUrl: './prices.css'
})
export class PricesComponent {
  // Fiyatlandırma ile ilgili dinamik işlemler (örn: aylık/yıllık geçişi) buraya eklenebilir
}