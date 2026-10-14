# The brand assets

Graphene's mark is a small tree with one branch pruned, in two colours: ink `#141413` and ivory `#F0EEE6` (the mark's
muted tones are `#AEADA7` on ink and `#5E5D59` on ivory). Every file here comes in those two directions; `-on-ivory`
and `-on-ink` carry their own background, the plain ones are transparent.

- `mark/`: the mark alone, 64 by 64 (`docs/assets/graphene-mark-ink.svg` and `-ivory.svg` in the README are copies).
- `mark-small/`: the mark cut for small sizes (favicons, tab bars); `graphene-mark-small-currentColor.svg` takes the
  colour of the text around it.
- `lockup/`: the mark with the word, in a full and a small cut.
- `avatar/`: the mark on a 512 by 512 square, for a profile picture (SVG and PNG).
- `favicon/`: `favicon.svg`, `favicon.ico` and `apple-touch-icon.png`.
- `mock/`: `og-image` (the link preview, 1200 by 630) and `topbar-before`/`topbar-after` (the site's header with and
  without the lockup).
- `board.html` and `site-snippet.html`: a static mock of the board and the header snippet for the site; they are not
  part of the package.
