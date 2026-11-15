"""Conservative transcript cleanup.

Only two things are done, both by deterministic rules (no LLM):
  1. remove filler / hesitation sounds (呃, 嗯, 啊 at clause start, 那个 used as a filler, um/uh ...)
  2. collapse stutter-style repetitions (我觉得我觉得 -> 我觉得, 我我我 -> 我)

Nothing is rephrased, reordered, or "improved". When a rule is unsure it leaves the text alone:
  * single-character reduplication (谢谢, 看看, 慢慢) is kept, except a short list of pronouns / function
    words that are almost always stutters (我我, 这这个);
  * two-character ABAB repeats are only collapsed for common disfluent words (然后然后, 就是就是),
    so 研究研究 / 考虑考虑 are kept;
  * 那个 / 这个 are only removed when they stand alone between pauses (那个，我们…), not before a noun.
"""
from __future__ import annotations

import re

HAN = r"\u4e00-\u9fff"
# clause boundary: start of string or Chinese/ASCII punctuation or whitespace
_B = r"(?:^|(?<=[，。！？、；：,.!?;:\s…]))"
# separator punctuation that may sit between a filler and the next words
_SEP = r"[，、,\s…\.]*"

# Pure hesitation sounds: no lexical meaning in normal dictation. Removed anywhere.
ALWAYS_FILLERS = ["呃", "唔", "嗯", "额额"]
# Removed only at a clause boundary (start / after punctuation), because they can be
# meaningful elsewhere (好啊 = tone particle, 金额 = word). 嗯 has no lexical use, so it is removed anywhere.
BOUNDARY_FILLERS = ["啊", "呦", "哟", "额", "哦", "噢", "诶", "欸"]
# Multi-char fillers: removed only when isolated between pauses ("那个，" / "那个…").
ISOLATED_FILLERS = ["那个", "这个", "就是说", "然后呢"]
EN_FILLERS = ["um", "umm", "uh", "uhh", "uhm", "erm", "er", "ah", "hmm"]

# 1-char words whose immediate doubling is a stutter (我我想 -> 我想).
STUTTER_CHARS = "我你他她它这那就在把被"
# 2-char words whose ABAB repetition is a stutter (keeps 研究研究, 考虑考虑, 谢谢谢谢? -> kept).
STUTTER_WORDS = [
    "然后", "就是", "那个", "这个", "我们", "你们", "他们", "我想", "我觉", "因为", "所以",
    "但是", "如果", "其实", "可能", "应该", "还有", "而且", "我是", "我要", "你看", "是不",
]
# English words that are legitimately doubled.
EN_KEEP_DOUBLE = {"very", "so", "really", "bye", "no", "ha", "go", "yes", "that", "had", "is"}


def _remove_fillers(t: str) -> str:
    for f in ALWAYS_FILLERS:
        t = t.replace(f, "")
    # sentence-initial / post-punctuation single-char fillers, possibly repeated (嗯嗯，啊啊)
    bf = "|".join(map(re.escape, BOUNDARY_FILLERS))
    t = re.sub(_B + rf"(?:(?:{bf})+{_SEP})+(?=[{HAN}A-Za-z0-9]|$)", "", t)
    # a boundary filler that ends a clause before punctuation: "我想啊，" keeps 啊 (tone), but
    # "，嗯，" (filler alone between pauses) goes.
    t = re.sub(rf"(?<=[，,、])(?:{bf})+[，,、]", "", t)
    iso = "|".join(map(re.escape, ISOLATED_FILLERS))
    # isolated: at boundary AND followed by a pause mark (or end of text)
    t = re.sub(_B + rf"(?:{iso})(?:[，、,…]+|\.\.\.+|\s+(?=[{HAN}]))", "", t)
    # 那个 directly before a pronoun is a filler (a real demonstrative is followed by a noun):
    # "那个我觉得" -> "我觉得", but "那个文件" stays.
    t = re.sub(_B + r"那个(?=我|你|他|她|咱|大家)", "", t)  # 这个 is left alone: "这个我不知道" is a topic
    ef = "|".join(EN_FILLERS)
    t = re.sub(rf"(?i)\b(?:{ef})\b[,\s…\.]*(?=\S|$)", "", t)
    return t


def _remove_repeats(t: str) -> str:
    # 3..8 Han characters repeated (optionally separated by a pause): 我觉得我觉得 / 我觉得，我觉得
    t = re.sub(rf"([{HAN}]{{3,8}})(?:[，、,\s…]*\1)+", r"\1", t)
    # 2-char disfluent words: 然后然后 / 然后，然后
    sw = "|".join(STUTTER_WORDS)
    t = re.sub(rf"({sw})(?:[，、,\s…]*\1)+", r"\1", t)
    # 1-char stutters: 我我我想 -> 我想 ; 这这个 -> 这个
    t = re.sub(rf"([{STUTTER_CHARS}])(?:[，、,\s…]*\1)+", r"\1", t)
    # English: "the the" -> "the" (keeps "very very", "bye bye")
    def _en(m: re.Match) -> str:
        w = m.group(1)
        return m.group(0) if w.lower() in EN_KEEP_DOUBLE else w
    t = re.sub(r"(?i)\b([A-Za-z']+)(?:[\s,]+\1\b)+", _en, t)
    return t


def _tidy(t: str) -> str:
    """Fix punctuation left dangling after removals. Never adds words."""
    t = re.sub(r"<\|[^|]*\|>", "", t)                 # stray model tags, if any
    t = re.sub(r"(…|\.\.\.)+", "，", t)               # pause marks -> plain comma
    t = re.sub(r"\s+([，。！？、；：])", r"\1", t)
    t = re.sub(r"([，、,])[，、,\s]+", r"\1", t)        # ，， -> ，
    t = re.sub(r"[，、,]+([。！？!?；;])", r"\1", t)     # ，。 -> 。
    t = re.sub(r"^[\s，、,。；;：:]+", "", t)           # leading punctuation
    t = re.sub(r"[，、,\s]+$", "", t)                  # trailing comma
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", t)  # spaces between Han chars
    t = re.sub(r" {2,}", " ", t)
    return t.strip()


def clean_text(text: str, remove_fillers: bool = True, remove_repeats: bool = True) -> str:
    t = text.strip()
    if not t:
        return t
    for _ in range(3):  # a couple of passes until stable (e.g. "呃 我我 呃 我想")
        prev = t
        if remove_fillers:
            t = _remove_fillers(t)
        if remove_repeats:
            t = _remove_repeats(t)
        t = _tidy(t)
        if t == prev:
            break
    return t
