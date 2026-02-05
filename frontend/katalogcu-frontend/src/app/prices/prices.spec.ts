import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Prices } from './prices';

describe('Prices', () => {
  let component: Prices;
  let fixture: ComponentFixture<Prices>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Prices]
    })
    .compileComponents();

    fixture = TestBed.createComponent(Prices);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
