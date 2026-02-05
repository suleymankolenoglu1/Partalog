import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PublicCatalogShowcase } from './public-catalog-showcase';

describe('PublicCatalogShowcase', () => {
  let component: PublicCatalogShowcase;
  let fixture: ComponentFixture<PublicCatalogShowcase>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PublicCatalogShowcase]
    })
    .compileComponents();

    fixture = TestBed.createComponent(PublicCatalogShowcase);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
