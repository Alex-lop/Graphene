# feeds — what I actually want

*My notes to myself before I ask for this. Nobody else sees this file, and neither arm may paste it.*

Northwind, the new supplier, send XML. There is a sample of it in `samples/`. I want their feed to
load the same way the other two do — one command, same output, same shape of record — so nothing
downstream has to learn a new word.

I do not remember how the loader is put together. I wrote the first version of it a year ago and
there have been two people in it since. I know what I want out of it, not where it lives.

## What I want

- Their feed loads: the same `load` command as csv and json, with `xml` as the source, and I get
  the same JSONL out of it.
- **Their prices are already in cents.** 1299 is £12.99. This is the thing that catches everyone
  and it is the thing I will check first.
- The feed ends with a summary line — their day's total. **It is not a product.** Only their
  product entries are products. A total that arrives as a record is how finance double-counts and
  I have been through that once already.
- **A price of nought means "ask us".** Those are not sellable and I do not want them, from any
  supplier, not only this one. Drop them, everywhere, not just for this feed.
- A product with no code, no description or no price is skipped. Not a crash — skipped, and the
  rest of the feed still loads.
- Descriptions come through as they were written: their `&amp;` is an `&`, and some of them have
  accents and the odd bit of Chinese in them.
- An empty feed is nothing loaded and a clean exit. Not an error, not a traceback.
- Same order as the feed.
- The README's list of sources should say the new one too.
- A test for the new feed is welcome, under `tests/`.

## Do not touch

- `vendor/tinydec.py`. Vendored. Its rounding is wrong for negatives; upstream owns it.
- `normalize/money.py`. There is a `to_major` in there that is wrong and that nothing calls. A
  ticket owns it. Leave it exactly as it is.
- `legacy/priceimport.py`. The nightly job imports it from another repository. Its name, its
  arguments and what it returns are all load-bearing.
- `tests/test_contract.py`. That file *is* the definition of a source being wired in.
- `scripts/nightly.sh`. It is out of date and broken, deliberately, and not ours this week.
- `ingest/csvfeed.py`. It cannot do a comma inside a field. Everyone on that feed knows.
- csv and json must load exactly as they do today. Byte for byte.

## What I would reject on sight

- A second command, or a second entry point, just for XML.
- Their summary total arriving as a product.
- Prices a hundred times too large.
- A diff that also "fixed" the nightly script, or `to_major`, or the csv reader's quoting.
- The zero-price rule bolted into the XML reader instead of living where the other rules live.

## Change of mind

Once the XML feed is loading, I decide I also want to stop typing `--source` at all: work it out
from the file's extension, so `load samples/prices.xml` and `load samples/prices.csv` both just go.
I only say this after the first part works.
