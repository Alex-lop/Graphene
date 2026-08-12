from app.auth.limiter import MAX_ATTEMPTS, WINDOW_SECONDS, should_block


def test_blocks_at_limit_inside_window():
    assert should_block(MAX_ATTEMPTS, WINDOW_SECONDS)


def test_allows_below_limit_or_after_window():
    assert not should_block(MAX_ATTEMPTS - 1, WINDOW_SECONDS)
    assert not should_block(MAX_ATTEMPTS, WINDOW_SECONDS + 1)
