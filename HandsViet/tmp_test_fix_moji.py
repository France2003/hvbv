from hansviet_user.middleware_i18n import GlobalContentTranslationMiddleware as M

samples = [
    "LÄ©nh vá»±c phá»¥c há»“i cÆ¡ xÆ°Æ¡ng khá»›p táº¡i HandsViet táº­p trung vÃ o giáº£m Ä‘au",
    "Đồng hành sau gãy xương",
    "15+ nÄƒm kinh nghiá»‡m",
    "Công nghệ tiên tiến từ Châu Âu",
    "MỤC TIÊU CỦA ÂM NGỮ TRỊ LIỆU",
]

for s in samples:
    f = M._fix_mojibake(s)
    print("IN :", s.encode("unicode_escape").decode("ascii"))
    print("OUT:", f.encode("unicode_escape").decode("ascii"))
    print("SCORE", M._repair_score(s), "=>", M._repair_score(f))
    print("---")
