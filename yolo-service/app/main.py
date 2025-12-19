from ultralytics import YOLO
import cv2

# Modeli yükle
model = YOLO("best.pt")

# Resmi yükle (OpenCV ile)
resim_yolu = "test7.jpg"
img = cv2.imread(resim_yolu)

# Tahmin yap (conf=0.35 diyerek çok emin olmadıklarını eledik)
results = model(resim_yolu, conf=0.35)

# Sonuçları kendimiz, incecik çizelim
sayac = 0
for result in results:
    for box in result.boxes:
        # Koordinatları al (Tam sayıya çevir)
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        
        # Sadece Kırmızı İnce Kutu Çiz (Yazı yazma)
        # (0, 0, 255) -> Kırmızı, 1 -> Çizgi Kalınlığı
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 1)
        sayac += 1

# Resmi kaydet
cv2.imwrite("temiz_sonuc7.jpg", img)

print(f"Toplam {sayac} adet kutu çizildi.")
print("Lütfen 'temiz_sonuc7.jpg' dosyasına bak.")