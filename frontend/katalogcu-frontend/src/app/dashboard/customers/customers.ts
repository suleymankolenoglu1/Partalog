import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-customers',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './customers.html',
  styleUrl: './customers.css'
})
export class CustomersComponent {
  // Sahte Müşteri Listesi
  customers = [
    { 
      id: 1, 
      name: 'Ahmet Yılmaz', 
      company: 'Yılmaz Oto Servis', 
      email: 'ahmet@yilmazoto.com', 
      phone: '0532 123 45 67', 
      balance: -12500, // Borçlu
      status: 'active',
      lastOrder: '2 gün önce'
    },
    { 
      id: 2, 
      name: 'Mehmet Demir', 
      company: 'Demirler Yedek Parça', 
      email: 'info@demirler.com', 
      phone: '0555 987 65 43', 
      balance: 0, 
      status: 'active',
      lastOrder: 'Bugün'
    },
    { 
      id: 3, 
      name: 'Ayşe Kaya', 
      company: 'Kaya Ford Özel Servis', 
      email: 'ayse@kayaoto.com', 
      phone: '0544 222 33 44', 
      balance: -4500, 
      status: 'inactive',
      lastOrder: '1 ay önce'
    },
    { 
      id: 4, 
      name: 'Ali Vural', 
      company: 'Vural Rot Balans', 
      email: 'ali@vuralrot.com', 
      phone: '0533 444 55 66', 
      balance: 1500, // Alacaklı
      status: 'active',
      lastOrder: '3 hafta önce'
    },
    { 
      id: 5, 
      name: 'Canan Yıldız', 
      company: 'Yıldız Otomotiv', 
      email: 'canan@yildizoto.com', 
      phone: '0530 111 22 33', 
      balance: 0, 
      status: 'blocked',
      lastOrder: '6 ay önce'
    },
  ];

  // Müşteri Durumuna Göre Badge Rengi
  getStatusBadge(status: string) {
    switch(status) {
      case 'active': return 'bg-green-100 text-green-800 dark:bg-green-500/20 dark:text-green-400';
      case 'inactive': return 'bg-gray-100 text-gray-800 dark:bg-gray-500/20 dark:text-gray-400';
      case 'blocked': return 'bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-400';
      default: return '';
    }
  }

  // Bakiye Durumuna Göre Renk (Borçluysa Kırmızı)
  getBalanceClass(balance: number) {
    if (balance < 0) return 'text-red-500 font-bold'; // Borçlu
    if (balance > 0) return 'text-green-500 font-bold'; // Alacaklı
    return 'text-text-dark dark:text-text-light'; // Nötr
  }
}