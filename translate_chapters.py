"""
translate_chapters.py – Phase 2: Dịch chương 101-216 bằng Gemini AI
Sử dụng Style Guide + Translation Memory + Glossary để đảm bảo consistency.
"""
import os
import sys
import json
import time
import math
import numpy as np

os.environ["PYTHONUTF8"] = "1"
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from google import genai
from google.genai import types
from google.genai.errors import APIError

# ==========================================
# CẤU HÌNH
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(SCRIPT_DIR, "raw_chapters")
TRANSLATED_DIR = os.path.join(SCRIPT_DIR, "translated_chapters")
STYLE_GUIDE_FILE = os.path.join(SCRIPT_DIR, "style_guide.txt")
TM_FILE = os.path.join(SCRIPT_DIR, "translation_memory.json")
GLOSSARY_FILE = os.path.join(SCRIPT_DIR, "glossary.json")
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "translate_progress.txt")

API_KEYS_FILE = os.environ.get("GEMINI_API_KEYS_FILE", "D:/Somecodes/API/api_keys.txt")
TRANSLATE_MODEL = "gemini-3.5-flash"
EMBEDDING_MODEL = "gemini-embedding-2"

START_CHAPTER = 262
END_CHAPTER = 262
TM_TOP_N = 6  # Số cặp TM tương tự nhất để đưa vào prompt
TM_MAX_PER_CHAPTER = 2  # Tối đa 2 cặp từ cùng 1 chương mẫu

SAFETY_SETTINGS = [
    types.SafetySetting(category=c, threshold=types.HarmBlockThreshold.BLOCK_NONE)
    for c in [
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    ]
]


def load_api_keys():
    with open(API_KEYS_FILE, "r", encoding="utf-8") as f:
        keys = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    return [k for k in keys if len(k) > 30]


API_KEYS = load_api_keys()
_key_index = 0
_client_cache = {}


def get_client():
    global _key_index
    key = API_KEYS[_key_index]
    if key not in _client_cache:
        _client_cache[key] = genai.Client(api_key=key)
    return _client_cache[key]


def rotate_key():
    global _key_index
    _key_index = (_key_index + 1) % len(API_KEYS)


# ==========================================
# LOAD RESOURCES
# ==========================================
def load_style_guide():
    if not os.path.exists(STYLE_GUIDE_FILE):
        return "Dịch light novel EN→VN, giữ nguyên tên riêng, văn phong tự nhiên."
    with open(STYLE_GUIDE_FILE, "r", encoding="utf-8") as f:
        return f.read()


