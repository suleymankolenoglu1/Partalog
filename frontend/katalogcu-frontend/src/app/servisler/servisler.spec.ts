import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Servisler } from './servisler';

describe('Servisler', () => {
  let component: Servisler;
  let fixture: ComponentFixture<Servisler>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Servisler]
    })
    .compileComponents();

    fixture = TestBed.createComponent(Servisler);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
