#!/usr/bin/env python3
"""
Rigorlytics - add USD figures alongside the EUR ones.

Transfermarkt reports in euros. MLS salaries are in dollars. To compare a
Premier League transfer fee against an MLS guaranteed-compensation figure you
need one currency, and for a fee paid in 2012 the honest number is what it cost
in dollars *in 2012*, not what those euros are worth today: EUR/USD has ranged
from roughly 0.85 to 1.60 over the period this data covers.

So every converted figure is computed at the rate on its own date, and the rate
and the date it came from are stored next to it. Any number on the site can be
audited back to an ECB reference rate.

Rates come from Frankfurter (ECB daily reference rates, no API key).

Adds to player_transfers:        fee_usd, market_value_usd, fx_rate, fx_date
Adds to player_market_profile:   market_value_usd, fx_rate, fx_date
Adds to player_market_values:    market_value_usd, fx_rate, fx_date

Usage:
    python scripts_add_usd.py --probe     # show the rate series, touch nothing
    python scripts_add_usd.py             # dry run: counts only
    python scripts_add_usd.py --write     # add columns and backfill
"""

import os, sys, json, bisect, argparse, datetime, urllib.request

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

sys.path.insert(0, os.getcwd())
from app.db import get_conn

UA = {"User-Agent": "Rigorlytics/1.0 (+https://rigorlytics.net)"}
FX_HOSTS = [
    "https://api.frankfurter.dev/v1/{start}..{end}?base=EUR&symbols=USD",
    "https://api.frankfurter.app/{start}..{end}?from=EUR&to=USD",
    "https://api.frankfurter.dev/v2/rates?from={start}&to={end}&quotes=USD",
]
FX_START = "1999-01-01"          # the euro did not exist before this
SOURCE = "ECB via frankfurter"

DDL = [
    "ALTER TABLE player_transfers      ADD COLUMN IF NOT EXISTS fee_usd bigint",
    "ALTER TABLE player_transfers      ADD COLUMN IF NOT EXISTS market_value_usd bigint",
    "ALTER TABLE player_transfers      ADD COLUMN IF NOT EXISTS fx_rate numeric(12,6)",
    "ALTER TABLE player_transfers      ADD COLUMN IF NOT EXISTS fx_date date",
    "ALTER TABLE player_market_profile ADD COLUMN IF NOT EXISTS market_value_usd bigint",
    "ALTER TABLE player_market_profile ADD COLUMN IF NOT EXISTS fx_rate numeric(12,6)",
    "ALTER TABLE player_market_profile ADD COLUMN IF NOT EXISTS fx_date date",
    "ALTER TABLE player_market_values  ADD COLUMN IF NOT EXISTS market_value_usd bigint",
    "ALTER TABLE player_market_values  ADD COLUMN IF NOT EXISTS fx_rate numeric(12,6)",
    "ALTER TABLE player_market_values  ADD COLUMN IF NOT EXISTS fx_date date",
]


# ------------------------------------------------------------------ fx

def _walk_rates(node, out):
    """Frankfurter has changed response shape across versions; accept any of
    them by finding ISO dates mapped to a number or to a dict holding USD."""
    if not isinstance(node, dict):
        return
    for k, v in node.items():
        if isinstance(k, str) and len(k) == 10 and k[4] == "-" and k[7] == "-":
            if isinstance(v, (int, float)):
                out[k] = float(v)
            elif isinstance(v, dict):
                for cur in ("USD", "usd"):
                    if isinstance(v.get(cur), (int, float)):
                        out[k] = float(v[cur])
                        break
        elif isinstance(v, dict):
            _walk_rates(v, out)


def fetch_rates(end=None):
    end = end or datetime.date.today().isoformat()
    last = None
    for tmpl in FX_HOSTS:
        url = tmpl.format(start=FX_START, end=end)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = "%s -> %s" % (url, str(e)[:70])
            continue
        rates = {}
        _walk_rates(data, rates)
        if len(rates) > 1000:
            print("  fx source: %s" % url.split("?")[0])
            return rates
        last = "%s -> only %d rates parsed" % (url, len(rates))
    raise RuntimeError("could not load EUR/USD series (%s)" % last)


class FX(object):
    """Nearest-previous-business-day lookup; markets are shut at weekends."""

    def __init__(self, rates):
        self.days = sorted(rates)
        self.rates = rates
        self.first, self.last = self.days[0], self.days[-1]

    def at(self, d):
        """-> (rate, date_used). Dates before the euro use the first rate."""
        if not d:
            return None, None
        d = str(d)[:10]
        if d in self.rates:
            return self.rates[d], d
        if d < self.first:
            return self.rates[self.first], self.first
        i = bisect.bisect_right(self.days, d) - 1
        if i < 0:
            return self.rates[self.first], self.first
        key = self.days[i]
        return self.rates[key], key


