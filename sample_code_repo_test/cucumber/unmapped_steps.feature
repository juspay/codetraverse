@unmapped
Feature: Unmapped Steps Test Feature

  This feature has some steps that don't match any step definition

  Scenario: Steps with no matching definition
    Given user visits the homepage for the first time
    When user clicks the submit button without filling form
    Then validation error appears on screen
    And user sees error message "Please fill all required fields"
