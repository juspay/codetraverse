import io.cucumber.java.en.Given;
import io.cucumber.java.en.When;
import io.cucumber.java.en.Then;
import org.junit.Assert;
import utils.TestContext;
import utils.ReUsableMethods;
import pages.LoginPage;
import pages.DashboardPage;

public class StepDefs {

    public TestContext context;
    public LoginPage loginPage;
    public DashboardPage dashboardPage;

    public StepDefs(TestContext context) {
        this.context = context;
        this.loginPage = new LoginPage();
        this.dashboardPage = new DashboardPage();
    }

    @Given("user is on login page")
    public void userIsOnLoginPage() {
        loginPage.load();
        Assert.assertTrue(loginPage.isDisplayed());
    }

    @Given("user is already logged in with username {string}")
    public void userIsAlreadyLoggedIn(String username) {
        context.setup();
        loginPage.loginAs(username, "password123");
    }

    @When("user enters username {string} and password {string}")
    public void userEntersCredentials(String username, String password) {
        loginPage.enterUsername(username);
        loginPage.enterPassword(password);
    }

    @When("user clicks login button")
    public void userClicksLoginButton() {
        loginPage.clickLogin();
    }

    @When("user enters invalid credentials")
    public void userEntersInvalidCredentials() {
        loginPage.enterUsername("invalid");
        loginPage.enterPassword("wrong");
    }

    @Then("user should see dashboard")
    public void userShouldSeeDashboard() {
        Assert.assertTrue(dashboardPage.isDisplayed());
        ReUsableMethods.waitForPageLoad();
    }

    @Then("user should see error message")
    public void userShouldSeeErrorMessage() {
        String error = loginPage.getErrorMessage();
        Assert.assertEquals("Invalid credentials", error);
    }

    @Then("user should be logged out")
    public void userShouldBeLoggedOut() {
        Assert.assertFalse(dashboardPage.isDisplayed());
    }

    @Given("setup test environment")
    public void setupTestEnvironment() {
        context.setup();
        ReUsableMethods.initialize();
    }

    @When("user performs search for {string}")
    public void userPerformsSearch(String searchTerm) {
        dashboardPage.search(searchTerm);
    }

    @Then("search results should contain {string}")
    public void searchResultsShouldContain(String expected) {
        Assert.assertTrue(dashboardPage.hasResult(expected));
    }
}
