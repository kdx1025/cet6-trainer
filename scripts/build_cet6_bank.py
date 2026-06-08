import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "tmp" / "cet6_source_pdfs"
CACHE_DIR = ROOT / "tmp" / "cet6_text_cache"
OUTPUT = ROOT / "cet6_2019_2025_practice.json"


SECTION_LABELS = {
    "cloze": "选词填空",
    "reading": "阅读理解",
    "translation": "汉翻英",
}


def log(message):
    print(message, flush=True)


def clean_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\n?\s*(?:\d{4}\.\d{1,2}|六\s*级\s*\d{4}\.\d).*?(?:第\s*\d+\s*页|共\s*\d+\s*页).*?\n", "\n", text)
    return text.strip()


def pdf_text_layer(pdf_path):
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
    return clean_text("\n".join(parts))


def ocr_pages(pdf_path, page_indexes):
    import numpy as np
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    pdf = pdfium.PdfDocument(str(pdf_path))
    chunks = []
    for idx in page_indexes:
        if idx < 0 or idx >= len(pdf):
            continue
        bitmap = pdf[idx].render(scale=1.3).to_pil().convert("RGB")
        result, _ = ocr(np.array(bitmap))
        lines = [line[1] for line in result] if result else []
        chunks.append(f"\n\n[[PAGE {idx + 1}]]\n" + "\n".join(lines))
    return clean_text("\n".join(chunks))


def cached_text(pdf_path, force_answer_ocr=False):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{pdf_path.stem}.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    text = pdf_text_layer(pdf_path)
    is_answer = pdf_path.stem.endswith("_ans")

    if is_answer:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(pdf_path))
        page_count = len(pdf)
        # Some books put a quick key on the final page; others only list answers
        # inside Reading explanations, usually in the final half of the PDF.
        last_pages = list(range(max(0, page_count - 12), page_count))
        ocr_text = ocr_pages(pdf_path, last_pages)
        text = clean_text(text + "\n\n" + ocr_text)
    elif len(text) < 1000:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(pdf_path))
        text = ocr_pages(pdf_path, range(len(pdf)))

    cache_path.write_text(text, encoding="utf-8")
    return text


def parse_meta(path):
    match = re.match(r"cet6_(\d{4})_(\d{2})_(.+?)(?:_ans)?$", path.stem)
    if not match:
        return None
    year, month, set_id = match.groups()
    return {
        "year": year,
        "month": month,
        "set": set_id,
        "paper": f"{year}-{month} 第{set_id}套",
        "base": f"cet6_{year}_{month}_{set_id}",
    }


def between(text, start_pattern, end_pattern=None, flags=re.I | re.S):
    start = re.search(start_pattern, text, flags)
    if not start:
        return ""
    rest = text[start.end() :]
    if end_pattern:
        end = re.search(end_pattern, rest, flags)
        if end:
            rest = rest[: end.start()]
    return rest.strip()


def normalize_letter(letter, for_word_bank=False):
    value = (letter or "").strip().upper()
    if for_word_bank:
        if value in {"0", "O"}:
            return "O"
        if value in {"1", "I"}:
            return "I"
    return value


def number_markers(text, number):
    token = str(number)
    pos = 0
    while True:
        pos = text.find(token, pos)
        if pos == -1:
            break
        before = text[pos - 1] if pos > 0 else ""
        after_pos = pos + len(token)
        after_scan = after_pos
        while after_scan < len(text) and text[after_scan].isspace():
            after_scan += 1
        after = text[after_scan] if after_scan < len(text) else ""
        if not before.isdigit() and after in ".、)）【":
            yield pos, after_scan + 1
        pos += len(token)


def answer_value_from_block(block):
    explicit = re.search(r"[【\[]\s*答案\s*[】\]\s]*([A-O0-1])", block, re.I)
    if explicit:
        return explicit.group(1).upper()

    markers = ("判断", "定位", "考点", "解析", "精析", "事实", "细节", "推理", "答案")
    for line in block.splitlines()[:14]:
        stripped = line.strip()
        if len(stripped) >= 2 and stripped[0].upper() in "ABCDEFGHIJKLMNO01" and stripped[1] in ")）":
            if any(marker in stripped for marker in markers):
                return stripped[0].upper()
    return None


