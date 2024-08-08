import os, sys, subprocess, atexit
from termios import ECHO, ICANON, TCSAFLUSH, tcgetattr as tget, tcsetattr as tset


def main():
    fd = sys.stdin.fileno()
    w = sys.stdout.write

    class T:
        def explicit(self, capname):
            w(capname)

        def hex_fg(self, hex):
            if hex.startswith("0x"):
                hex = hex[2:]
            elif hex.startswith("#"):
                hex = hex[1:]

            self.rgb_fg(int(hex[:2], 16), int(hex[2:4], 16), int(hex[4:], 16))

        def rgb_fg(self, r, g, b):
            w(f"\033[38;2;{r};{g};{b}m")

        def hex_bg(self, hex):
            if hex.startswith("0x"):
                hex = hex[2:]
            elif hex.startswith("#"):
                hex = hex[1:]

            self.rgb_bg(int(hex[:2], 16), int(hex[2:4], 16), int(hex[4:], 16))

        def rgb_bg(self, r, g, b):
            w(f"\033[48;2;{r};{g};{b}m")

        def reset(self):
            w("\033[0m")

        def __getattr__(self, capname):
            def f(n=1):
                w(
                    str(
                        subprocess.check_output(
                            ["tput", capname], universal_newlines=True
                        )
                    )
                    * n
                )

            return f

    t = T()

    save = tget(fd)

    @atexit.register
    def clean_up():
        tset(fd, TCSAFLUSH, save)
        t.cnorm()
        t.rmkx()

    next = tget(fd)
    next[3] &= ~(ICANON | ECHO)
    tset(fd, TCSAFLUSH, next)

    def key():
        return os.read(fd, 80).decode("ascii")

    t.smkx()
    t.civis()

    def limit(s, max_l):
        assert max_l >= 0
        if max_l <= 3:
            return s[:max_l]
        elif max_l <= 10:
            return f"{s[:max_l - 2]}.." if len(s) > max_l else s
        else:
            return f"{s[:max_l - 3]}..." if len(s) > max_l else s

    def get_wh():
        t_sz = os.get_terminal_size()
        return t_sz.columns, t_sz.lines - 1

    stuff = [
        "hi",
        "mhm",
        "bye",
        " ".join(["super long"] * 10),
    ] * 5
    at = 0
    t_w, t_h = get_wh()
    v_s = 0
    v_e = min(len(stuff), t_h)

    def anchor_top(v_s):
        assert v_s >= 0
        t_w, t_h = get_wh()
        return min(len(stuff), v_s + t_h)

    def anchor_bottom(v_e):
        assert v_e <= len(stuff)
        t_w, t_h = get_wh()
        return max(0, v_e - t_h)

    try:
        while True:
            t_w, t_h = get_wh()
            # todo: ugly
            width = max(min(max(map(lambda entry: len(entry), stuff)) + 1, t_w - 2), 0)
            # print(f"{at=}, {v_s=}, {v_e=}", file=sys.stderr)
            for off, entry in enumerate(stuff[v_s:v_e]):
                if off:
                    w("\n")
                idx = v_s + off
                if idx == at:
                    # todo: ugly
                    t.bold()
                    t.hex_fg("#7acb7f")
                    t.hex_bg("#444444")
                    w(">")
                    t.reset()

                    t.bold()
                    t.hex_bg("#444444")
                    if t_w > 1:
                        w(" ")
                        w(f"{limit(entry, width):<{width}}")
                    t.reset()

                else:
                    # todo: ugly
                    w(" ")
                    if t_w > 1:
                        w(" ")
                        w(f"{limit(entry, width):<{width}}")

            w("\r")
            for s in range(v_e - v_s - 1):
                t.cuu1()

            sys.stdout.flush()

            for k in key():
                match k:
                    case "j":
                        at = min(at + 1, len(stuff) - 1)
                        if at >= v_e:
                            v_e = at + 1
                            v_s = anchor_bottom(v_e)

                    case "k":
                        at = max(at - 1, 0)
                        if at < v_s:
                            v_s = at
                            v_e = anchor_top(v_s)

                    case "\n":
                        t.dl1(v_e - v_s)
                        clean_up()
                        atexit.unregister(clean_up)
                        print(stuff[at])
                        return

                    case _:
                        w(str(k.encode()))
    except KeyboardInterrupt:
        t.dl1(v_e - v_s)


if __name__ == "__main__":
    main()
