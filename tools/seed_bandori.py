"""把 BanG Dream! 的乐队/角色资料导入当前群 canon。

数据来自用户提供的资料，只写明确给出的事实，不做二次创作。
用法：
    python tools/seed_bandori.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.canon import entity_key  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.store import GroupStore  # noqa: E402
from bot.util import now_iso  # noqa: E402

# (名字, 定位, 简介, 别名, 额外字段)
BANDS: dict[str, list[tuple[str, str, str, list[str], dict[str, str]]]] = {
    "Poppin'Party": [
        ("户山香澄", "Vo. & Gt.", "花咲川女子学园高中生，性格开朗乐观，行动力强，一直在寻找“闪闪发光、令人心动”的事物。", ["香澄"], {"学校": "花咲川女子学园"}),
        ("花园多惠", "Gt.", "吉他技巧高超，性格天然，有时会做出令人意想不到的举动。", ["多惠"], {}),
        ("牛込里美", "Ba.", "性格原本内向，加入乐队后逐渐变得积极，使用的粉色贝斯是姐姐的旧琴。", ["里美"], {}),
        ("山吹沙绫", "Dr.", "性格温柔，是乐队里的调和剂，课余时间会帮家里打理面包店。", ["沙绫"], {"家业": "山吹烘焙坊"}),
        ("市谷有咲", "Key.", "典型的室内派，性格有些毒舌，不善于坦率表达，成绩优秀。", ["有咲"], {}),
    ],
    "Afterglow": [
        ("美竹兰", "Vo. & Gt.", "华道世家独生女，性格要强不服输，但内心其实很害怕寂寞。", ["兰"], {}),
        ("青叶摩卡", "Gt.", "说话做事我行我素，但对喜欢的事物会非常专注。", ["摩卡", "モカ"], {}),
        ("上原绯玛丽", "Ba.", "性格开朗，是乐队的队长，负责团结个性迥异的成员。", ["绯玛丽", "小绯"], {}),
        ("宇田川巴", "Dr.", "性格爽朗，深受商店街居民的喜爱，是Roselia鼓手宇田川亚子的姐姐。", ["巴"], {}),
        ("羽泽鸫", "Key.", "成员中最普通的一个，但非常努力，是大家的心灵支柱。", ["鸫", "鸫鸫"], {}),
    ],
    "Pastel*Palettes": [
        ("丸山彩", "Vo.", "偶像宅，以成为偶像为目标，无论遇到什么困难都不会放弃。", ["彩"], {}),
        ("冰川日菜", "Gt.", "天才少女，说话直接，是Roselia吉他手冰川纱夜的双胞胎妹妹。", ["日菜"], {}),
        ("白鹭千圣", "Ba.", "童星出身，性格温柔，在乐队中担任可靠的姐姐角色。", ["千圣"], {}),
        ("大和麻弥", "Dr.", "性格开朗，是乐队的开心果。", ["麻弥"], {}),
        ("若宫伊芙", "Key.", "混血归国子女，性格率直，非常憧憬武士道文化。", ["伊芙"], {}),
    ],
    "Roselia": [
        ("凑友希那", "Vo.", "性格酷酷的，对自己和他人要求严格，对音乐非常纯粹。", ["友希那", "Yukina"], {}),
        ("冰川纱夜", "Gt.", "性格认真严谨，是风纪委员，与日菜是双胞胎姐妹。", ["纱夜", "Sayo"], {}),
        ("今井莉莎", "Ba.", "性格亲切，很会照顾人，是Roselia成员之间的润滑剂。", ["莉莎", "Lisa"], {}),
        ("宇田川亚子", "Dr.", "性格活泼，是Afterglow鼓手宇田川巴的妹妹。", ["亚子", "Ako"], {}),
        ("白金燐子", "Key.", "性格内向，但一旦专注就会深入钻研，也是学生会长。", ["燐子", "Rinko"], {}),
    ],
    "Hello, Happy World!": [
        ("弦卷心", "Vo.", "好奇心旺盛，想到什么就会立刻去做，像台风一样的存在。", ["心", "Kokoro"], {}),
        ("濑田薰", "Gt.", "容貌端丽，在学校很受欢迎，自称“儚い”。", ["薰", "Kaoru"], {}),
        ("北泽育美", "Ba.", "性格开朗活泼，运动神经拔群，是垒球队的王牌。", ["育美", "Hagumi"], {}),
        ("松原花音", "Dr.", "性格内向，有点冒失，不擅长拒绝别人的请求。", ["花音", "Kanon"], {}),
        ("奥泽美咲", "DJ", "穿着熊玩偶服的DJ，是乐队里唯一的吐槽担当。", ["美咲", "米歇尔", "Michelle"], {}),
    ],
    "Morfonica": [
        ("仓田真白", "Vo.", "性格内向，想象力丰富，负责乐队的作词。", ["真白", "Mashiro"], {}),
        ("桐谷透子", "Gt.", "在SNS上很有人气，性格开朗但有点我行我素。", ["透子", "Touko"], {}),
        ("广町七深", "Ba.", "天才型少女，憧憬“普通”的生活。", ["七深", "Nanami"], {}),
        ("二叶筑紫", "Dr.", "努力可靠，是乐队的领导者。", ["筑紫", "Tsukushi"], {}),
        ("八潮瑠唯", "Vn.", "性格冷静现实，是乐队的提琴手。", ["瑠唯", "Rui"], {}),
    ],
    "RAISE A SUILEN": [
        ("和奏瑞依", "Vo. & Ba.", "性格沉稳成熟，拥有强有力的歌声。", ["LAYER", "レイヤ"], {}),
        ("朝日六花", "Gt.", "从岐阜来到东京，非常崇拜Poppin'Party。", ["LOCK", "ロック"], {}),
        ("佐藤增姬", "Dr.", "外表看起来不好惹，但内心是个重情义的人。", ["MASKING", "マスキング"], {}),
        ("鳰原令王那", "Key.", "非常喜欢可爱的东西，对CHU²非常忠诚。", ["PAREO", "パレオ"], {}),
        ("珠手知由", "DJ", "RAS的制作人，虽然态度蛮横但很有实力。", ["CHU²", "チュチュ"], {}),
    ],
    "MyGO!!!!!": [
        ("高松灯", "Vo.", "感性独特，被称为“羽丘的怪女生”。", ["灯", "Tomori"], {}),
        ("千早爱音", "Gt.", "乐队的发起人，渴望得到他人的认可。", ["爱音", "Anon"], {}),
        ("要乐奈", "Gt.", "在Live House出没的“野猫”，性格像猫一样自由。", ["乐奈", "野猫", "Rāna"], {}),
        ("长崎爽世", "Ba.", "原CRYCHIC成员，使用一把无品贝斯。", ["爽世", "SOYO", "そよ"], {"原乐队": "CRYCHIC"}),
        ("椎名立希", "Dr.", "性格认真，是乐队的鼓手。", ["立希", "Rikki", "Taki"], {}),
    ],
    "Ave Mujica": [
        ("三角初华", "Vo. & Gt.", "花咲川女子学园学生，同时也是偶像组合sumimi的成员。", ["Doloris", "ドロリス"], {"学校": "花咲川女子学园"}),
        ("若叶睦", "Gt.", "原CRYCHIC成员，性格沉默寡言。", ["Mortis", "モーティス"], {"原乐队": "CRYCHIC"}),
        ("八幡海铃", "Ba.", "冷静沉着，是乐队的贝斯手。", ["Timoris", "ティモリス"], {}),
        ("祐天寺若麦", "Dr.", "性格开朗，以“喵梦亲”的名义进行视频直播。", ["Amoris", "アモリス"], {}),
        ("丰川祥子", "Key.", "原CRYCHIC成员，Ave Mujica的创立者。", ["Oblivionis", "オブリビオニス"], {"原乐队": "CRYCHIC"}),
    ],
    "梦限大MewType": [
        ("仲町阿拉蕾", "Vo.", "喜欢动画和VTuber，性格开朗但有时会情绪低落。", [], {}),
        ("宫永野乃花", "Gt.", "主音吉他手，性格天真烂漫。", [], {}),
        ("峰月律", "Gt.", "节奏吉他手，外表看起来像优等生。", [], {}),
        ("藤都子", "Key.", "乐队的键盘手。", [], {}),
        ("千石由乃", "DJ & Mp.", "性格酷酷的，不太出门，但内心重情义。", [], {}),
    ],
    "millsage": [
        ("汐见萤", "Vo. & Key.", "被誉为“乐坛的天使”的音乐天才，性格善良。", [], {}),
        ("琴平凪", "Gt.", "乐队的吉他手。", [], {}),
        ("伊泽枣", "Gt.", "乐队的另一名吉他手。", [], {}),
        ("滨崎茉幌", "Ba.", "性格亲切随和，在团队中负责统筹。", [], {}),
        ("和泉朋花", "Dr.", "乐队的鼓手。", [], {}),
    ],
    "一家Dumb Rock!": [
        ("须贺蕾叶", "Vo. & Gt.", "性格开朗直率，是行动派。", [], {}),
        ("马桥心玖", "Gt.", "待人接物和善，但不会轻易吐露真心话。", [], {}),
        ("矢仓蓬咲", "Ba.", "乐队的贝斯手。", [], {}),
        ("梅里千樱梨", "Dr.", "有点任性的叛逆期少女，但让人讨厌不起来。", [], {}),
        ("四宫宁月", "Key.", "最年少的成员，但有着与年龄不符的沉着。", [], {}),
    ],
}


def field(value: str) -> dict:
    return {"value": value, "sources": [], "conflict_ids": []}


def relation(to: str, kind: str) -> dict:
    return {"to": to, "kind": kind, "sources": []}


def merge_entity(canon: dict, etype: str, name: str, aliases: list[str],
                 fields: dict[str, str], relations: list[dict]) -> bool:
    key = entity_key(etype, name)
    now = now_iso()
    ent = canon["entities"].get(key)
    created = ent is None
    if ent is None:
        ent = {
            "type": etype,
            "name": name,
            "aliases": [],
            "fields": {},
            "relations": [],
            "sources": [],
            "created_at": now,
            "updated_at": now,
        }
        canon["entities"][key] = ent
    for alias in aliases:
        if alias and alias not in ent["aliases"]:
            ent["aliases"].append(alias)
    for field_name, value in fields.items():
        ent["fields"].setdefault(field_name, field(value))
    existing = {(str(rel.get("to")), str(rel.get("kind"))) for rel in ent["relations"]}
    for rel in relations:
        pair = (str(rel.get("to")), str(rel.get("kind")))
        if pair not in existing:
            ent["relations"].append(rel)
            existing.add(pair)
    ent["updated_at"] = now
    return created


def main() -> int:
    cfg = Config.load(ROOT)
    store = GroupStore(cfg.data_dir, 123456789, cfg.timezone)
    canon = store.load_bandori()
    before = len(canon.get("entities", {}))

    created = 0
    bands = list(BANDS)
    for band, members in BANDS.items():
        band_fields = {"类型": "女子乐队", "成员数": str(len(members))}
        member_names = [name for name, *_ in members]
        created += merge_entity(
            canon, "faction", band, [], band_fields,
            [relation(name, "成员") for name in member_names],
        )
        for name, role, desc, aliases, extra in members:
            fields = {"乐队": band, "定位": role, "简介": desc}
            fields.update(extra)
            rels = [relation(band, "所属乐队")]
            if extra.get("原乐队"):
                rels.append(relation(extra["原乐队"], "原乐队"))
            created += merge_entity(canon, "character", name, aliases, fields, rels)

    # 姐妹关系
    for left, right, kind in [
        ("冰川日菜", "冰川纱夜", "双胞胎姐妹"),
        ("冰川纱夜", "冰川日菜", "双胞胎姐妹"),
        ("宇田川巴", "宇田川亚子", "姐妹"),
        ("宇田川亚子", "宇田川巴", "姐妹"),
    ]:
        left_key = entity_key("character", left)
        ent = canon["entities"].get(left_key)
        if ent and not any(rel.get("to") == right for rel in ent["relations"]):
            ent["relations"].append(relation(right, kind))

    # sumimi
    created += merge_entity(
        canon, "faction", "sumimi", [], {"类型": "偶像组合", "成员数": "1"},
        [relation("三角初华", "成员")],
    )
    chun = canon["entities"].get(entity_key("character", "三角初华"))
    if chun and not any(rel.get("to") == "sumimi" for rel in chun["relations"]):
        chun["relations"].append(relation("sumimi", "所属组合"))

    # 山吹烘焙坊
    created += merge_entity(
        canon, "location", "山吹烘焙坊", [], {"类型": "面包店", "关联": "山吹家"},
        [relation("山吹沙绫", "店主女儿")],
    )
    saaya = canon["entities"].get(entity_key("character", "山吹沙绫"))
    if saaya and not any(rel.get("to") == "山吹烘焙坊" for rel in saaya["relations"]):
        saaya["relations"].append(relation("山吹烘焙坊", "家业"))

    canon["updated_at"] = now_iso()
    store.save_bandori(canon)
    after = len(canon["entities"])
    store.append_changelog("导入 BanG Dream! 世界观（独立库）", [
        f"- 来源：用户提供的 BanG Dream! 乐队/角色资料",
        f"- 乐队 {len(bands)} 支，角色 {sum(len(v) for v in BANDS.values())} 位",
        f"- 写入 bandori.json：{before} -> {after}（新增 {created}）",
    ])
    print(f"完成：{len(bands)} 支乐队，{sum(len(v) for v in BANDS.values())} 位角色")
    print(f"邦多利库：{before} -> {after}（新增 {created}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
