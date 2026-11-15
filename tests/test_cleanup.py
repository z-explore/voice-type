import pytest

from voice_type.cleanup import clean_text


@pytest.mark.parametrize("raw,expected", [
    # fillers
    ("呃，我想明天去北京。", "我想明天去北京。"),
    ("呃呃我想明天去北京。", "我想明天去北京。"),
    ("嗯，这个方案可以。", "这个方案可以。"),
    ("啊，我刚才说到哪了？", "我刚才说到哪了？"),
    ("我们，呃，下周开会。", "我们，下周开会。"),
    ("那个，我们下午三点见。", "我们下午三点见。"),
    ("那个我觉得可以。", "我觉得可以。"),
    ("这个功能嗯明天可以上线。", "这个功能明天可以上线。"),
    ("um, I think we should go.", "I think we should go."),
    # repetitions
    ("我觉得我觉得这个可以。", "我觉得这个可以。"),
    ("我觉得，我觉得这个可以。", "我觉得这个可以。"),
    ("我我我想说一下。", "我想说一下。"),
    ("然后然后我们就走了。", "然后我们就走了。"),
    ("这这个问题很简单。", "这个问题很简单。"),
    ("I think the the plan works.", "I think the plan works."),
    # combined
    ("呃，那个，我觉得我觉得，就是就是这个需求没问题。", "我觉得，就是这个需求没问题。"),
])
def test_removes_disfluencies(raw, expected):
    assert clean_text(raw) == expected


@pytest.mark.parametrize("text", [
    # meaning-bearing words / legit reduplication must survive unchanged
    "把那个文件发给我。",            # 那个 = real demonstrative
    "这个价格太贵了。",
    "那个人是我同事。",             # 那个 + noun is a real demonstrative
    "我要那个。",
    "这个我不知道。",                 # 这个 as a topic, not a filler                     # 那个 at the end = "that one"
    "好啊，没问题。",                 # 啊 as sentence-final tone particle
    "谢谢你，我们看看再说。",          # 谢谢 / 看看 reduplication
    "我们研究研究再决定。",            # ABAB verb reduplication
    "请慢慢来，不着急。",
    "这笔金额是三百元。",              # 额 inside a word
    "我们讨论一下 Python 3.12 的新特性。",
    "This is very very important.",
])
def test_keeps_meaning(text):
    assert clean_text(text) == text


def test_disabled_is_noop_except_whitespace():
    raw = "呃，我觉得我觉得可以。"
    assert clean_text(raw, remove_fillers=False, remove_repeats=False) == raw


def test_empty():
    assert clean_text("") == ""
    assert clean_text("呃") == ""
