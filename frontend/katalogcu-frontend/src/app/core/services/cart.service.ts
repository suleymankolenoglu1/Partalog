import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject } from 'rxjs';
import { CatalogPageItem } from './catalog.service'; // 🔥 Doğru interface'i buradan alıyoruz

export interface CartItem {
  product: CatalogPageItem; 
  quantity: number;
}

@Injectable({
  providedIn: 'root'
})
export class CartService {
  private http = inject(HttpClient);
  
  // 🔥 Backend API Adresi (HTTPS Portu)
  private apiUrl = 'http://localhost:5159/api'; 
  private cartKey = 'partalog_cart';

  // --- STATE MANAGEMENT (Reactive) ---
  
  // 1. Sepet Listesi
  private _cart = new BehaviorSubject<CartItem[]>([]);
  public cart$ = this._cart.asObservable();

  // 2. Toplam Adet (Async Pipe İçin)
  private _totalCount = new BehaviorSubject<number>(0);
  public totalCount$ = this._totalCount.asObservable();

  // 3. Toplam Tutar (Async Pipe İçin)
  private _totalPrice = new BehaviorSubject<number>(0);
  public totalPrice$ = this._totalPrice.asObservable();

  constructor() {
    this.loadCart();
  }

  // --- SEPET İŞLEMLERİ ---

  addToCart(product: CatalogPageItem) {
    const currentCart = this._cart.value;
    
    // Ürün zaten var mı? (ID kontrolü)
    const existingItem = currentCart.find(i => i.product.catalogItemId === product.catalogItemId);

    if (existingItem) {
      existingItem.quantity += 1;
    } else {
      currentCart.push({ product, quantity: 1 });
    }

    this.updateState(currentCart);
  }

  removeFromCart(catalogItemId: string) {
    const currentCart = this._cart.value.filter(i => i.product.catalogItemId !== catalogItemId);
    this.updateState(currentCart);
  }

  updateQuantity(catalogItemId: string, quantity: number) {
    const currentCart = this._cart.value;
    const item = currentCart.find(i => i.product.catalogItemId === catalogItemId);

    if (item) {
      if (quantity <= 0) {
        this.removeFromCart(catalogItemId);
        return;
      }
      item.quantity = quantity;
      this.updateState(currentCart);
    }
  }

  clearCart() {
    this.updateState([]);
  }

  // --- SİPARİŞ GÖNDERME ---

  submitOrder(customerInfo: { name: string; phone: string; email: string; note?: string }) {
    // Backend 'CreateOrderDto' yapısına uygun veri hazırlıyoruz
    const orderData = {
      customerName: customerInfo.name,
      customerPhone: customerInfo.phone,
      customerEmail: customerInfo.email,
      note: customerInfo.note,
      items: this._cart.value.map(i => ({
        // Eğer stokta varsa ProductId, yoksa CatalogItemId veya null (Backend mantığına göre)
        productId: i.product.productId, 
        partCode: i.product.partCode,   
        partName: i.product.partName,
        quantity: i.quantity,
        price: i.product.price || 0
      }))
    };

    return this.http.post(`${this.apiUrl}/orders`, orderData);
  }

  // --- YARDIMCI METODLAR ---

  // Tüm observable'ları ve LocalStorage'ı günceller
  private updateState(cart: CartItem[]) {
    this._cart.next(cart);
    this.calculateTotals(cart);
    this.saveToStorage(cart);
  }

  private calculateTotals(cart: CartItem[]) {
    const count = cart.reduce((acc, item) => acc + item.quantity, 0);
    const price = cart.reduce((acc, item) => acc + (item.quantity * (item.product.price || 0)), 0);

    this._totalCount.next(count);
    this._totalPrice.next(price);
  }

  // LocalStorage İşlemleri
  private saveToStorage(cart: CartItem[]) {
    localStorage.setItem(this.cartKey, JSON.stringify(cart));
  }

  private loadCart() {
    const saved = localStorage.getItem(this.cartKey);
    if (saved) {
      try {
        const cart = JSON.parse(saved);
        this._cart.next(cart);
        this.calculateTotals(cart);
      } catch (e) {
        console.error('Sepet verisi bozuk, sıfırlanıyor.', e);
        this.clearCart();
      }
    }
  }
}