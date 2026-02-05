import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PublicCatalogViewer } from './public-catalog-viewer';

describe('PublicCatalogViewer', () => {
  let component: PublicCatalogViewer;
  let fixture: ComponentFixture<PublicCatalogViewer>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PublicCatalogViewer]
    })
    .compileComponents();

    fixture = TestBed.createComponent(PublicCatalogViewer);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
