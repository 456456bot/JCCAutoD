class ShopNameCache:
    """Compare the five OCR names in slot order; pixels never trigger purchase."""

    def __init__(self):
        self.previous = None

    def changed(self, names):
        if len(names) != 5 or any(not isinstance(name, str) for name in names):
            raise ValueError("商店名称序列必须包含五个栏位，空栏用空字符串表示")
        current = tuple(name.strip() for name in names)
        changed = current != self.previous
        # Compare adjacent name sequences, not a permanent set of seen shops.
        self.previous = current
        return changed
