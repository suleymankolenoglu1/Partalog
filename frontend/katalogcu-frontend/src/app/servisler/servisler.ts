import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-servisler',
  standalone: true,
  imports: [CommonModule],
  // 👇 Dosya isimlerin Türkçe olduğu için burası değişti
  templateUrl: './servisler.html',
  styleUrl: './servisler.css'
})
export class ServislerComponent {
  // Class ismini de ServislerComponent yaptık
}