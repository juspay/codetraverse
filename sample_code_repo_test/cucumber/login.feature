@login @smoke
Feature: User Login Feature

  As a registered user
  I want to login to the application
  So that I can access my account

  Background:
    Given the user is on the login page
  
  @valid
  Scenario: Successful login with valid credentials
    When the user enters username "testuser" and password "password123"
    And clicks the login button
    Then the user should be redirected to the dashboard
    And the welcome message should be displayed

  @invalid
  Scenario Outline: Login failure with invalid credentials
    Given the user is on the login page
    When the user enters username "<username>" and password "<password>"
    And clicks the login button
    Then an error message should be displayed
    And the user should remain on the login page

    Examples:
      | username | password   |
      | wrong    | password   |
      | testuser | wrongpass  |
      |          | password   |
