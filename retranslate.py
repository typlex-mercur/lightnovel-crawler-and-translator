import os
import glob
from translate_chapters import translate_chapter, load_resources, get_translation_memory_examples

d = r'd:\Somecodes\lightnovel-translator\translated_chapters'
files = glob.glob(os.path.join(d, 'chapter_*.txt'))
short_files = []
for f in sorted(files):
    size = os.path.getsize(f)
    if size < 10000:
        num = int(os.path.basename(f).replace('chapter_', '').replace('.txt', ''))
        short_files.append(num)

print(f"Các chương cần dịch lại: {short_files}")

style_guide, glossary, tm_pairs = load_resources()

for ch_num in short_files:
    print(f"\n--- DỊCH LẠI CHƯƠNG {ch_num} ---")
    raw_file = os.path.join(r"d:\Somecodes\lightnovel-translator\raw_chapters", f"chapter_{ch_num:03d}.txt")
    out_file = os.path.join(d, f"chapter_{ch_num:03d}.txt")
    
    with open(raw_file, "r", encoding="utf-8") as f:
        raw_text = f.read().strip()
        
    print("Đang dịch...")
    translated, error = translate_chapter(raw_text, style_guide, glossary, tm_pairs)
    if error:
        print(f"FAIL: {error}")
    else:
        # Giữ title
        title_line = raw_text.split('\n')[0] if raw_text.startswith('#') else f"Chương {ch_num}"
        if not translated.startswith('#'):
            translated = f"{title_line}\n\n{translated}"
            
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(translated)
        print(f"OK ({len(translated)} chars)")