def load_translation_memory():
    if not os.path.exists(TM_FILE):
        return {"pairs": []}
    with open(TM_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_glossary():
    if not os.path.exists(GLOSSARY_FILE):
        return {"entries": []}
    with open(GLOSSARY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_glossary(glossary):
    with open(GLOSSARY_FILE, "w", encoding="utf-8") as f:
        json.dump(glossary, f, ensure_ascii=False, indent=2)


# ==========================================
# TRANSLATION MEMORY SEARCH
# ==========================================
def cosine_similarity(a, b):
    """Tính cosine similarity giữa 2 vectors."""
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def find_similar_tm_pairs(chapter_text, tm_data, top_n=TM_TOP_N):
    """Tìm top-N cặp TM tương tự nhất với chapter text."""
    pairs = tm_data.get("pairs", [])
    if not pairs:
        return []

    # Embed chapter text
    client = get_client()
    try:
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[chapter_text[:3000]],  # Truncate
        )
        query_embedding = result.embeddings[0].values
    except Exception as e:
        print(f"  [!] Lỗi embedding: {e}")
        rotate_key()
        return []

    # Tính similarity với tất cả TM pairs
    scored = []
    for pair in pairs:
        emb = pair.get("embedding", [])
        if not emb:
            continue
        sim = cosine_similarity(query_embedding, emb)
        scored.append((sim, pair))

    # Sort theo similarity giảm dần
    scored.sort(key=lambda x: x[0], reverse=True)

    # Lấy top-N, đa dạng hóa (max 2 cặp từ cùng 1 chương)
    selected = []
    chapter_counts = {}
    for sim, pair in scored:
        ch = pair.get("chapter", 0)
        if chapter_counts.get(ch, 0) >= TM_MAX_PER_CHAPTER:
            continue
        selected.append(pair)
        chapter_counts[ch] = chapter_counts.get(ch, 0) + 1
        if len(selected) >= top_n:
            break

    return selected


# ==========================================
# TRANSLATE 1 CHAPTER
# ==========================================
def translate_chapter(raw_text, style_guide, glossary, tm_pairs, retry_count=0):
    """Dịch 1 chương raw EN → VN."""
    max_retries = len(API_KEYS) * 2
    if retry_count >= max_retries:
        return None, "Đã thử hết keys"

    # Build glossary section
    glossary_text = ""
    entries = glossary.get("entries", [])
    if entries:
        glossary_lines = []
        for e in entries:
            name_en = e.get("name_en", "")
            name_vi = e.get("name_vi", name_en)
            identity = e.get("identity", "")
            if name_en != name_vi:
                glossary_lines.append(f"- {name_en} → {name_vi}: {identity}")
            else:
                glossary_lines.append(f"- {name_en}: {identity}")
        glossary_text = "\n".join(glossary_lines)

    # Build TM examples section
    tm_text = ""
    if tm_pairs:
        tm_examples = []
        for i, pair in enumerate(tm_pairs, 1):
            tm_examples.append(
                f"--- Ví dụ {i} ---\n"
                f"[EN]: {pair['en'][:800]}\n"
                f"[VN]: {pair['vi'][:800]}"
            )
        tm_text = "\n\n".join(tm_examples)

    prompt = f"""[HƯỚNG DẪN DỊCH]
{style_guide}

[BẢNG THUẬT NGỮ & NHÂN VẬT]
{glossary_text if glossary_text else "(Chưa có)"}

[VÍ DỤ DỊCH THAM KHẢO - Hãy bắt chước văn phong này]
{tm_text if tm_text else "(Không có ví dụ)"}

[CHƯƠNG CẦN DỊCH]
{raw_text}

[YÊU CẦU]
- DỊCH TOÀN BỘ NỘI DUNG, TỪ ĐẦU ĐẾN CUỐI, KHÔNG SÓT MỘT TỪ NÀO.
- Bắt chước chính xác văn phong và cách dịch trong các ví dụ tham khảo
- Giữ nguyên tên riêng tiếng Anh (nhân vật, địa danh)
- Giữ nguyên các thuật ngữ đặc biệt (Aura, Mana, etc.)
- Không bỏ sót đoạn nào, dịch đầy đủ
- Không thêm chú thích hoặc giải thích
- CHỈ trả về bản dịch tiếng Việt, không kèm gì khác"""

    client = get_client()
    try:
        response = client.models.generate_content(
            model=TRANSLATE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=SAFETY_SETTINGS,
                temperature=0.3,
            )
        )

        if not response.candidates or not response.candidates[0].content.parts:
            return None, "Safety block (No candidates)"

        return response.text, None

    except ValueError as e:
        # ValueError thường bị văng khi response.text bị gọi trên content bị block
        return None, f"Lỗi nội dung/Safety block: {e}"

    except APIError as e:
        error_str = str(e).lower()
        backoff = min(2 ** retry_count, 30)

        if any(kw in error_str for kw in ["quota", "429", "403", "exhausted"]):
            rotate_key()
            time.sleep(backoff)
            return translate_chapter(raw_text, style_guide, glossary, tm_pairs, retry_count + 1)

        if any(kw in error_str for kw in ["overloaded", "503", "500"]):
            time.sleep(backoff)
            return translate_chapter(raw_text, style_guide, glossary, tm_pairs, retry_count + 1)

        return None, f"API Error: {e}"

    except Exception as e:
        backoff = min(2 ** retry_count, 30)
        rotate_key()
        time.sleep(backoff)
        return translate_chapter(raw_text, style_guide, glossary, tm_pairs, retry_count + 1)


# ==========================================
# UPDATE GLOSSARY (detect new terms)
# ==========================================
def detect_new_terms(raw_text, translated_text, glossary, chapter_num):
    """Dùng AI phát hiện tên mới cần thêm vào glossary."""
    existing_names = {e.get("name_en", "").lower() for e in glossary.get("entries", [])}

    prompt = f"""Đọc đoạn truyện EN và bản dịch VN bên dưới.
Liệt kê các NHÂN VẬT, THẾ LỰC, hoặc ĐỊA DANH MỚI xuất hiện lần đầu trong chương này.

CHỈ liệt kê những tên QUAN TRỌNG, có vai trò trong cốt truyện.
KHÔNG liệt kê thuật ngữ phổ biến (Aura, Mana, Sword, Knight...).
KHÔNG liệt kê tên đã có: {', '.join(e.get('name_en','') for e in glossary.get('entries', [])[:30])}

QUY TẮC VỀ MÔ TẢ (identity):
- PHẢI viết bằng tiếng Việt, KHÔNG dùng tiếng Anh.
- Mô tả KHÁCH QUAN về bản thân nhân vật/địa danh: ngoại hình, xuất thân, chức vụ, đặc điểm nhận diện.
- KHÔNG mô tả hành động nhân vật làm trong chương (VD: "người đã tặng X cho Y" là SAI).
- KHÔNG mô tả mối quan hệ với nhân vật khác trừ khi đó là đặc điểm nhận diện chính (VD: "con trai của X" là OK nếu đó là thông tin quan trọng).
- VÍ DỤ ĐÚNG: "Thiếu niên tóc vàng xuất thân từ khu ổ chuột, có tài năng kiếm thuật"
- VÍ DỤ ĐÚNG: "Hiệp sĩ trẻ tuổi thuộc Đội Diệt Rồng, con trai Công tước Dragulia"
- VÍ DỤ ĐÚNG: "Thành phố cảng phía Tây, trung tâm thương mại quan trọng"
- VÍ DỤ SAI: "Người đã cung cấp thông tin cho nhóm của Vlad"
- VÍ DỤ SAI: "A man who confronts Vlad with an arrest warrant"

[EN]:
{raw_text[:3000]}

[VN]:
{translated_text[:3000]}

Trả về JSON. Nếu không có tên mới, trả về {{"new_entries": []}}
{{
  "new_entries": [
    {{
      "name_en": "tên EN",
      "name_vi": "tên VN (giữ nguyên nếu là tên riêng)",
      "identity": "mô tả khách quan bằng tiếng Việt: ngoại hình, xuất thân, chức vụ",
      "type": "character|faction|location"
    }}
  ]
}}"""

    client = get_client()
    try:
        response = client.models.generate_content(
            model=TRANSLATE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=SAFETY_SETTINGS,
                response_mime_type="application/json",
                temperature=0.1,
            )
        )
        result = json.loads(response.text)
        new_entries = result.get("new_entries", [])
        added = 0
        for entry in new_entries:
            name = entry.get("name_en", "").lower()
            if name and name not in existing_names:
                entry["first_seen"] = chapter_num
                glossary.setdefault("entries", []).append(entry)
                existing_names.add(name)
                added += 1
        if added:
            save_glossary(glossary)
            print(f"  [GLOSSARY] +{added} entries mới")
    except Exception as e:
        # Non-critical, bỏ qua
        pass


