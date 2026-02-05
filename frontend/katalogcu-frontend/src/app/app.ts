import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, Router, NavigationEnd } from '@angular/router';
import { HeaderComponent } from './layout/header/header';
import { filter } from 'rxjs/operators';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, HeaderComponent],
  template: `
    @if (showHeader) {
      <app-header></app-header>
      <main class="flex w-full flex-col items-center">
          <router-outlet></router-outlet>
      </main>
    } 
    @else {
      <router-outlet></router-outlet>
    }
  `,
  styleUrl: './app.css'
})
export class AppComponent {
  showHeader = true;

  constructor(private router: Router) {
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: any) => {
      
      const url = event.urlAfterRedirects;
      
      // 👇 DÜZELTİLEN MANTIK: '/public-view' rotası da buraya eklendi.
      // Artık bu sayfalarda HeaderComponent gizlenecek.
      if (
          url.startsWith('/dashboard') || 
          url.startsWith('/view') || 
          url.startsWith('/public-view')
         ) {
        this.showHeader = false;
      } else {
        this.showHeader = true;
      }
      
    });
  }
}