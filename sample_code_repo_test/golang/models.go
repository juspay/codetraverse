package models

import (
    "fmt"
    "example.com/sample/types"
)

// Person represents a user in the system.
type Person struct {
    ID   int
    Name string
    Role types.Role
}

// Greet returns a greeting for the person.
func (p Person) Greet() string {
    return fmt.Sprintf("Hello, %s!", p.Name)
}

// SetName sets the Name field of Person.
func (p *Person) SetName(name string) {
    p.Name = name
}

// Print outputs the person's details.
func Print(p Person) {
    fmt.Println("Person details:", p.ID, p.Name, p.Role)
}