def parse_answer_key(answer_text):
    key = {}
    source = answer_text
    quick = re.search(r"答案速查|Reading\s*Comprehension|Part\s*III", answer_text, re.I)
    if quick:
        source = answer_text[quick.start() :]

    for match in re.finditer(r"(?<!\d)([2-5]\d)\s*[\.\)]\s*([A-O0-1])", source, re.I):
        number = int(match.group(1))
        if 26 <= number <= 45:
            key[number] = normalize_letter(match.group(2), for_word_bank=True)
        elif 46 <= number <= 55:
            value = normalize_letter(match.group(2))
            if value in {"A", "B", "C", "D"}:
                key[number] = value

    for match in re.finditer(r"(?<!\d)([2-5]\d)\s*[\.\)、]?\s*[【\[]?\s*答案\s*[】\]\s]*([A-O0-1])", source, re.I):
        number = int(match.group(1))
        if 26 <= number <= 45:
            key[number] = normalize_letter(match.group(2), for_word_bank=True)
        elif 46 <= number <= 55:
            value = normalize_letter(match.group(2))
            if value in {"A", "B", "C", "D"}:
                key[number] = value

    for number in range(26, 56):
        candidates = []
        for start_pos, content_pos in number_markers(source, number):
            next_positions = list(number_markers(source[content_pos:], number + 1))
            block_end = content_pos + (next_positions[0][0] if next_positions else 900)
            block = source[content_pos:block_end]
            prefix = block[:100]
            score = 0
            value = answer_value_from_block(block)
            if value and "答案" in block[:160]:
                score += 6
            elif value:
                score += 4
            if value:
                if any(marker in prefix for marker in ("考点", "定位", "答案")):
                    score += 8
                candidates.append((score, value))
        value = max(candidates, default=(0, None))[1]
        if not value:
            continue
        if 26 <= number <= 45:
            key[number] = normalize_letter(value, for_word_bank=True)
        else:
            answer_value = normalize_letter(value)
            if answer_value in {"A", "B", "C", "D"}:
                key[number] = answer_value
    return key


def parse_word_bank(section_text):
    options = {}
    # Restrict to the tail to avoid matching option labels from directions.
    tail = section_text[-1800:]
    for match in re.finditer(r"(?<![A-Za-z])([A-O0-1])\)\s*([A-Za-z][A-Za-z'’-]+)", tail, re.I):
        key = normalize_letter(match.group(1), for_word_bank=True)
        word = match.group(2).strip(" .;:,")
        if key and word and key not in options:
            options[key] = word
    return dict(sorted(options.items()))


def strip_section_a_directions(section_text):
    markers = [
        "than once.",
        "thanonce.",
        "through the centre.",
        "through thecentre.",
    ]
    lower = section_text.lower()
    cut = 0
    for marker in markers:
        pos = lower.find(marker.lower())
        if pos != -1:
            cut = max(cut, pos + len(marker))
    return section_text[cut:].strip()


def remove_word_bank_from_passage(section_text, options):
    first_positions = []
    for key, word in options.items():
        for label in [key, "0" if key == "O" else key]:
            match = re.search(rf"(?<![A-Za-z]){re.escape(label)}\)\s*{re.escape(word[:4])}", section_text, re.I)
            if match:
                first_positions.append(match.start())
    if first_positions:
        return section_text[: min(first_positions)].strip()
    return section_text.strip()


def answer_explanation(answer_text, number):
    next_number = number + 1
    pattern = rf"(?s)(?:^|\n)\s*{number}\s*[\.\)、]?\s*(.*?)(?=(?:\n\s*{next_number}\s*[\.\)、])|\n\s*词汇分析|\n\s*Section|\n\s*Passage\s+\w+|\n\s*Part\s*IV|\Z)"
    match = re.search(pattern, answer_text, re.I)
    if not match:
        return ""
    return clean_text(match.group(0))[:1500]


def reading_part(question_text):
    part = between(
        question_text,
        r"Reading\s*Comprehension\s*\(40\s*minutes\)",
        r"(?:Part\s*IV\s*)?Translation\s*\(30\s*minutes\)|Part\s*IV\s*Translation",
    )
    if part:
        return part
    return between(question_text, r"Reading\s*Comprehension", r"(?:Part\s*IV\s*)?Translation|Part\s*IV")


