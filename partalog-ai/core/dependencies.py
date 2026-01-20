# core/dependencies.py

# Global değişkeni burada tutuyoruz
global_ai_engine = None

def get_ai_engine():
    """
    API endpoint'lerinin motoru çağırmak için kullanacağı fonksiyon.
    """
    if global_ai_engine is None:
        raise RuntimeError("AI Motoru henüz başlatılmadı veya hazır değil!")
    return global_ai_engine

def set_ai_engine(engine):
    """
    Main.py başlatılırken motoru buraya kaydetmek için kullanılır.
    """
    global global_ai_engine
    global_ai_engine = engine