#!/usr/bin/env python3
"""Supplement glossary aliases from the full-book regenerated consistency audit."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from glossary.models import GlossaryEntry  # noqa: E402
from glossary.store import EntryNotFoundError, GlossaryStore  # noqa: E402

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
NOTE = "2026-06-18 fullbook regenerated actual-data consistency rules"


def strip_brackets(text: str) -> str:
    return (text or "").strip().strip("【】").strip()


def merge_aliases(existing: list[str] | None, extra: list[str], target: str) -> list[str]:
    target_plain = strip_brackets(target)
    seen: set[str] = set()
    out: list[str] = []
    for item in [*(existing or []), *extra]:
        item = (item or "").strip()
        if not item or item == target_plain or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def upsert_entry(
    store: GlossaryStore,
    source: str,
    target: str,
    category: str,
    aliases: list[str],
    first_seen: int,
    log: list[dict],
) -> None:
    try:
        entry = store.get(source)
    except EntryNotFoundError:
        store.add(
            GlossaryEntry(
                source_term=source,
                target_term=target,
                category=category,
                description="fullbook regenerated actual-data consistency audit",
                first_seen_chapter=first_seen,
                locked=True,
                approved_by_user=True,
                aliases=merge_aliases([], aliases, target),
                notes=f"{NOTE}; canonical {strip_brackets(target)}",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        log.append({"action": "added", "source": source, "target": target, "aliases": aliases})
        return

    notes = entry.notes or ""
    if NOTE not in notes:
        notes += f"; {NOTE}"
    store.update(
        source,
        {
            "target_term": target,
            "category": category or entry.category,
            "aliases": merge_aliases(entry.aliases or [], aliases, target),
            "notes": notes,
        },
        by_machine=False,
    )
    log.append({"action": "updated", "source": source, "target": target, "aliases": aliases})


def main() -> int:
    store = GlossaryStore(REPO_ROOT / "workspace/configs/glossary.yaml")
    log: list[dict] = []
    entries = [
        ("【アルビニズム】", "【白化症】", "skill_name", ["白化症（アルビニズム）", "白化病"], 2),
        ("【スレッド】", "【讨论串】", "system_term", ["スレッド"], 19),
        ("【いんべんとり】", "【物品栏】", "system_term", ["インベントリ"], 22),
        ("【ネカマ】", "【男扮女号】", "system_term", ["ネカマ"], 26),
        ("【ネナベ】", "【女扮男号】", "system_term", ["ネナベ"], 26),
        ("【デスモダス】", "【德斯莫达斯】", "race", ["デスモダス"], 37),
        ("【デイウォーカー】", "【昼行者】", "race", ["昼行者（デイウォーカー）"], 76),
        ("【カミナリスラッシュ】", "【神雷斩】", "skill_name", ["神雷斩（カミナリスラッシュ）"], 79),
        ("【丈夫ではがれにくい】", "【Joubu de Hagarenikui】", "person_name", ["牢固且不易剥落"], 88),
        ("【名無しのエルフさん】", "【Nanashi no Elf-san】", "person_name", ["匿名精灵", "匿名精灵族玩家", "无名氏精灵先生", "无名氏精灵先生大人"], 88),
        ("【その手が暖か】", "【Sono Te ga Atataka】", "person_name", ["那只手好温暖", "那只手温暖", "还有那双手挺暖和的"], 102),
        ("【オクトー】", "【Octo】", "title", ["欧克托"], 243),
        (
            "【哲学者の卵】",
            "【哲学者之卵】",
            "item_name",
            ["贤者之卵", "哲学者的卵", "哲学家之卵", "哲学家的卵", "哲学家的蛋", "哲人之卵", "哲学者的蛋", "贤者之石（哲学家之卵）"],
            40,
        ),
        ("【レアちゃん】", "【小蕾雅】", "person_name", [], 113),
        ("【ハセラ】", "【哈塞拉】", "person_name", ["哈瑟拉"], 172),
        ("【フレアアロー】", "【烈焰箭】", "magic", ["炎矢", "闪耀箭"], 19),
        ("【パレオクトラ】", "【Paleoctra】", "person_name", ["帕雷奥克特拉"], 402),
        ("【コウキ】", "【Kouki】", "person_name", ["幸辉", "光希", "幸树", "光辉", "科乌基"], 167),
        ("【クランプ】", "【Clamp】", "person_name", ["钳子"], 184),
        ("【サンダーボルト】", "【雷霆】", "magic", ["雷电", "雷鸣弹", "雷电术"], 46),
        ("【リスポーン】", "【重生】", "system_term", [], 27),
        ("【ブランちゃん】", "【小布兰】", "person_name", ["布兰小妹妹"], 175),
        ("【ノーブル・ヒューマン】", "【Noble Human】", "race", ["高贵的人类", "贵族人"], 118),
        ("【マリオン】", "【玛莉昂】", "person_name", ["玛丽安"], 14),
        ("【テューア】", "【休亚】", "place_name", ["秋亚"], 161),
        ("【テューア草原】", "【休亚草原】", "place_name", ["秋亚草原"], 161),
        ("【スタニスラフ】", "【斯坦尼斯拉夫】", "person_name", ["斯塔尼斯拉夫", "斯坦尼斯劳斯"], 212),
        ("【マゼンタ】", "【玛珍塔】", "person_name", ["洋红"], 54),
        ("【ホーリー・エクスプロージョン】", "【圣光爆发】", "skill_name", ["神圣·爆裂", "神圣爆炸"], 169),
        ("【スクワイア・ゾンビ】", "【侍从僵尸】", "race", ["Squire Zombie", "仆从僵尸", "随从（Squire Zombie）"], 29),
        ("【ダーク・インプロージョン】", "【暗黑内爆】", "skill_name", ["黑暗内爆", "暗黑爆缩（Dark Implosion）"], 170),
        ("【ランスチャージ】", "【长枪冲锋】", "skill_name", ["枪突贯"], 233),
        ("【聖女たん】", "【圣女酱】", "title", ["圣女大人"], 245),
        ("【レッサーヴァンパイア】", "【低阶吸血鬼】", "race", ["下级吸血鬼", "Lesser Vampire"], 29),
        ("【ヒデオ】", "【Hideo】", "person_name", ["秀雄"], 212),
        ("【レヴィンパニッシャー】", "【雷罚制裁者】", "skill_name", ["雷霆惩击"], 522),
        ("【カーマイン】", "【卡麦因】", "person_name", ["胭脂红"], 77),
        ("【ラコリーヌの森】", "【拉科里努森林】", "place_name", ["拉克琳娜之森"], 144),
        ("【ラコリーヌ】", "【拉科里努】", "place_name", ["拉克琳娜"], 144),
        ("【アウラケルサス】", "【奥拉凯尔萨斯】", "place_name", ["奥拉克尔萨斯"], 283),
        ("【マグナメルム・ラルヴァ】", "【玛格纳梅尔姆·拉尔瓦】", "title", ["玛格纳梅尔姆·拉瓦"], 325),
        ("【ダンジョン実装】", "【地下城实装】", "system_term", ["迷宫实装"], 141),
        ("【目利きのルーペ】", "【鉴赏家的放大镜】", "item_name", ["鉴定放大镜"], 246),
        ("【賢者の石グレート】", "【贤者之石·极】", "item_name", ["贤者之石·卓越", "贤者之石·伟大"], 66),
        ("【フレスヴェルグ】", "【弗雷斯贝尔格】", "race", ["赫拉斯瓦尔格尔"], 483),
        ("【ヴァイス】", "【瓦伊斯】", "person_name", ["怀斯"], 156),
        ("【セーフティエリア】", "【安全区域】", "system_term", ["安全区"], 17),
        ("【アンリ】", "【安莉】", "person_name", ["安利"], 463),
        ("【アンフィスバエナ】", "【双头蛇】", "race", ["安菲斯拜纳"], 188),
        ("【グライテン】", "【格莱顿】", "place_name", ["格雷滕"], 402),
    ]
    for source, target, category, aliases, first_seen in entries:
        upsert_entry(store, source, target, category, aliases, first_seen, log)

    out = REPO_ROOT / "workspace/review/fullbook_regen_rule_supplement_log_20260618.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"updated_at": NOW, "changes": log}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"changes": len(log), "log": str(out.relative_to(REPO_ROOT))}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
