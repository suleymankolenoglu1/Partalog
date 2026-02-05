import { Component, inject } from '@angular/core'; // inject eklendi
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms'; // 👈 Form işlemleri için gerekli
import { AuthService } from '../core/services/auth.service';
 // Servisi çağırdık

@Component({
  selector: 'app-login',
  standalone: true,
  // 👇 FormsModule'u eklemeyi unutma!
  imports: [CommonModule, RouterLink, FormsModule], 
  templateUrl: './login.html',
  styleUrl: './login.css'
})
export class LoginComponent {
  private authService = inject(AuthService);
  private router = inject(Router);

  // Form verileri
  email = '';
  password = '';
  showPassword = false;
  errorMessage = ''; // Hata mesajı göstermek için
  isLoading = false; // Yükleniyor animasyonu için

  togglePassword() {
    this.showPassword = !this.showPassword;
  }

  onLogin() {
    if (!this.email || !this.password) {
      this.errorMessage = 'Lütfen tüm alanları doldurun.';
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';

    this.authService.login({ email: this.email, password: this.password }).subscribe({
      next: () => {
        // Başarılı! Dashboard'a git
        this.router.navigate(['/dashboard']);
      },
      error: (err) => {
        // Hata! (401 Unauthorized vb.)
        this.isLoading = false;
        this.errorMessage = 'E-posta veya şifre hatalı!';
        console.error(err);
      }
    });
  }
}