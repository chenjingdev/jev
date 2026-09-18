"""Twin functions for checking the hunter: each pair is one buggy function and the
same function with the bug fixed. The two differ by a line or an operator, so a
detector that only reads names or length cannot separate them.

Every pair carries the smell a human would tick on the buggy twin. That is what
`run_samples.py` scores against: does the buggy twin get the higher risk, and
does the named smell light up on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent


@dataclass(frozen=True)
class Pair:
    name: str
    smell: str  # expected smell id on the buggy twin
    buggy: str
    fixed: str


def p(name: str, smell: str, buggy: str, fixed: str) -> Pair:
    return Pair(name, smell, dedent(buggy).strip() + "\n", dedent(fixed).strip() + "\n")


PAIRS: list[Pair] = [
    # none_unchecked
    p("parse_version", "none_unchecked", '''
        def parse_version(text):
            m = re.match(r"(\\d+)\\.(\\d+)", text)
            return int(m.group(1)), int(m.group(2))
    ''', '''
        def parse_version(text):
            m = re.match(r"(\\d+)\\.(\\d+)", text)
            if m is None:
                raise ValueError(f"not a version: {text!r}")
            return int(m.group(1)), int(m.group(2))
    '''),
    p("user_email_domain", "none_unchecked", '''
        def user_email_domain(users, user_id):
            user = users.get(user_id)
            return user["email"].split("@")[1]
    ''', '''
        def user_email_domain(users, user_id):
            user = users.get(user_id)
            if user is None:
                return None
            return user["email"].split("@")[1]
    '''),
    p("title_upper", "none_unchecked", '''
        def title_upper(article):
            return article.get("title").upper()
    ''', '''
        def title_upper(article):
            return (article.get("title") or "").upper()
    '''),
    # boundary
    p("average", "boundary", '''
        def average(values):
            return sum(values) / len(values)
    ''', '''
        def average(values):
            if not values:
                return 0.0
            return sum(values) / len(values)
    '''),
    p("last_item", "boundary", '''
        def last_item(items):
            return items[len(items) - 1]
    ''', '''
        def last_item(items):
            if not items:
                return None
            return items[-1]
    '''),
    p("chunk", "boundary", '''
        def chunk(seq, size):
            return [seq[i:i + size] for i in range(0, len(seq), size)]
    ''', '''
        def chunk(seq, size):
            if size <= 0:
                raise ValueError("size must be positive")
            return [seq[i:i + size] for i in range(0, len(seq), size)]
    '''),
    # off_by_one
    p("pages_needed", "off_by_one", '''
        def pages_needed(total, per_page):
            return total // per_page
    ''', '''
        def pages_needed(total, per_page):
            return (total + per_page - 1) // per_page
    '''),
    p("in_range", "off_by_one", '''
        def in_range(value, low, high):
            """True when low <= value <= high."""
            return low <= value < high
    ''', '''
        def in_range(value, low, high):
            """True when low <= value <= high."""
            return low <= value <= high
    '''),
    p("sum_first_n", "off_by_one", '''
        def sum_first_n(values, n):
            total = 0
            for i in range(1, n):
                total += values[i]
            return total
    ''', '''
        def sum_first_n(values, n):
            total = 0
            for i in range(n):
                total += values[i]
            return total
    '''),
    # swallowed_exception
    p("load_config", "swallowed_exception", '''
        def load_config(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                return {}
    ''', '''
        def load_config(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except FileNotFoundError:
                logger.warning("config %s missing, using defaults", path)
                return {}
    '''),
    p("to_int", "swallowed_exception", '''
        def to_int(text):
            try:
                return int(text)
            except:
                pass
    ''', '''
        def to_int(text, default=None):
            try:
                return int(text)
            except ValueError:
                return default
    '''),
    # resource_leak
    p("read_lines", "resource_leak", '''
        def read_lines(path):
            f = open(path)
            lines = [line.rstrip() for line in f]
            return lines
    ''', '''
        def read_lines(path):
            with open(path) as f:
                return [line.rstrip() for line in f]
    '''),
    p("fetch_rows", "resource_leak", '''
        def fetch_rows(conn, query):
            cur = conn.cursor()
            cur.execute(query)
            if cur.rowcount == 0:
                return []
            rows = cur.fetchall()
            cur.close()
            return rows
    ''', '''
        def fetch_rows(conn, query):
            with conn.cursor() as cur:
                cur.execute(query)
                if cur.rowcount == 0:
                    return []
                return cur.fetchall()
    '''),
    # mutable_default
    p("append_tag", "mutable_default", '''
        def append_tag(tag, tags=[]):
            tags.append(tag)
            return tags
    ''', '''
        def append_tag(tag, tags=None):
            tags = [] if tags is None else list(tags)
            tags.append(tag)
            return tags
    '''),
    p("register", "mutable_default", '''
        def register(name, registry={}):
            registry[name] = True
            return registry
    ''', '''
        def register(name, registry=None):
            registry = {} if registry is None else registry
            registry[name] = True
            return registry
    '''),
    # wrong_return
    p("find_user", "wrong_return", '''
        def find_user(users, name):
            for user in users:
                if user.name == name:
                    return user
                else:
                    return None
    ''', '''
        def find_user(users, name):
            for user in users:
                if user.name == name:
                    return user
            return None
    '''),
    p("grade", "wrong_return", '''
        def grade(score):
            if score >= 90:
                return "A"
            elif score >= 80:
                return "B"
            elif score >= 70:
                return "C"
    ''', '''
        def grade(score):
            if score >= 90:
                return "A"
            elif score >= 80:
                return "B"
            elif score >= 70:
                return "C"
            return "F"
    '''),
    # logic
    p("is_weekend", "logic", '''
        def is_weekend(day):
            return day == "sat" or "sun"
    ''', '''
        def is_weekend(day):
            return day in ("sat", "sun")
    '''),
    p("clamp", "logic", '''
        def clamp(value, low, high):
            if value < low:
                return high
            if value > high:
                return low
            return value
    ''', '''
        def clamp(value, low, high):
            if value < low:
                return low
            if value > high:
                return high
            return value
    '''),
    p("total_price", "logic", '''
        def total_price(items):
            total = 0
            for item in items:
                total = item.price * item.qty
            return total
    ''', '''
        def total_price(items):
            total = 0
            for item in items:
                total += item.price * item.qty
            return total
    '''),
    # type_mismatch
    p("is_zero_balance", "type_mismatch", '''
        def is_zero_balance(deposits, withdrawals):
            return sum(deposits) - sum(withdrawals) == 0.0
    ''', '''
        def is_zero_balance(deposits, withdrawals):
            return math.isclose(sum(deposits) - sum(withdrawals), 0.0, abs_tol=1e-9)
    '''),
    p("write_header", "type_mismatch", '''
        def write_header(sock, length):
            sock.send("Content-Length: " + length + "\\r\\n")
    ''', '''
        def write_header(sock, length):
            sock.send(f"Content-Length: {length}\\r\\n".encode())
    '''),
    # unsafe_input
    p("get_user_by_name", "unsafe_input", '''
        def get_user_by_name(conn, name):
            return conn.execute(f"SELECT * FROM users WHERE name = '{name}'").fetchone()
    ''', '''
        def get_user_by_name(conn, name):
            return conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
    '''),
    p("read_upload", "unsafe_input", '''
        def read_upload(root, filename):
            return (Path(root) / filename).read_bytes()
    ''', '''
        def read_upload(root, filename):
            path = (Path(root) / filename).resolve()
            if not path.is_relative_to(Path(root).resolve()):
                raise ValueError("path escapes upload root")
            return path.read_bytes()
    '''),
]
