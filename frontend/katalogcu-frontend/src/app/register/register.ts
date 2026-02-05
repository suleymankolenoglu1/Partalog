import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../core/services/auth.service';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './register.html',
  styleUrl: './register.css'
})
export class RegisterComponent {
  private authService = inject(AuthService);
  private router = inject(Router);

  // Form Verileri
  fullName = '';
  email = '';
  password = '';
  termsAccepted = false;
  
  showPassword = false;
  isLoading = false;
  errorMessage = '';

  togglePassword() {
    this.showPassword = !this.showPassword;
  }

  onRegister() {
    // Basit Validasyonlar
    if (!this.fullName || !this.email || !this.password) {
      this.errorMessage = 'Lütfen tüm alanları doldurun.';
      return;
    }

    if (!this.termsAccepted) {
      this.errorMessage = 'Lütfen kullanım koşullarını kabul edin.';
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';

    // Servisi Çağır
    this.authService.register({
      fullName: this.fullName,
      email: this.email,
      password: this.password
    }).subscribe({
      next: () => {
        alert('Kayıt başarılı! Giriş sayfasına yönlendiriliyorsunuz.');
        this.router.navigate(['/login']);
      },
      error: (err) => {
        this.isLoading = false;
        // Backend'den gelen mesajı göster veya genel hata ver
        this.errorMessage = err.error?.message || 'Kayıt sırasında bir hata oluştu!';
      }
    });
  }
}