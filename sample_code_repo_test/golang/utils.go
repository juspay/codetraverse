// utils.go
package utils

import (
    "fmt"
    "example.com/sample/models"
)

// GreetUser constructs a greeting for the given Person.
func GreetUser(p models.Person) string {
    models.Print(p)
    return fmt.Sprintf("Welcome, %s!", p.Greet())
}

// UtilFunc is the second link in the call chain.
func UtilFunc() {
    models.ModelFunc()
}
