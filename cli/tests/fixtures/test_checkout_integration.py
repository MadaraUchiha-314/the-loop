"""Fixture integration test used by the scenarios-extractor tests.

Feature: Checkout pricing
Requirement: docs/specs/issue-11/requirements.md#R2

Scenario: Cart total includes regional tax
    Given a cart with one $10.00 item
    When the cart is priced in a 10% tax region
    Then the order total is $11.00
"""


def test_cart_total_includes_regional_tax():
    assert 10.00 * 1.10 == 11.0


def test_free_shipping_over_threshold():
    """
    Scenario: Free shipping over the threshold
        Given a cart subtotal of $60.00
        When the free-shipping threshold is $50.00
        Then shipping is $0.00
    """
    assert True
