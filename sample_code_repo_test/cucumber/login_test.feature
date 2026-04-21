@login @smoke
Feature: User Login Feature

  Background:
    Given setup test environment

  @valid
  Scenario: Successful login with valid credentials
    Given user is on login page
    When user enters username "admin" and password "password123"
    And user clicks login button
    Then user should see dashboard

  @invalid
  Scenario: Login with invalid credentials
    Given user is on login page
    When user enters invalid credentials
    And user clicks login button
    Then user should see error message

  Scenario Outline: Login with different users
    Given user is already logged in with username "<username>"
    When user performs search for "<searchTerm>"
    Then search results should contain "<expectedResult>"

    Examples:
      | username | searchTerm | expectedResult |
      | admin    | products   | Product List   |
      | user1    | orders     | Order History  |