def parse_section_a(question_text, answer_key, answer_text, meta):
    part_iii = reading_part(question_text)
    section = between(part_iii, r"Section\s*A", r"Section\s*B")
    if not section:
        return []

    content = strip_section_a_directions(section)
    word_bank = parse_word_bank(content)
    if len(word_bank) < 10:
        return []

    passage = remove_word_bank_from_passage(content, word_bank)
    passage = re.sub(r"\n\s*", "\n", passage).strip()

    options = [{"key": key, "text": value} for key, value in word_bank.items()]
    questions = []
    for number in range(26, 36):
        answer = answer_key.get(number)
        if not answer:
            continue
        answer_word = word_bank.get(answer, "")
        explanation = answer_explanation(answer_text, number)
        if not explanation:
            explanation = f"本题答案来自 {meta['paper']} 答案速查。选项 {answer} 对应单词 {answer_word}。"
        questions.append(
            {
                "id": f"{meta['base']}-cloze-{number}",
                "type": "choice",
                "section": "cloze",
                "source": meta["paper"],
                "stem": f"选词填空：第 {number} 空应选择哪个单词？",
                "passage": passage,
                "options": options,
                "answer": answer,
                "explanation": explanation,
            }
        )
    return questions


def strip_section_c_directions(section_text):
    markers = [
        "Question Sheet 2.",
        "Answer Sheet 2.",
        "through the centre.",
        "through thecentre.",
    ]
    lower = section_text.lower()
    cut = 0
    for marker in markers:
        pos = lower.find(marker.lower())
        if pos != -1:
            cut = max(cut, pos + len(marker))
    return section_text[cut:].strip()


def parse_mc_block(block, start_number, end_number):
    items = []
    for number in range(start_number, end_number + 1):
        start = re.search(rf"(?m)^\s*{number}\s*[\.\)]\s*", block)
        if not start:
            start = re.search(rf"(?<!\d){number}\s*[\.\)]\s*", block)
        if not start:
            continue
        next_start = re.search(rf"(?m)^\s*{number + 1}\s*[\.\)]\s*", block[start.end() :])
        raw = block[start.end() :]
        if next_start:
            raw = raw[: next_start.start()]
        option_matches = list(re.finditer(r"(?<![A-Za-z])([A-D])\)\s*", raw))
        if len(option_matches) < 4:
            continue
        stem = raw[: option_matches[0].start()].strip()
        options = []
        for idx, match in enumerate(option_matches[:4]):
            end = option_matches[idx + 1].start() if idx + 1 < len(option_matches[:4]) else len(raw)
            text = raw[match.end() : end].strip()
            text = re.sub(r"\s+", " ", text)
            options.append({"key": match.group(1).upper(), "text": text})
        options = sorted(options, key=lambda item: item["key"])
        items.append({"number": number, "stem": clean_text(stem), "options": options})
    return items


def parse_section_c(question_text, answer_key, answer_text, meta):
    part_iii = reading_part(question_text)
    section = between(part_iii, r"Section\s*C", None)
    if not section:
        return []
    section = strip_section_c_directions(section)

    chunks = []
    ranges = [(46, 50), (51, 55)]
    for idx, (start_q, end_q) in enumerate(ranges):
        start_pattern = rf"Questions?\s+{start_q}\s+to\s+{end_q}"
        start = re.search(start_pattern, section, re.I)
        if not start:
            # Some PDFs omit the "Questions x to y" line.
            start = re.search(rf"(?<!\d){start_q}\s*[\.\)]", section)
        if not start:
            continue
        chunk = section[start.end() :]
        if idx + 1 < len(ranges):
            next_q = ranges[idx + 1][0]
            next_start = re.search(
                rf"Questions?\s+{next_q}\s+to\s+{ranges[idx + 1][1]}|^\s*{next_q}\s*[\.\)]",
                chunk,
                re.I | re.M,
            )
            if next_start:
                chunk = chunk[: next_start.start()]
        question_start = re.search(rf"(?m)^\s*{start_q}\s*[\.\)]\s*", chunk)
        if not question_start:
            question_start = re.search(rf"(?<!\d){start_q}\s*[\.\)]\s*", chunk)
        if not question_start:
            continue
        passage = clean_text(chunk[: question_start.start()])
        block = chunk[question_start.start() :]
        chunks.append((start_q, end_q, passage, block))

    questions = []
    for start_q, end_q, passage, block in chunks:
        for item in parse_mc_block(block, start_q, end_q):
            answer = answer_key.get(item["number"])
            if not answer:
                continue
            explanation = answer_explanation(answer_text, item["number"])
            if not explanation:
                explanation = f"本题答案来自 {meta['paper']} 答案速查。"
            questions.append(
                {
                    "id": f"{meta['base']}-reading-{item['number']}",
                    "type": "choice",
                    "section": "reading",
                    "source": meta["paper"],
                    "stem": item["stem"],
                    "passage": passage,
                    "options": item["options"],
                    "answer": answer,
                    "explanation": explanation,
                }
            )
    return questions