# ==========================================
# MAIN PIPELINE
# ==========================================
def main():
    os.makedirs(TRANSLATED_DIR, exist_ok=True)

    print("=" * 50)
    print("=== PHASE 2: TRANSLATE CHAPTERS ===")
    print("=" * 50)

    # Load resources
    print("[*] Loading resources...")
    style_guide = load_style_guide()
    tm_data = load_translation_memory()
    glossary = load_glossary()

    tm_pair_count = len(tm_data.get("pairs", []))
    glossary_count = len(glossary.get("entries", []))
    print(f"  Style Guide: {len(style_guide)} chars")
    print(f"  Translation Memory: {tm_pair_count} pairs")
    print(f"  Glossary: {glossary_count} entries")

    # Check prerequisites
    if not os.path.exists(STYLE_GUIDE_FILE):
        print("[!] Chưa có style_guide.txt - chạy preprocess.py trước!")
        return

    # Load progress
    start_chapter = START_CHAPTER
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            saved = f.read().strip()
            if saved.isdigit():
                start_chapter = max(START_CHAPTER, int(saved) + 1)

    print(f"\n[*] Bắt đầu dịch từ chương {start_chapter} đến {END_CHAPTER}")

    for ch_num in range(start_chapter, END_CHAPTER + 1):
        raw_file = os.path.join(RAW_DIR, f"chapter_{ch_num:03d}.txt")
        out_file = os.path.join(TRANSLATED_DIR, f"chapter_{ch_num:03d}.txt")

        # Skip nếu đã dịch
        if os.path.exists(out_file) and os.path.getsize(out_file) > 100:
            continue

        # Kiểm tra raw
        if not os.path.exists(raw_file):
            print(f"  [{ch_num}] Raw không tồn tại, bỏ qua")
            continue

        with open(raw_file, "r", encoding="utf-8") as f:
            raw_text = f.read()

        print(f"\n--- CHƯƠNG {ch_num}/{END_CHAPTER} ---")
        print(f"  Raw: {len(raw_text)} chars")

        # Tìm TM pairs tương tự
        print(f"  Đang tìm Translation Memory tương tự...", end=" ", flush=True)
        tm_pairs = find_similar_tm_pairs(raw_text, tm_data)
        print(f"→ {len(tm_pairs)} cặp")

        # Dịch
        print(f"  Đang dịch...", end=" ", flush=True)
        translated, error = translate_chapter(raw_text, style_guide, glossary, tm_pairs)

        if error:
            print(f"FAIL: {error}")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(f"# Lỗi dịch Chương {ch_num}\n\n[API Error: {error}] - Vui lòng tự dịch tay hoặc thử lại sau.")
            # Lưu progress và tiếp tục
            with open(PROGRESS_FILE, "w") as f:
                f.write(str(ch_num))
            continue

        # Lưu bản dịch
        # Giữ title từ raw (dòng đầu tiên nếu bắt đầu bằng #)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(translated)
        print(f"OK ({len(translated)} chars)")

        # Phát hiện thuật ngữ mới (non-blocking)
        detect_new_terms(raw_text, translated, glossary, ch_num)

        # Lưu progress
        with open(PROGRESS_FILE, "w") as f:
            f.write(str(ch_num))

    print(f"\n{'=' * 50}")
    print("[*] DỊCH HOÀN TẤT!")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
