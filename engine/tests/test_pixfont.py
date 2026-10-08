from engine.campus import pixfont


def test_every_glyph_is_seven_rows_of_five():
    for ch, rows in pixfont.GLYPHS.items():
        assert len(rows) == pixfont.CHAR_H, ch
        assert all(len(r) == pixfont.CHAR_W and set(r) <= {"0", "1"} for r in rows), ch


def test_the_label_characters_exist():
    for ch in "%+_/:()":
        assert ch in pixfont.GLYPHS


def _cells(rects, cell):
    out = set()
    for x, y, w, h in rects:
        assert h == cell
        for k in range(round(w / cell)):
            out.add((round(x / cell) + k, round(y / cell)))
    return out


def test_text_rects_cover_exactly_the_on_pixels():
    got = _cells(pixfont.text_rects("L1", 0, 0, 2.0), 2.0)
    want = set()
    for i, ch in enumerate("L1"):
        for r, row in enumerate(pixfont.GLYPHS[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    want.add((i * (pixfont.CHAR_W + pixfont.SPACING) + c, pixfont.CHAR_H - 1 - r))
    assert got == want


def test_unknown_characters_are_spaces_and_text_is_upper_cased():
    assert list(pixfont.text_rects("~", 0, 0, 1.0)) == []
    assert list(pixfont.text_rects("l", 0, 0, 1.0)) == list(pixfont.text_rects("L", 0, 0, 1.0))
    assert pixfont.text_width("ABC", 1.0) == 18
