exec(open("probe_thicker_in_the_middle.py", encoding="utf-8").read())
print("replaced input faces:", [int(f) for f in np.nonzero(r.replaced)[0]], s["side_pieces_replaced_by"])
