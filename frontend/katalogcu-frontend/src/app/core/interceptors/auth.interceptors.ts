

import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from '../services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  // Servisi inject ediyoruz (Constructor olmadığı için bu yöntemi kullanıyoruz)
  const authService = inject(AuthService);
  
  // Token'ı alıyoruz
  const token = authService.getToken();

  // Eğer token varsa, isteği kopyalayıp başlığına ekliyoruz
  if (token) {
    const clonedRequest = req.clone({
      setHeaders: {
        Authorization: `Bearer ${token}`
      }
    });
    
    // Değiştirilmiş isteği gönder
    return next(clonedRequest);
  }

  // Token yoksa isteği olduğu gibi gönder
  return next(req);
};