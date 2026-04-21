@background @test
Feature: Background Test Feature

  Background:
    Given user is logged in as admin
    And user has admin permissions
    When user navigates to dashboard

  @smoke
  Scenario: First test scenario
    Given user selects option "A"
    Then action is performed successfully

  @regression
  Scenario: Second test scenario
    Given user selects option "B"
    Then action is performed successfully
