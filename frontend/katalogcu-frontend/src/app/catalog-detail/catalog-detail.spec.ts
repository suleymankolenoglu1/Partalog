import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CatalogDetail } from './catalog-detail';

describe('CatalogDetail', () => {
  let component: CatalogDetail;
  let fixture: ComponentFixture<CatalogDetail>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CatalogDetail]
    })
    .compileComponents();

    fixture = TestBed.createComponent(CatalogDetail);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
