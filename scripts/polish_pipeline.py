#!/usr/bin/env python3
"""Utilities for polished CN chapters: normalize quotes, rebuild bilingual files, and QA."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
NOVEL = "是谁杀死了勇者"
PARA_SPACER = '<p style="margin:0.6em 0;line-height:0;font-size:0;">&nbsp;</p>'
DISCLAIMER_RE = re.compile(
    r'<p style="font-size:0\.72em;color:#888;line-height:1\.45;margin:0\.6em 0;">\s*'
    r"译者说明：.*?</p>\s*",
    re.DOTALL,
)
SPACER_RE = re.compile(rf"\n*{re.escape(PARA_SPACER)}\n*")
URL_MAP = {f"{i:03d}": f"https://ncode.syosetu.com/n1052ib/{i}/" for i in range(1, 21)}
JP_FILES = {
    "001": "001-誰が勇者を殺したか---プロローグ.md",
    "002": "002-誰が勇者を殺したか---その１.md",
    "003": "003-誰が勇者を殺したか---断章１.md",
    "004": "004-誰が勇者を殺したか---その２.md",
    "005": "005-誰が勇者を殺したか---断章2.md",
    "006": "006-誰が勇者を殺したか---その３.md",
    "007": "007-誰が勇者を殺したか---断章３.md",
    "008": "008-誰が勇者を殺したか---その４.md",
    "009": "009-誰が勇者を殺したか---断章４.md",
    "010": "010-誰が勇者を殺したか---断章５.md",
    "011": "011-誰が勇者を殺したか---断章６.md",
    "012": "012-誰が勇者を殺したか---その５.md",
    "013": "013-誰が勇者を殺したか---断章７.md",
    "014": "014-誰が勇者を殺したか---その６.md",
    "015": "015-誰が勇者を殺したか---その７.md",
    "016": "016-誰が勇者を殺したか---断章８.md",
    "017": "017-誰が勇者を殺したか---エピローグ.md",
    "018": "018-誰が勇者を殺したか---発売記念ss-麒麟児１.md",
    "019": "019-誰が勇者を殺したか---発売記念ss-麒麟児２.md",
    "020": "020-誰が勇者を殺したか---発売記念ss-麒麟児３.md",
}

TERM_REPLACEMENTS = {
    "治愈咒语": "恢复魔法",
    "治愈魔法": "恢复魔法",
    "女祭司": "巫女",
    "修士": "僧侣",
    "政党": "队伍",
    "MAMONO": "魔物",
    "魔兽": "魔物",
    "聚会成员": "队伍成员",
    "观众开始了": "谒见开始了",
}

FORBIDDEN_PATTERNS = [
    "「",
    "」",
    "『",
    "』",
    '"',
    "治愈咒语",
    "女祭司",
    "MAMONO",
    "**原文：**",
    "**译文：**",
]


def chapter_disclaimer(num: str) -> str:
    url = URL_MAP[num]
    return (
        '<p style="font-size:0.72em;color:#888;line-height:1.45;margin:0.6em 0;">\n'
        f"译者说明：本译文为駄犬老师作品《{NOVEL}》的个人翻译，出于学习、整理与个人阅读目的制作。"
        f'原文出处：<a href="{url}">{url}</a>。'
        "并非官方译文；如需转载、引用或公开发布，请遵守原作者与原平台的版权规则。\n"
        "</p>"
    )


def normalize_dialogue_quotes(text: str) -> str:
    text = text.replace("「", "“").replace("」", "”")
    text = text.replace("『", "‘").replace("』", "’")
    # Convert simple ASCII quote pairs inside Chinese prose. Keep HTML attributes untouched by
    # running this only on body paragraphs, not the disclaimer.
    return re.sub(r'"([^"\n]+)"', r"“\1”", text)


def normalize_terms(text: str) -> str:
    for old, new in TERM_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def parse_cn_chapter(path: Path) -> tuple[str, str, str, list[str]]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"# (\d{3})　.+\n## (.+?)\n", text)
    if not match:
        raise ValueError(f"Cannot parse chapter header: {path}")
    num, subtitle = match.group(1), match.group(2)
    rest = text[match.end() :]
    rest = DISCLAIMER_RE.sub("", rest, count=1).strip()
    rest = SPACER_RE.sub("\n\n", rest)
    paragraphs = [p.strip() for p in re.split(r"\n\n+", rest) if p.strip()]
    return num, subtitle, text[: match.end()], paragraphs


def write_cn_chapter(path: Path, num: str, subtitle: str, paragraphs: list[str]) -> None:
    body = f"\n\n{PARA_SPACER}\n\n".join(paragraphs)
    path.write_text(
        f"# {num}　{NOVEL}\n## {subtitle}\n{chapter_disclaimer(num)}\n\n{body}\n",
        encoding="utf-8",
    )


def normalize_cn_files() -> None:
    for path in sorted((ROOT / "output_cn" / "translated").glob("chapter_*_cn.md")):
        num, subtitle, _, paragraphs = parse_cn_chapter(path)
        updated = [normalize_terms(normalize_dialogue_quotes(p)) for p in paragraphs]
        write_cn_chapter(path, num, subtitle, updated)
        print(f"normalized {path.name}")


def parse_jp_paragraphs(path: Path) -> tuple[str, list[str]]:
    text = path.read_text(encoding="utf-8").strip()
    text = re.sub(r"\n---\n+Source URL:.*\Z", "", text, flags=re.DOTALL).strip()
    subtitle_match = re.search(r"^##\s+(.+)$", text, re.MULTILINE)
    subtitle = subtitle_match.group(1).strip() if subtitle_match else ""
    body = re.sub(r"^# .+?\n+", "", text, count=1, flags=re.DOTALL)
    body = re.sub(r"^## .+?\n+", "", body, count=1, flags=re.DOTALL)
    paragraphs = [
        p.strip()
        for p in re.split(r"\n\n+", body)
        if p.strip() and p.strip() != "---"
    ]
    return subtitle, paragraphs


def rebuild_bilingual() -> None:
    out_dir = ROOT / "output_cn" / "bilingual"
    for num, jp_name in JP_FILES.items():
        cn_path = ROOT / "output_cn" / "translated" / f"chapter_{num}_cn.md"
        jp_path = ROOT / "input_jp" / jp_name
        _, subtitle, _, cn_paras = parse_cn_chapter(cn_path)
        _, jp_paras = parse_jp_paragraphs(jp_path)
        if len(jp_paras) != len(cn_paras):
            raise ValueError(
                f"Paragraph count mismatch chapter {num}: jp={len(jp_paras)} cn={len(cn_paras)}"
            )
        blocks = [f"{jp}\n{cn}" for jp, cn in zip(jp_paras, cn_paras)]
        body = f"\n\n{PARA_SPACER}\n\n".join(blocks)
        (out_dir / f"chapter_{num}_bilingual.md").write_text(
            f"# {num}　{NOVEL}\n## {subtitle}\n\n{chapter_disclaimer(num)}\n\n{body}\n",
            encoding="utf-8",
        )
        print(f"rebuilt bilingual chapter_{num}_bilingual.md")


def rebuild_full_volume() -> None:
    parts = [
        f"# {NOVEL}\n\n",
        '<p style="font-size:0.72em;color:#888;line-height:1.45;margin:0.6em 0;">\n'
        f"译者说明：本译文为駄犬老师作品《{NOVEL}》的个人翻译，出于学习、整理与个人阅读目的制作。"
        "原作版权归原作者及原发布平台所有。并非官方译文。"
        "原文出处请参见各章节标注的来源 URL。"
        "若需转载、引用或公开发布，请遵守原作者与原平台的版权规则。\n</p>\n\n",
        '<p style="font-size:0.72em;color:#888;line-height:1.45;margin:0.6em 0;">\n'
        '原文出处：<a href="https://ncode.syosetu.com/n1052ib/">https://ncode.syosetu.com/n1052ib/</a>\n</p>\n\n',
    ]
    for i in range(1, 21):
        chapter = ROOT / "output_cn" / "translated" / f"chapter_{i:03d}_cn.md"
        text = chapter.read_text(encoding="utf-8").rstrip()
        parts.append(text + "\n\n")
    (ROOT / "output_cn" / "translated" / "full_volume_cn.md").write_text(
        "".join(parts), encoding="utf-8"
    )
    print("rebuilt full_volume_cn.md")


def lint() -> int:
    issues: list[str] = []
    cn_dir = ROOT / "output_cn" / "translated"
    bi_dir = ROOT / "output_cn" / "bilingual"
    for path in sorted(cn_dir.glob("chapter_*_cn.md")):
        num, _, _, paras = parse_cn_chapter(path)
        text = path.read_text(encoding="utf-8")
        body = SPACER_RE.sub("\n\n", DISCLAIMER_RE.sub("", text))
        for pattern in FORBIDDEN_PATTERNS[:7]:
            if pattern in body:
                issues.append(f"{path.name}: contains {pattern!r}")
        if body.count("“") != body.count("”"):
            issues.append(f"{path.name}: unmatched Chinese double quotes")
        if body.count("‘") != body.count("’"):
            issues.append(f"{path.name}: unmatched Chinese single quotes")
        _, jp_paras = parse_jp_paragraphs(ROOT / "input_jp" / JP_FILES[num])
        if len(paras) != len(jp_paras):
            issues.append(f"{path.name}: paragraph mismatch cn={len(paras)} jp={len(jp_paras)}")
    for path in sorted(bi_dir.glob("chapter_*_bilingual.md")):
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS[7:]:
            if pattern in text:
                issues.append(f"{path.name}: contains {pattern!r}")
    report = ROOT / "output_cn" / "review" / "polish_validation.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    if issues:
        report.write_text("# 润色校验报告\n\n" + "\n".join(f"- {i}" for i in issues) + "\n", encoding="utf-8")
        print(f"lint failed with {len(issues)} issue(s); see {report}")
        return 1
    report.write_text("# 润色校验报告\n\n未发现引号、术语残留或段落数量问题。\n", encoding="utf-8")
    print(f"lint OK; see {report}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["normalize-cn", "rebuild-bilingual", "rebuild-full", "lint", "all"],
    )
    args = parser.parse_args()
    if args.command in {"normalize-cn", "all"}:
        normalize_cn_files()
    if args.command in {"rebuild-bilingual", "all"}:
        rebuild_bilingual()
    if args.command in {"rebuild-full", "all"}:
        rebuild_full_volume()
    if args.command in {"lint", "all"}:
        return lint()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
