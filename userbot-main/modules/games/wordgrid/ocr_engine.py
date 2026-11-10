import easyocr
import os, gc

# 'en' model load karo. Pehli baar mein ye model download karega (100MB approx).
reader = easyocr.Reader(['en'], gpu=False)

def extract_grid(image_path):
    try:
        if not os.path.exists(image_path): return None
        
        # EasyOCR direct image path se read karta hai
        results = reader.readtext(image_path, detail=0)
        
        # Grid format mein convert karo
        matrix = []
        for line in results:
            # Sirf letters rakho
            row = [c.upper() for c in line if c.isalpha()]
            # Grid width check (assume 8x8 or 6x6 based on your images)
            if len(row) >= 5: 
                matrix.append(row)
        
        # Agar bot ne lines alag-alag read ki hain, toh matrix ban jayega
        return matrix if len(matrix) >= 5 else None
    except Exception:
        return None
    finally:
        if os.path.exists(image_path): os.remove(image_path)
        gc.collect()
