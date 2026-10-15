# Working in this repository

- Run the tests with `python3 -m unittest`.
- `vendor/` holds third-party code copied in from upstream releases, byte for byte. Never edit anything under
  `vendor/`: a fix there belongs upstream, and the next update would overwrite it. Work around it in `src/`.