def parse_translation_prompt(question_text):
    part = between(question_text, r"Part\s*IV\s*.*?Translation", None)
    if not part:
        part = between(question_text, r"Translation", None)
    if not part:
        return ""
    markers = ["Answer Sheet 2.", "AnswerSheet2.", "answer on Answer Sheet 2"]
    lower = part.lower()
    cut = 0
    for marker in markers:
        pos = lower.find(marker.lower())
        if pos != -1:
            cut = max(cut, pos + len(marker))
    prompt = part[cut:].strip()
    prompt = re.sub(r"(?is)For this part.*?Answer Sheet 2\.?", "", prompt).strip()
    prompt = re.sub(r"\n+", "\n", prompt)
    return clean_text(prompt)


def parse_translation_reference(answer_text):
    part_starts = list(re.finditer(r"Part\s*IV\s*Translation|PartIV\s*Translation", answer_text, re.I))
    source = answer_text[part_starts[-1].start() :] if part_starts else answer_text
    match = re.search(r"(?:参考译文|译文)[】】·\s]*(.*?)(?:精简结构|译点精析|重点词汇|答案速查|Part\s*II|Part\s*III|\Z)", source, re.S)
    if not match:
        return ""
    reference = clean_text(match.group(1))
    reference = re.sub(r"\n+", " ", reference)
    return reference[:2500].strip()


def parse_translation(question_text, answer_text, meta):
    prompt = parse_translation_prompt(question_text)
    if not prompt:
        return []
    reference = parse_translation_reference(answer_text)
    explanation = "提交后对照参考译文，重点看信息是否完整、句子结构是否自然、关键词是否准确。"
    if reference:
        answer = reference
    else:
        answer = "参考译文未能自动识别，请回看原答案 PDF。"
    return [
        {
            "id": f"{meta['base']}-translation",
            "type": "translation",
            "section": "translation",
            "source": meta["paper"],
            "stem": prompt,
            "answer": answer,
            "explanation": explanation,
        }
    ]


def build_bank():
    question_pdfs = sorted(p for p in PDF_DIR.glob("*.pdf") if not p.stem.endswith("_ans"))
    answer_map = {p.stem.replace("_ans", ""): p for p in PDF_DIR.glob("*_ans.pdf")}
    all_questions = []
    report = []

    for pdf_path in question_pdfs:
        meta = parse_meta(pdf_path)
        if not meta:
            continue
        answer_pdf = answer_map.get(meta["base"])
        if not answer_pdf:
            report.append({"paper": pdf_path.name, "status": "skipped", "reason": "missing answer pdf"})
            continue

        log(f"Processing {meta['paper']} ...")
        question_text = cached_text(pdf_path)
        answer_text = cached_text(answer_pdf)
        answer_key = parse_answer_key(answer_text)

        before = len(all_questions)
        all_questions.extend(parse_section_a(question_text, answer_key, answer_text, meta))
        all_questions.extend(parse_section_c(question_text, answer_key, answer_text, meta))
        all_questions.extend(parse_translation(question_text, answer_text, meta))
        added = len(all_questions) - before
        report.append(
            {
                "paper": meta["paper"],
                "added": added,
                "answers_found": len(answer_key),
                "question_chars": len(question_text),
                "answer_chars": len(answer_text),
            }
        )
        log(f"  added={added}, answers_found={len(answer_key)}")

    bank = {
        "name": "大学英语六级 2019-2025 真题练习",
        "description": "仅包含选词填空、阅读理解和汉翻英；由本地合法 PDF 自动整理，建议人工抽查校对。",
        "questions": all_questions,
    }
    OUTPUT.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "cet6_import_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Saved {OUTPUT} ({len(all_questions)} questions)")
    log(f"Saved {ROOT / 'cet6_import_report.json'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build"])
    args = parser.parse_args()
    if args.command == "build":
        build_bank()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