# ------------------------------------------------------------------ db

def bulk_update(cur, table, cols, rows, page=500):
    """UPDATE ... FROM (VALUES ...) for a batch of id-keyed rows."""
    if not rows:
        return 0
    ncol = len(rows[0])
    tmpl = "(" + ",".join(["%s"] * ncol) + ")"
    sets = ", ".join("%s = v.%s%s" % (c, c, cast) for c, cast in cols)
    done = 0
    for i in range(0, len(rows), page):
        chunk = rows[i:i + page]
        stmt = ("UPDATE %s AS t SET %s FROM (VALUES %s) AS v(id,%s) "
                "WHERE t.id = v.id::int"
                % (table, sets, ",".join([tmpl] * len(chunk)),
                   ",".join(c for c, _ in cols)))
        cur.execute(stmt, [x for r in chunk for x in r])
        done += len(chunk)
    return done


def convert(cur, fx, table, amount_col, date_col, extra_amount=None, dry=False):
    """Read EUR amounts, compute USD at the row's own date, write back."""
    sel = "SELECT id, %s AS amt, %s AS d" % (amount_col, date_col)
    if extra_amount:
        sel += ", %s AS amt2" % extra_amount
    sel += " FROM %s WHERE %s IS NOT NULL" % (table, amount_col)
    cur.execute(sel)
    rows, skipped = [], 0
    for r in cur.fetchall():
        r = dict(r)
        rate, used = fx.at(r["d"])
        if rate is None:
            skipped += 1
            continue
        vals = [r["id"], int(round(float(r["amt"]) * rate))]
        if extra_amount:
            vals.append(int(round(float(r["amt2"]) * rate))
                        if r.get("amt2") is not None else None)
        vals += [round(rate, 6), used]
        rows.append(tuple(vals))

    cols = [("%s_usd" % amount_col.replace("_eur", ""), "::bigint")]
    if extra_amount:
        cols.append((extra_amount.replace("_eur", "") + "_usd", "::bigint"))
    cols += [("fx_rate", "::numeric"), ("fx_date", "::date")]

    print("  %-24s %d rows to convert (%d skipped, no usable date)"
          % (table, len(rows), skipped))
    if dry:
        return 0
    return bulk_update(cur, table, cols, rows)


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()

    print("loading EUR/USD daily series")
    fx = FX(fetch_rates())
    print("  %d daily rates, %s to %s" % (len(fx.days), fx.first, fx.last))

    if a.probe:
        for d in ("1999-01-04", "2008-07-15", "2012-06-30", "2020-03-20",
                  "2025-06-30", fx.last):
            rate, used = fx.at(d)
            print("   %s -> %.4f  (rate dated %s)" % (d, rate, used))
        print("\nspot check: EUR 50,000,000 on 2012-06-30 = USD %s"
              % format(int(50000000 * fx.at("2012-06-30")[0]), ","))
        print("            EUR 50,000,000 at %s        = USD %s"
              % (fx.last, format(int(50000000 * fx.at(fx.last)[0]), ",")))
        return

    with get_conn() as c:
        cur = c.cursor()
        if a.write:
            for stmt in DDL:
                cur.execute(stmt)
            c.commit()
            print("columns ready")

        n1 = convert(cur, fx, "player_transfers", "fee_eur", "transfer_date",
                     extra_amount="market_value_eur", dry=not a.write)
        n2 = convert(cur, fx, "player_market_values", "market_value_eur", "as_of",
                     dry=not a.write)
        n3 = convert(cur, fx, "player_market_profile", "market_value_eur",
                     "updated_at::date", dry=not a.write)

        if not a.write:
            print("\nDRY RUN - nothing written (use --write)")
            return
        c.commit()
        print("\nupdated transfers=%d values=%d profiles=%d" % (n1, n2, n3))

        cur.execute("""SELECT p.full_name, t.transfer_date, t.from_club, t.to_club,
                              t.fee_eur, t.fee_usd, t.fx_rate
                       FROM player_transfers t JOIN players p ON p.id = t.player_id
                       WHERE t.fee_eur > 0
                       ORDER BY t.fee_eur DESC LIMIT 8""")
        print("\nbiggest fees now in both currencies:")
        for r in cur.fetchall():
            r = dict(r)
            print("   %-22s %s  %s -> %s   EUR %-12s USD %-12s @%.4f"
                  % (r["full_name"], r["transfer_date"], (r["from_club"] or "")[:16],
                     (r["to_club"] or "")[:16], format(r["fee_eur"], ","),
                     format(r["fee_usd"], ","), r["fx_rate"]))


if __name__ == "__main__":
    main()
