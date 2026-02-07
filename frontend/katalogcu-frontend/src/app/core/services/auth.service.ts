import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment.development';
import { tap } from 'rxjs/operators';
import { Router } from '@angular/router';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);
  private apiUrl = environment.apiUrl;

  // Giriş Yap
  login(credentials: { email: string; password: string }) {
    return this.http.post<any>(`${this.apiUrl}/auth/login`, credentials).pipe(
      tap(response => {
        if (response.token) {
          // Token'ı tarayıcıya kaydet
          localStorage.setItem('auth_token', response.token);
          // Kullanıcı bilgisini kaydet (Opsiyonel)
          localStorage.setItem('user_info', JSON.stringify(response.user));
        }
      })
    );
  }
  register(userData: { fullName: string; email: string; password: string }) {
    return this.http.post<any>(`${this.apiUrl}/auth/register`, userData);
  }

  // Çıkış Yap
  logout() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user_info');
    this.router.navigate(['/login']);
  }

  // Kullanıcı giriş yapmış mı?
  isLoggedIn(): boolean {
    return !!localStorage.getItem('auth_token');
  }

  // Token'ı getir
  getToken(): string | null {
    return localStorage.getItem('auth_token');
  }

  // ✅ UserId'yi getir
  getUserId(): string | null {
    const raw = localStorage.getItem('user_info');
    if (!raw) return null;

    try {
      const user = JSON.parse(raw);
      return user?.id ?? null;
    } catch {
      return null;
    }
  }
}