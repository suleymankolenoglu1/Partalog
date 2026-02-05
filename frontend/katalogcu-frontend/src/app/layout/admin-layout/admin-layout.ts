import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../core/services/auth.service'; // Yolun doğru olduğundan emin ol

@Component({
  selector: 'app-admin-layout',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './admin-layout.html',
  styleUrl: './admin-layout.css'
})
export class AdminLayoutComponent {
  // Auth servisini içeri alıyoruz
  private authService = inject(AuthService);

  isSidebarOpen = true;

  // HTML'deki (click)="logout()" olayının çağırdığı fonksiyon
  logout() {
    this.authService.logout();
  }
}