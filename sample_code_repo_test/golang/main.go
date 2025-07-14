package main

import (
    "example.com/sample/models"
    "example.com/sample/utils"
    "example.com/sample/types"
    "fmt"
)

var AppName = "GoTraverse"

// main function: demonstrates calls, loops, struct, interface, etc.
func main() {
    fmt.Println("Starting application:", AppName)

    user := models.Person{ID: 1, Name: "Alice", Role: types.AdminRole}
    fmt.Println("User greeting:", utils.GreetUser(user))

    roles := []types.Role{types.AdminRole, types.UserRole}
    for _, r := range roles {
        fmt.Println("Role value:", r)
    }

    var greeter types.Greeter = &models.Person{ID: 2, Name: "Bob", Role: types.UserRole}
    fmt.Println("Greeter says:", greeter.Greet())
}
