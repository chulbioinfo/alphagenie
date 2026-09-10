"""Offline checks of bounded render caching and process-local request budgets."""
import threading
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.render_cache import RenderCache
from app.request_limits import RateBudget, is_render_path, is_retired_path


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class RenderCacheTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def cache(self, **kwargs):
        return RenderCache(clock=self.clock, **kwargs)

    def test_hit_including_empty_bytes_does_not_render_again(self):
        cache = self.cache()
        for key, content in (("figure", b"figure"), ("empty", b"")):
            with self.subTest(key=key):
                make = Mock(return_value=content)
                self.assertEqual(cache.get(key, make), content)
                self.assertEqual(cache.get(key, make), content)
                make.assert_called_once_with()
        self.assertEqual(cache.size, 6)

    def test_byte_bound_evicts_least_recently_used_entries(self):
        cache = self.cache(max_bytes=6, max_entries=10)
        cache.get("a", lambda: b"aa")
        cache.get("b", lambda: b"bb")
        cache.get("a", Mock(side_effect=AssertionError("cached hit")))
        self.assertEqual(cache.get("c", lambda: b"cccc"), b"cccc")
        self.assertEqual(list(cache.entries), ["a", "c"])
        self.assertEqual(cache.size, 6)
        self.assertEqual(cache.get("d", lambda: b"dddddd"), b"dddddd")
        self.assertEqual(list(cache.entries), ["d"])
        self.assertEqual(cache.size, 6)

    def test_count_bound_includes_zero_length_entries(self):
        cache = self.cache(max_entries=2)
        for key in ("a", "b", "c"):
            cache.get(key, lambda: b"")
        self.assertEqual(list(cache.entries), ["b", "c"])
        self.assertEqual(cache.size, 0)

    def test_oversized_result_is_returned_but_not_cached(self):
        cache = self.cache(max_bytes=3)
        cache.get("small", lambda: b"ok")
        make = Mock(return_value=b"large")
        self.assertEqual(cache.get("large", make), b"large")
        self.assertEqual(cache.get("large", make), b"large")
        self.assertEqual(make.call_count, 2)
        self.assertEqual(list(cache.entries), ["small"])
        self.assertEqual(cache.size, 2)

    def test_ttl_is_absolute_and_expires_at_boundary(self):
        cache = self.cache(ttl=10)
        make = Mock(side_effect=[b"old", b"newer"])
        self.assertEqual(cache.get("a", make), b"old")
        self.clock.advance(9)
        self.assertEqual(cache.get("a", make), b"old")
        self.clock.advance(1)
        self.assertEqual(cache.get("a", make), b"newer")
        self.assertEqual(make.call_count, 2)
        self.assertEqual(cache.size, 5)

    def test_expiry_sweeps_unrequested_entries_and_bytes(self):
        cache = self.cache(ttl=10)
        cache.get("a", lambda: b"old")
        cache.get("b", lambda: b"older")
        self.clock.advance(10)
        cache.get("c", lambda: b"new")
        self.assertEqual(list(cache.entries), ["c"])
        self.assertEqual(cache.size, 3)

    def test_validation_failure_is_cached_until_ttl(self):
        cache = self.cache(ttl=10)
        make = Mock(side_effect=HTTPException(422, "invalid options"))
        for age in (0, 9):
            self.clock.now = 100 + age
            with self.assertRaises(HTTPException) as caught:
                cache.get("bad", make)
            self.assertEqual(caught.exception.status_code, 422)
            self.assertEqual(caught.exception.detail, "invalid options")
        make.assert_called_once_with()
        self.clock.advance(1)
        self.assertEqual(cache.get("bad", lambda: b"fixed"), b"fixed")
        self.assertFalse(cache.errors)

    def test_validation_failure_cache_has_128_entry_bound(self):
        cache = self.cache()
        make = Mock(side_effect=HTTPException(422, "invalid options"))
        for key in range(129):
            with self.assertRaises(HTTPException):
                cache.get(key, make)
        self.assertEqual(list(cache.errors), list(range(1, 129)))
        self.assertFalse(cache.entries)
        self.assertEqual(cache.size, 0)
        with self.assertRaises(HTTPException):
            cache.get(128, make)
        self.assertEqual(make.call_count, 129)
        self.assertEqual(cache.get(0, lambda: b"retried"), b"retried")

    def test_non_validation_failures_are_not_cached_and_release_slot(self):
        for error in (HTTPException(503, "busy"), RuntimeError("render failed")):
            with self.subTest(error=type(error).__name__):
                cache = self.cache()
                make = Mock(side_effect=error)
                for _ in range(2):
                    with self.assertRaises(type(error)):
                        cache.get("a", make)
                self.assertEqual(make.call_count, 2)
                self.assertFalse(cache.errors)
                self.assertEqual(cache.get("a", lambda: b"retry"), b"retry")

    def test_clear_removes_content_and_failures(self):
        cache = self.cache()
        cache.get("good", lambda: b"cached")
        with self.assertRaises(HTTPException):
            cache.get("bad", Mock(side_effect=HTTPException(422, "bad")))
        cache.clear()
        self.assertEqual(cache.size, 0)
        self.assertFalse(cache.entries)
        self.assertFalse(cache.errors)
        self.assertEqual(cache.get("good", lambda: b"new"), b"new")
        self.assertEqual(cache.get("bad", lambda: b"fixed"), b"fixed")

    def test_single_flight_rejects_misses_but_allows_cached_hits(self):
        cache = self.cache()
        cache.get("hit", lambda: b"cached")
        entered, release = threading.Event(), threading.Event()
        results, failures = [], []

        def make():
            entered.set()
            if not release.wait(5):
                raise AssertionError("test did not release renderer")
            return b"rendered"

        def render():
            try:
                results.append(cache.get("active", make))
            except BaseException as exc:
                failures.append(exc)

        thread = threading.Thread(target=render, daemon=True)
        thread.start()
        try:
            self.assertTrue(entered.wait(5), "renderer did not start")
            for key in ("active", "other"):
                rejected = Mock(side_effect=AssertionError("must not render"))
                with self.assertRaises(HTTPException) as caught:
                    cache.get(key, rejected)
                self.assertEqual(caught.exception.status_code, 503)
                self.assertEqual(caught.exception.headers, {"Retry-After": "2"})
                rejected.assert_not_called()
            self.assertEqual(cache.get("hit", Mock(side_effect=AssertionError("cached hit"))), b"cached")
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(results, [b"rendered"])
        self.assertEqual(cache.get("other", lambda: b"next"), b"next")

    def test_manuscript_wrapper_keys_all_render_inputs_and_exposes_clear(self):
        from app import manuscript_view as view

        cache = self.cache()
        with patch.object(view, "RENDER_CACHE", cache), patch.object(
            view, "verified_context", return_value="context"
        ) as context, patch.object(view, "_figure_bytes", return_value=b"figure") as make:
            base = ("preset", "fingerprint", view.Options(), "svg", False)
            self.assertEqual(view._render_cached(*base), b"figure")
            self.assertEqual(view._render_cached(*base), b"figure")
            make.assert_called_once_with("context", base[2], "svg", top_only=False)
            context.assert_called_once_with("preset")
            for index, value in enumerate(("other", "changed", view.Options(width_mm=180), "png", True)):
                changed = list(base)
                changed[index] = value
                self.assertEqual(view._render_cached(*changed), b"figure")
            self.assertEqual(make.call_count, 6)
        self.assertIs(view._render_cached.cache_clear.__self__, view.RENDER_CACHE)


class RateBudgetTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def budget(self, **kwargs):
        return RateBudget(clock=self.clock, **kwargs)

    def test_per_client_limit_is_independent_and_denial_does_not_spend(self):
        budget = self.budget(per_client=2, total=10)
        self.assertTrue(budget.allow("a"))
        self.assertTrue(budget.allow("a"))
        self.assertFalse(budget.allow("a"))
        self.assertTrue(budget.allow("b"))
        self.assertEqual(len(budget.clients["a"]), 2)
        self.assertEqual(len(budget.clients["b"]), 1)
        self.assertEqual(len(budget.events), 3)

    def test_global_limit_applies_across_clients(self):
        budget = self.budget(per_client=10, total=3)
        for identity in ("a", "b", "c"):
            self.assertTrue(budget.allow(identity))
        self.assertFalse(budget.allow("a"))
        self.assertFalse(budget.allow("d"))
        self.assertNotIn("d", budget.clients)
        self.assertEqual(len(budget.events), 3)

    def test_client_and_global_budgets_reset_at_exact_window_boundary(self):
        budget = self.budget(per_client=1, total=1, seconds=10)
        self.assertTrue(budget.allow("a"))
        self.clock.advance(9)
        self.assertFalse(budget.allow("a"))
        self.assertFalse(budget.allow("b"))
        self.clock.advance(1)
        self.assertTrue(budget.allow("a"))
        self.clock.advance(10)
        self.assertTrue(budget.allow("b"))
        self.assertEqual(list(budget.clients), ["b"])
        self.assertEqual(list(budget.events), [120])

    def test_window_expires_individual_events_not_entire_client(self):
        budget = self.budget(per_client=2, total=10, seconds=10)
        self.assertTrue(budget.allow("a"))
        self.clock.advance(5)
        self.assertTrue(budget.allow("a"))
        self.clock.advance(5)
        self.assertTrue(budget.allow("a"))
        self.assertFalse(budget.allow("a"))
        self.assertEqual(list(budget.clients["a"]), [105, 110])
        self.assertEqual(list(budget.events), [105, 110])

    def test_client_bound_does_not_evict_active_identity_and_frees_on_expiry(self):
        budget = self.budget(per_client=1, total=10, max_clients=2, seconds=10)
        self.assertTrue(budget.allow("a"))
        self.assertTrue(budget.allow("b"))
        self.assertFalse(budget.allow("c"))
        self.assertFalse(budget.allow("a"))
        self.assertEqual(list(budget.clients), ["a", "b"])
        self.clock.advance(10)
        self.assertTrue(budget.allow("c"))
        self.assertEqual(list(budget.clients), ["c"])
        self.assertEqual(len(budget.events), 1)


