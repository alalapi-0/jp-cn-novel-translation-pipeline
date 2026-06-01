#!/usr/bin/env python3
"""Apply chapter formatting: novel title headers, personal translation disclaimer, bilingual layout."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOVEL = "是谁杀死了勇者"
URL_MAP = {f"{i:03d}": f"https://ncode.syosetu.com/n1052ib/{i}/" for i in range(1, 21)}

DISCLAIMER_RE = re.compile(
    r'<p style="font-size:0\.72em;color:#888;line-height:1\.45;margin:0\.6em 0;">\s*'
    r"译者说明：.*?"
    r"</p>\s*",
    re.DOTALL,
)

LEGACY_BILINGUAL_PARA_RE = re.compile(
    r"## 段落 \d+\n\*\*原文：\*\*\n(.*?)\n\n\*\*译文：\*\*\n(.*?)\n\n(?:---\n)?",
    re.DOTALL,
)

CLEAN_BILINGUAL_PARA_RE = re.compile(
    r"\*\*原文：\*\*\n(.*?)\n\n\*\*译文：\*\*\n(.*?)(?=\n\n\*\*原文：\*\*|\Z)",
    re.DOTALL,
)

CHAPTER_HEADER_RE = re.compile(r"^# (\d{3})　(.+)$", re.MULTILINE)

# Visible gap between blocks in MD preview (single blank lines collapse in many readers).
PARA_SPACER = '<p style="margin:0.6em 0;line-height:0;font-size:0;">&nbsp;</p>'
PARA_SPACER_BLOCK_RE = re.compile(
    rf"\n\n{re.escape(PARA_SPACER)}\n\n"
)

JP_FILES = {
    f"{i:03d}": name
    for i, name in enumerate(
        [
            "001-誰が勇者を殺したか---プロローグ.md",
            "002-誰が勇者を殺したか---その１.md",
            "003-誰が勇者を殺したか---断章１.md",
            "004-誰が勇者を殺したか---その２.md",
            "005-誰が勇者を殺したか---断章2.md",
            "006-誰が勇者を殺したか---その３.md",
            "007-誰が勇者を殺したか---断章３.md",
            "008-誰が勇者を殺したか---その４.md",
            "009-誰が勇者を殺したか---断章４.md",
            "010-誰が勇者を殺したか---断章５.md",
            "011-誰が勇者を殺したか---断章６.md",
            "012-誰が勇者を殺したか---その５.md",
            "013-誰が勇者を殺したか---断章７.md",
            "014-誰が勇者を殺したか---その６.md",
            "015-誰が勇者を殺したか---その７.md",
            "016-誰が勇者を殺したか---断章８.md",
            "017-誰が勇者を殺したか---エピローグ.md",
            "018-誰が勇者を殺したか---発売記念ss-麒麟児１.md",
            "019-誰が勇者を殺したか---発売記念ss-麒麟児２.md",
            "020-誰が勇者を殺したか---発売記念ss-麒麟児３.md",
        ],
        start=1,
    )
}


def chapter_disclaimer(url: str) -> str:
    return (
        '<p style="font-size:0.72em;color:#888;line-height:1.45;margin:0.6em 0;">\n'
        f"译者说明：本译文为駄犬老师作品《{NOVEL}》的个人翻译，出于学习、整理与个人阅读目的制作。"
        f'原文出处：<a href="{url}">{url}</a>。'
        "并非官方译文；如需转载、引用或公开发布，请遵守原作者与原平台的版权规则。\n"
        "</p>"
    )


VOLUME_DISCLAIMER = (
    '<p style="font-size:0.72em;color:#888;line-height:1.45;margin:0.6em 0;">\n'
    f"译者说明：本译文为駄犬老师作品《{NOVEL}》的个人翻译，出于学习、整理与个人阅读目的制作。"
    "原作版权归原作者及原发布平台所有。并非官方译文。"
    "原文出处请参见各章节标注的来源 URL。"
    "若需转载、引用或公开发布，请遵守原作者与原平台的版权规则。\n"
    "</p>"
)

VOLUME_URL_BLOCK = (
    '<p style="font-size:0.72em;color:#888;line-height:1.45;margin:0.6em 0;">\n'
    '原文出处：<a href="https://ncode.syosetu.com/n1052ib/">https://ncode.syosetu.com/n1052ib/</a>\n'
    "</p>"
)


def strip_para_spacers(text: str) -> str:
    return PARA_SPACER_BLOCK_RE.sub("\n\n", text)


def join_with_spacers(blocks: list[str]) -> str:
    if not blocks:
        return ""
    body = f"\n\n{PARA_SPACER}\n\n".join(blocks)
    return body if body.endswith("\n") else body + "\n"


def add_cn_paragraph_spacers(rest: str) -> str:
    rest = strip_para_spacers(rest.strip())
    parts = [p.strip() for p in re.split(r"\n\n+", rest) if p.strip()]
    return join_with_spacers(parts)


def cn_paragraphs_from_chapter(content: str) -> tuple[str, str, list[str]]:
    parsed = parse_chapter_header(content)
    if not parsed:
        raise ValueError("Cannot parse CN chapter header")
    num, subtitle, rest = parsed
    rest = DISCLAIMER_RE.sub("", rest, count=1).lstrip("\n")
    rest = strip_para_spacers(rest.strip())
    paragraphs = [p.strip() for p in re.split(r"\n\n+", rest) if p.strip()]
    return num, subtitle, paragraphs


def jp_paragraphs(num: str) -> list[str]:
    content = (ROOT / "input_jp" / JP_FILES[num]).read_text(encoding="utf-8").strip()
    content = re.sub(r"\n---\n+Source URL:.*\Z", "", content, flags=re.DOTALL).strip()
    content = re.sub(r"^# .+?\n+", "", content, count=1, flags=re.DOTALL)
    content = re.sub(r"^## .+?\n+", "", content, count=1, flags=re.DOTALL)
    return [
        p.strip()
        for p in re.split(r"\n\n+", content)
        if p.strip() and p.strip() != "---"
    ]


def parse_chapter_header(content: str) -> tuple[str, str, str] | None:
    """Return (chapter_num, subtitle, rest_after_header_line)."""
    match = re.match(r"# (\d{3})　(.+)\n", content)
    if not match:
        return None
    num, subtitle = match.group(1), match.group(2)
    if subtitle == NOVEL:
        sub_match = re.search(r"^## (.+)$", content[match.end() :], re.MULTILINE)
        if not sub_match:
            return None
        subtitle = sub_match.group(1)
        header_end = match.end() + sub_match.end()
    else:
        header_end = match.end()
    return num, subtitle, content[header_end:]


def transform_cn_chapter(content: str) -> str:
    parsed = parse_chapter_header(content)
    if not parsed:
        return content
    num, subtitle, rest = parsed
    rest = DISCLAIMER_RE.sub("", rest, count=1).lstrip("\n")
    rest = add_cn_paragraph_spacers(rest)
    url = URL_MAP[num]
    return (
        f"# {num}　{NOVEL}\n"
        f"## {subtitle}\n"
        f"{chapter_disclaimer(url)}\n\n"
        f"{rest}"
    )


def transform_bilingual(content: str) -> str:
    parsed = parse_chapter_header(content)
    if not parsed:
        return content
    num, subtitle, _ = parsed
    cn_content = (ROOT / "output_cn" / "translated" / f"chapter_{num}_cn.md").read_text(
        encoding="utf-8"
    )
    _, subtitle, cn_paras = cn_paragraphs_from_chapter(cn_content)
    jp_paras = jp_paragraphs(num)
    if len(jp_paras) != len(cn_paras):
        raise ValueError(
            f"Paragraph count mismatch for chapter {num}: jp={len(jp_paras)} cn={len(cn_paras)}"
        )

    blocks = [f"{jp}\n{cn}" for jp, cn in zip(jp_paras, cn_paras)]
    body = join_with_spacers(blocks)

    return (
        f"# {num}　{NOVEL}\n"
        f"## {subtitle}\n\n"
        f"{chapter_disclaimer(URL_MAP[num])}\n\n"
        f"{body}"
    )


def rebuild_full_volume() -> None:
    parts = [f"# {NOVEL}\n\n", VOLUME_DISCLAIMER, "\n\n", VOLUME_URL_BLOCK, "\n\n"]
    for i in range(1, 21):
        chapter_path = ROOT / "output_cn" / "translated" / f"chapter_{i:03d}_cn.md"
        chapter_text = chapter_path.read_text(encoding="utf-8")
        parts.append(chapter_text)
        if not chapter_text.endswith("\n\n"):
            parts.append("\n" if chapter_text.endswith("\n") else "\n\n")
    (ROOT / "output_cn" / "translated" / "full_volume_cn.md").write_text(
        "".join(parts), encoding="utf-8"
    )


def update_volume_preface() -> None:
    text = (ROOT / "output_cn" / "translated" / "000_volume_preface.md").read_text(
        encoding="utf-8"
    )
    text = DISCLAIMER_RE.sub(VOLUME_DISCLAIMER + "\n\n", text, count=1)
    (ROOT / "output_cn" / "translated" / "000_volume_preface.md").write_text(
        text, encoding="utf-8"
    )


def main() -> None:
    cn_dir = ROOT / "output_cn" / "translated"
    bi_dir = ROOT / "output_cn" / "bilingual"

    for path in sorted(cn_dir.glob("chapter_*_cn.md")):
        original = path.read_text(encoding="utf-8")
        updated = transform_cn_chapter(original)
        path.write_text(updated, encoding="utf-8")
        print(f"CN  {path.name}")

    for path in sorted(bi_dir.glob("chapter_*_bilingual.md")):
        original = path.read_text(encoding="utf-8")
        updated = transform_bilingual(original)
        path.write_text(updated, encoding="utf-8")
        print(f"BI  {path.name}")

    update_volume_preface()
    print("Updated 000_volume_preface.md")
    rebuild_full_volume()
    print("Rebuilt full_volume_cn.md")


if __name__ == "__main__":
    main()
