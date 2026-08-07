"""Unit tests for `config/semver.py` -- the semver RANGE ref -> concrete tag
resolver (item #2b): caret/tilde -> `packaging.specifiers.SpecifierSet`
mapping, and highest-matching-tag selection.
"""

from __future__ import annotations

import pytest

from copilot_cli.config.semver import (
    RangeResolutionError,
    range_to_specifier,
    resolve_range_to_tag,
)

# ------------------------------------------------------------------ #
# range_to_specifier -- caret
# ------------------------------------------------------------------ #


class TestCaretToSpecifier:
    def test_caret_major_pins_major(self):
        assert range_to_specifier("^1.4.5") == ">=1.4.5,<2.0.0"

    def test_caret_zero_major_pins_minor(self):
        assert range_to_specifier("^0.2.3") == ">=0.2.3,<0.3.0"

    def test_caret_zero_major_zero_minor_pins_patch(self):
        assert range_to_specifier("^0.0.3") == ">=0.0.3,<0.0.4"

    def test_caret_partial_major_minor(self):
        assert range_to_specifier("^1.x") == ">=1.0.0,<2.0.0"

    def test_caret_zero_major_wildcard_minor(self):
        assert range_to_specifier("^0.x") == ">=0.0.0,<1.0.0"

    def test_caret_zero_major_zero_minor_wildcard_patch(self):
        assert range_to_specifier("^0.0.x") == ">=0.0.0,<0.1.0"

    def test_caret_bare_major(self):
        assert range_to_specifier("^1") == ">=1.0.0,<2.0.0"


# ------------------------------------------------------------------ #
# range_to_specifier -- tilde
# ------------------------------------------------------------------ #


class TestTildeToSpecifier:
    def test_tilde_full_version_pins_minor(self):
        assert range_to_specifier("~1.2.3") == ">=1.2.3,<1.3.0"

    def test_tilde_major_minor_pins_minor(self):
        assert range_to_specifier("~1.2") == ">=1.2.0,<1.3.0"

    def test_tilde_bare_major_pins_major(self):
        assert range_to_specifier("~1") == ">=1.0.0,<2.0.0"


# ------------------------------------------------------------------ #
# range_to_specifier -- plain comparator passthrough
# ------------------------------------------------------------------ #


class TestPlainComparatorPassthrough:
    def test_single_comparator_passes_through_unchanged(self):
        assert range_to_specifier(">=1.4.5") == ">=1.4.5"

    def test_comma_joined_comparators_pass_through_unchanged(self):
        assert range_to_specifier(">=1.4.5,<2.0.0") == ">=1.4.5,<2.0.0"


# ------------------------------------------------------------------ #
# range_to_specifier -- malformed input
# ------------------------------------------------------------------ #


class TestMalformedRange:
    def test_non_numeric_caret_component_raises(self):
        with pytest.raises(RangeResolutionError):
            range_to_specifier("^abc.4.5")

    def test_missing_major_raises(self):
        with pytest.raises(RangeResolutionError):
            range_to_specifier("^.4.5")


# ------------------------------------------------------------------ #
# resolve_range_to_tag -- highest-matching-tag selection
# ------------------------------------------------------------------ #


class TestResolveRangeToTag:
    def test_caret_range_picks_highest_matching_tag(self):
        tags = ["v1.4.5", "v1.5.0", "v1.5.9", "v2.0.0"]
        assert resolve_range_to_tag("^1.4.5", tags) == "v1.5.9"

    def test_no_matching_tag_returns_none(self):
        tags = ["v0.9.0", "v0.9.9"]
        assert resolve_range_to_tag("^1.4.5", tags) is None

    def test_empty_tag_list_returns_none(self):
        assert resolve_range_to_tag("^1.4.5", []) is None

    def test_malformed_range_returns_none_not_raise(self):
        """`resolve_range_to_tag` never raises -- `config/sync.py` treats a
        `None` result as a clean skip, never a crash."""
        assert resolve_range_to_tag("^abc", ["v1.0.0"]) is None

    def test_non_semver_tags_are_silently_skipped(self):
        tags = ["release-candidate", "v1.4.5", "latest", "v1.5.0"]
        assert resolve_range_to_tag("^1.4.5", tags) == "v1.5.0"

    def test_tag_at_exact_lower_bound_matches(self):
        assert resolve_range_to_tag("^1.4.5", ["v1.4.5"]) == "v1.4.5"

    def test_tag_at_upper_bound_is_excluded(self):
        """`^1.4.5` excludes `2.0.0` -- the caret's whole point is pinning
        the major version."""
        assert resolve_range_to_tag("^1.4.5", ["v1.4.5", "v2.0.0"]) == "v1.4.5"

    def test_tilde_range_pins_minor_not_just_patch(self):
        tags = ["v1.2.3", "v1.2.9", "v1.3.0"]
        assert resolve_range_to_tag("~1.2.3", tags) == "v1.2.9"

    def test_unprefixed_tags_also_match(self):
        assert resolve_range_to_tag("^1.4.5", ["1.4.5", "1.5.0"]) == "1.5.0"


# ------------------------------------------------------------------ #
# resolve_range_to_tag -- prereleases are never selected by a range
# ------------------------------------------------------------------ #


class TestResolveRangeToTagExcludesPrereleases:
    def test_prerelease_tag_in_range_is_ignored_in_favor_of_stable(self):
        """A plain caret range resolves to the highest STABLE match -- a
        prerelease is only ever obtained by pinning an exact ref, never by
        a range (this is the #2b QA should-fix: `update` must not fan a
        prerelease like `v1.6.0-rc.1` out to every enrolled machine)."""
        tags = ["v1.4.5", "v1.5.0", "v1.6.0-rc.1"]
        assert resolve_range_to_tag("^1.4.5", tags) == "v1.5.0"

    def test_range_with_only_prerelease_candidates_returns_none(self):
        """No stable tag satisfies the range -- clean no-match, not a
        fallback to the prerelease."""
        tags = ["v1.4.5", "v1.6.0-rc.1"]
        assert resolve_range_to_tag("^1.6.0", tags) is None

    def test_stable_tag_equal_to_prerelease_base_is_still_chosen(self):
        """The final stable release of a version that also has a
        prerelease tag is a normal, valid match."""
        tags = ["v1.6.0-rc.1", "v1.6.0"]
        assert resolve_range_to_tag("^1.6.0", tags) == "v1.6.0"
