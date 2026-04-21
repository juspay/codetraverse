@rule_test
Feature: Order Processing Feature

  Rule: Valid Order Processing
    Background:
      Given system is ready for orders

    Example: Processing valid order
      Given order contains valid items
      When order is submitted
      Then order is confirmed
      And order ID is generated

  Rule: Invalid Order Processing
    Example: Processing invalid order
      Given order contains invalid items
      When order is submitted
      Then order is rejected
      And error message is shown
