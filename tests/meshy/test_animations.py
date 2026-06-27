"""Tests for Meshy animation catalog helpers."""

from __future__ import annotations

import pytest

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.meshy.animations import (
    ANIMATIONS,
    AnimationCategory,
    AnimationSubcategory,
    get_animation,
    get_animations_by_category,
    get_animations_by_subcategory,
)


def test_get_animation_returns_extended_payload() -> None:
    """Single animation lookup should expose extended mapping payloads."""
    action_id, raw_animation = next(iter(ANIMATIONS.items()))

    result = get_animation(action_id)

    assert isinstance(result, ExtendedDict)
    assert result["id"] == raw_animation.id
    assert result["name"] == raw_animation.name
    assert isinstance(result["name"], ExtendedString)
    assert result["preview_url"] == raw_animation.preview_url


def test_get_animations_by_category_returns_extended_payloads() -> None:
    """Category lookup should expose an extended list of extended mappings."""
    raw_animation = next(iter(ANIMATIONS.values()))

    result = get_animations_by_category(AnimationCategory(raw_animation.category))

    assert isinstance(result, ExtendedList)
    assert result
    assert all(isinstance(animation, ExtendedDict) for animation in result)
    assert all(animation["category"] == raw_animation.category for animation in result)
    assert isinstance(result[0]["subcategory"], ExtendedString)


def test_get_animations_by_subcategory_returns_extended_payloads() -> None:
    """Subcategory lookup should expose an extended list of extended mappings."""
    raw_animation = next(iter(ANIMATIONS.values()))

    result = get_animations_by_subcategory(AnimationSubcategory(raw_animation.subcategory))

    assert isinstance(result, ExtendedList)
    assert result
    assert all(isinstance(animation, ExtendedDict) for animation in result)
    assert all(animation["subcategory"] == raw_animation.subcategory for animation in result)
    assert isinstance(result[0]["name"], ExtendedString)


def test_get_animation_rejects_unknown_id() -> None:
    """Missing animations should remain explicit errors."""
    with pytest.raises(ValueError, match="Animation ID -1 not found"):
        get_animation(-1)
