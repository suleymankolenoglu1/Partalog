import { Routes } from '@angular/router';

// Public Components
import { HomeComponent } from './home/home.component';
import { ExploreComponent } from './explore/explore';
import { BlogComponent } from './blog/blog';
import { ServislerComponent } from './servisler/servisler';
import { PricesComponent } from './prices/prices';
import { LoginComponent } from './login/login';
import { RegisterComponent } from './register/register';
import { PublicViewComponent } from './public-view/public-view';

// 👇 YENİ COMPONENTLERİMİZ (Showcase ve Viewer)
import { PublicCatalogShowcaseComponent } from './public-catalog-showcase/public-catalog-showcase';
import { PublicCatalogViewerComponent } from './public-view/public-catalog-viewer/public-catalog-viewer';

// Admin Components
import { AdminLayoutComponent } from './layout/admin-layout/admin-layout';
import { DashboardComponent } from './dashboard/dashboard';
import { CatalogDetailComponent } from './catalog-detail/catalog-detail';
import { CatalogsComponent } from './dashboard/catalogs/catalogs';
import { PartsComponent } from './dashboard/parts/parts';
import { CustomersComponent } from './dashboard/customers/customers';
import { SettingsComponent } from './dashboard/settings/settings';
import { CatalogAddComponent } from './dashboard/catalogs/catalog-add/catalog-add';
import { PartsAddComponent } from './dashboard/parts/parts-add/parts-add';
import { PartsImportComponent } from './dashboard/parts/parts-import/parts-import';

export const routes: Routes = [
  // --- PUBLIC SAYFALAR (Müşteri Tarafı) ---
  
  { path: '', component: HomeComponent },
  
  // 1. Katalog Listesi (Arama Ekranı)
  { path: 'public-view/:userId', component: PublicViewComponent },
  
  // 2. Katalog Vitrini (Kutu kutu gruplar)
  { path: 'view/:id', component: PublicCatalogShowcaseComponent },

  // 3. Profesyonel Görüntüleyici (Teknik Resim & Tablo)
  { path: 'view/:id/viewer/:pageIndex', component: PublicCatalogViewerComponent },

  // Diğer Sayfalar
  { path: 'explore', component: ExploreComponent },
  { path: 'blog', component: BlogComponent },
  { path: 'services', component: ServislerComponent },
  { path: 'prices', component: PricesComponent },
  { path: 'login', component: LoginComponent },
  { path: 'register', component: RegisterComponent },
  
  // --- ADMIN PANELİ ---
  {
    path: 'dashboard',
    component: AdminLayoutComponent,
    children: [
      { path: '', component: DashboardComponent },
      { path: 'catalogs', component: CatalogsComponent },
      { path: 'catalog/:id', component: CatalogDetailComponent }, // Admin detay sayfası
      { path: 'catalogs/new', component: CatalogAddComponent },
      
      { path: 'customers', component: CustomersComponent },
      { path: 'settings', component: SettingsComponent },
      { path: 'parts', component: PartsComponent },
      { path: 'parts/new', component: PartsAddComponent },
      { path: 'parts/import', component: PartsImportComponent }
    ]
  }
];