class RequestPathTests(unittest.TestCase):
    def test_render_paths_match_only_complete_supported_routes(self):
        for path in (
            "/api/explorer/demo/curve.svg", "/api/explorer/demo/view-options",
            *(f"/api/explorer/demo/export/{kind}" for kind in ("pdf", "svg", "png")),
            "/api/single-variant/preset/demo/plot", "/api/single-variant/preset/demo/view-options",
            *(f"/api/single-variant/preset/demo/download/plot_{kind}" for kind in ("pdf", "svg", "png")),
        ):
            with self.subTest(path=path):
                self.assertTrue(is_render_path(path))
        for path in ("/api/explorer/demo", "/api/explorer/demo/export/jpg", "/api/explorer/demo/export/pdf/extra",
                     "/api/explorer//curve.svg", "/api/local/status", "/prefix/api/explorer/demo/curve.svg"):
            with self.subTest(path=path):
                self.assertFalse(is_render_path(path))

    def test_retired_paths_match_only_complete_known_routes(self):
        for path in ("/api/validate_variant", "/api/multi-variant/validate", "/api/track-selection/preview",
                     "/jobs/demo/plot", "/multi-jobs/demo/plot"):
            with self.subTest(path=path):
                self.assertTrue(is_retired_path(path))
        for path in ("/api/local/preflight", "/jobs/demo", "/jobs/demo/plot/extra", "/jobs//plot"):
            with self.subTest(path=path):
                self.assertFalse(is_retired_path(path))


if __name__ == "__main__":
    unittest.main()
