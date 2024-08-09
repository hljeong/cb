import os, sys, subprocess
from termios import ECHO, ICANON, TCSAFLUSH, tcgetattr as tget, tcsetattr as tset

# todo: type annotate this at some point idk

fd = sys.stdin.fileno()
w = sys.stdout.write


# "#rrggbb" -> r, g, b
def hex2rgb(hex):
    return int(hex[1:3], 16), int(hex[2:4], 16), int(hex[5:7], 16)


class Term:
    class Code(str):
        def __call__(self, n=1):
            w(self * n)

    def dims(self):
        sz = os.get_terminal_size()
        return sz.columns, sz.lines

    def flush(self):
        sys.stdout.flush()

    def explicit(self, code):
        w(code)

    def fg(self, hex):
        r, g, b = hex2rgb(hex)
        w(f"\033[38;2;{r};{g};{b}m")

    def bg(self, hex):
        r, g, b = hex2rgb(hex)
        w(f"\033[48;2;{r};{g};{b}m")

    def rst(self):
        w("\033[0m")

    # honestly i still dont know whats going on here
    def __getattr__(self, capname):
        return Term.Code(
            subprocess.check_output(["tput", capname], universal_newlines=True)
        )


t = Term()


def clamp(x, constraint, inclusive=False):
    l, r = constraint
    assert l is None or r is None or inclusive and l <= r or not inclusive and l < r

    if l is not None and x < l:
        return l

    if r is not None and (inclusive and x > r or not inclusive and x >= r):
        return r if inclusive else r - 1

    return x


class View:
    def __init__(self, n, constraint=(None, None)):
        self.n = n
        self._constraint = constraint

        l, r = self._constraint
        assert l is None or r is None or self.n <= r - l

        self.s = 0
        self.e = self.n

    def anchor_s(self, anchor):
        self.s = clamp(anchor, self._constraint)
        self.e = self.s + self.n

    def anchor_e(self, anchor):
        self.e = clamp(anchor, self._constraint) + 1
        self.s = self.e - self.n

    def resize(self, n, anchor=None):
        self.n = n
        self.e = self.s + self.n
        if anchor is not None and anchor >= self.e:
            self.e = anchor + 1
            self.s = self.e - self.n


def limit(s, max_l, ellipsis=True, extend=False):
    assert max_l >= 0

    ret = s

    if ellipsis:
        if max_l <= 3:
            ret = s[:max_l]

        elif max_l <= 10:
            ret = f"{ret[:max_l - 2]}.." if len(ret) > max_l else ret

        else:
            ret = f"{ret[:max_l - 3]}..." if len(ret) > max_l else ret

    else:
        ret = ret[:max_l]

    if extend:
        ret += " " * (max_l - len(ret))

    return ret


class Columns:
    class Column:
        def __init__(self, default_width=None, min_width=3, ellipsis=True):
            self.default_width = default_width
            self.min_width = min_width
            self.ellipsis = ellipsis

        def format(self, s, width):
            return limit(s, width, ellipsis=self.ellipsis, extend=True)

    def __init__(self):
        self._cols = []

    # surely there is a better way...
    def column(self, default_width=None, min_width=3, ellipsis=True):
        self._cols.append(
            Columns.Column(
                default_width=default_width, min_width=min_width, ellipsis=ellipsis
            )
        )

    def get_widths(self, rows, width):
        total_width = 0
        widths = []
        for idx, col in enumerate(self._cols):
            col_width = col.default_width
            # no default_width means adaptive
            if col_width is None:
                col_width = 0
                for row in rows:
                    col_width = max(col_width, len(row[idx]))
            widths.append(col_width)
            total_width += col_width

        # very inefficient... but dont really care? unless this becomes a real issue
        while total_width > width:
            # sort columns by
            #   1. column is not at min width?
            #   2. allocated column width
            #
            # decrement width of the the "largest" column by 1
            # this will make sure columns at min width will not be narrowed
            # before all other columns are at min width
            sacrificial_idx = sorted(
                list(range(len(self._cols))),
                key=lambda idx: (widths[idx] != self._cols[idx].min_width, widths[idx]),
            )[-1]
            widths[sacrificial_idx] -= 1
            total_width -= 1

        return widths

    def format_rows(self, rows, width):
        widths = self.get_widths(rows, width)
        output_rows = []
        for row in rows:
            assert len(row) == len(self._cols)
            output_rows.append(
                list(
                    col.format(component, width)
                    for component, col, width in zip(row, self._cols, widths)
                )
            )
        return output_rows

    def format(self, rows, width):
        return "\n".join(
            list(map(lambda row: "".join(row), self.format_rows(rows, width)))
        )


# todo: event-driven? or smth
def key():
    return os.read(fd, 80).decode("ascii")


class Menu:
    def __init__(self, entries):
        self._entries = list(entries)
        self._n = len(self._entries)
        self._constraint = (0, self._n)
        self._save = None

    def _setup(self):
        self._save = tget(fd)
        temp = tget(fd)
        temp[3] &= ~(ICANON | ECHO)
        tset(fd, TCSAFLUSH, temp)
        t.smkx()
        t.civis()

    def _teardown(self, n):
        assert self._save is not None
        t.dl1(n)
        t.cnorm()
        t.rmkx()
        tset(fd, TCSAFLUSH, self._save)

    def select(self):
        self._setup()
        cols = Columns()
        # arrow
        cols.column(default_width=2, min_width=2, ellipsis=False)
        # item
        cols.column(min_width=10)
        # rpad
        cols.column(default_width=1, min_width=1, ellipsis=False)

        at = 0
        v = View(min(self._n, t.dims()[1] - 1), self._constraint)

        try:
            while True:
                # very nice responsiveness :)
                # todo: just need to put this on a timer instead of blocked by read()
                v.resize(min(self._n, t.dims()[1] - 1), anchor=at)
                rows = []
                for off, entry in enumerate(self._entries[v.s : v.e]):
                    idx = v.s + off
                    row = []
                    row.append("> " if idx == at else "  ")
                    row.append(entry)
                    row.append("")
                    rows.append(row)

                formatted_rows = cols.format_rows(rows, t.dims()[0])
                for off, row in enumerate(formatted_rows):
                    if off:
                        w("\n")

                    idx = v.s + off
                    arrow, entry, rpad = row

                    if idx == at:
                        t.bold()
                        t.fg("#7acb7f")
                        t.bg("#444444")
                        w(arrow)
                        t.rst()

                        t.bold()
                        t.bg("#444444")
                        w(entry)
                        w(rpad)
                        t.rst()

                    else:
                        w(arrow)
                        w(entry)
                        w(rpad)

                w("\r")
                for _ in range(v.n - 1):
                    t.cuu1()

                sys.stdout.flush()

                for k in key():
                    match k:
                        case "j":
                            at = clamp(at + 1, self._constraint)
                            if at >= v.e:
                                v.anchor_e(at)

                        case "k":
                            at = clamp(at - 1, self._constraint)
                            if at < v.s:
                                v.anchor_s(at)

                        case "\n":
                            self._teardown(v.n)
                            return self._entries[at]

        except KeyboardInterrupt:
            self._teardown(v.n)
            return None


def main():
    entries = [
        "hi",
        "mhm",
        "bye",
        " ".join(["super long"] * 10),
    ] * 5

    print(Menu(entries).select())


if __name__ == "__main__":
    main()
