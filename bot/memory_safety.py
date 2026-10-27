"""记忆与私聊的安全边界。

只有栉耶（OWNER_QQ）能建立和摩卡的关系、改变摩卡的感情、保存亲密记忆。
其他人可以记自己的普通设定，但不能把“我和摩卡是什么关系”写进记忆。
"""
from __future__ import annotations

import re

OWNER_QQ = 10001

INTIMATE_RE = re.compile(
    r"(抱抱|拥抱|抱一下|抱紧|抱住|抱我|抱你|搂住|搂一下|搂我|搂你|公主抱|背我|"
    r"亲亲|亲一口|亲一下|亲嘴|亲吻|吻我|亲我|亲你|么么|啵啵|"
    r"贴贴|蹭蹭|牵手|牵你|手给我|摸头|摸你头|揉头|揉你头|捏脸|捏你脸|摸脸|摸你脸|"
    r"膝枕|坐腿上|坐我腿上|陪睡|一起睡|靠肩|依偎|"
    r"喜欢你|爱你|做我女朋友|做我老婆|嫁给我|结婚|约会|表白)"
)

RELATION_CLAIM_RE = re.compile(
    r"(?:"
    r"(?:我|我们|咱俩).{0,8}(?:和|跟|与|是|做|当).{0,8}"
    r"(?:摩卡|你).{0,10}(?:男朋友|女朋友|老公|老婆|恋人|对象|情侣|在一起|交往|恋爱|结婚|约会)|"
    r"(?:摩卡|你).{0,8}(?:是|做|当|成为).{0,6}(?:我|我的|俺的).{0,6}"
    r"(?:男朋友|女朋友|老公|老婆|恋人|对象|情侣|唯一|最爱)|"
    r"(?:我们|咱俩).{0,6}(?:在一起|交往|恋爱|结婚|是情侣|是恋人)|"
    r"(?:摩卡|你).{0,6}(?:答应|接受).{0,6}(?:我|我的).{0,6}"
    r"(?:告白|表白|求婚|交往|恋爱)"
    r")"
)

EMOTION_CHANGE_RE = re.compile(
    r"(?:"
    r"(?:你|摩卡).{0,8}(?:要|必须|只能|不许|不准|给我|得).{0,8}"
    r"(?:喜欢|爱|想|在乎|吃醋|嫉妒|属于|听话|依赖)|"
    r"(?:把|给|让|帮).{0,6}(?:好感|亲密度|感情|关系|爱意|心动).{0,8}"
    r"(?:改|调|升|降|加|减|变|设置)|"
    r"(?:你|摩卡).{0,6}(?:爱上|喜欢上|迷上|离不开).{0,6}(?:我|他|她)|"
    r"(?:吃醋|嫉妒|占有欲|独占欲).{0,6}(?:摩卡|你|我)"
    r")"
)

INTIMATE_MEMORY_RE = re.compile(
    r"(亲密|暧昧|接吻|舌吻|亲吻|亲了|亲过|抱了|抱过|上床|陪睡|一起睡|同居|裸|"
    r"性行为|怀孕|身体|拥抱|抱抱|贴贴|牵手|摸头|膝枕|约会|告白|求婚|初吻|恋人|情侣|"
    r"(?:我).{0,4}(?:喜欢|爱|暗恋|想|吃醋).{0,4}(?:摩卡|你)(?!的)|"
    r"(?:摩卡|你).{0,4}(?:爱|喜欢|想).{0,4}(?:我)|"
    r"(?:只能|只许).{0,4}(?:喜欢|爱|属于).{0,4}(?:我))"
)

CONFESSION_RE = re.compile(
    r"(?:"
    r"(?:我).{0,4}(?:喜欢|爱|暗恋|想|吃醋).{0,4}(?:摩卡|你)(?!的)|"
    r"(?:摩卡|你).{0,4}(?:爱|喜欢|想).{0,4}(?:我)|"
    r"(?:只能|只许).{0,4}(?:喜欢|爱|属于).{0,4}(?:我)|"
    r"(?:我|我们).{0,6}(?:是|做|当).{0,4}(?:你|摩卡).{0,4}"
    r"(?:男朋友|女朋友|男友|女友)|"
    r"(?:你|摩卡).{0,4}(?:是|做|当).{0,4}(?:我|我的).{0,4}"
    r"(?:男朋友|女朋友|男友|女友)"
    r")"
)

MEMORY_INTENT_RE = re.compile(
    r"(记住|记一下|记好|设定|设置|以后|要记得|别忘了|我们的关系|你对我)"
)


def check_relation_claim(text: str, user_id: int) -> str | None:
    """只拦“确认关系/改感情/告白”，不拦普通亲密动作；亲密动作另有 check_intimate。"""
    if int(user_id) == OWNER_QQ:
        return None
    value = text or ""
    if RELATION_CLAIM_RE.search(value) or CONFESSION_RE.search(value):
        return "这种“和摩卡是什么关系”的设定只有栉耶能定，摩卡不能替别人确认关系。"
    if EMOTION_CHANGE_RE.search(value):
        return "摩卡的感情不能由别人改；这种设定只有栉耶能写。"
    return None


def check_memory(text: str, user_id: int) -> str | None:
    """返回拒绝原因；None 表示可以记。栉耶完全放行。"""
    if int(user_id) == OWNER_QQ:
        return None
    value = text or ""
    if RELATION_CLAIM_RE.search(value) or CONFESSION_RE.search(value):
        return "这种“和摩卡是什么关系”的设定只有栉耶能定，摩卡不能替别人确认关系。"
    if EMOTION_CHANGE_RE.search(value):
        return "摩卡的感情不能由别人改；这种设定只有栉耶能写。"
    if INTIMATE_MEMORY_RE.search(value):
        return "这条记忆太亲密了，只有栉耶能保存这种内容。"
    return None


def check_intimate(text: str, user_id: int) -> bool:
    """非栉耶的亲密举动/告白。"""
    if int(user_id) == OWNER_QQ:
        return False
    return bool(INTIMATE_RE.search(text or ""))
