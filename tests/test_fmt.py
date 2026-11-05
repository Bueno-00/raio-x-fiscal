from raio_x_fiscal.fmt import num, pct


def test_num_brazilian_separators():
    assert num(1234567.891, 2) == "1.234.567,89"
    assert num(547718) == "547.718"
    assert num(0.99, 2) == "0,99"


def test_pct_from_fraction():
    assert pct(0.7866) == "78,7%"
    assert pct(0.92, 0) == "92%"


def test_text_around_numbers_is_untouched():
    # The old whole-line swap turned every "X" into "." ("COXA" -> "CO.A") and every comma into a dot.
    line = f"| COXA S/COXA FLEX 2,5MM | {num(314.7, 2)} |"
    assert line == "| COXA S/COXA FLEX 2,5MM | 314,70 |"
