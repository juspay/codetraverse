// types.go
package types

// Role is a user role.
type Role string

const (
    // AdminRole represents administrative privileges.
    AdminRole Role = "admin"
    // UserRole represents a regular user.
    UserRole Role = "user"
)

// Name is an alias for string to represent person names.
type Name = string

// Greeter defines an interface for greeting behavior.
type Greeter interface {
    Greet() string
}

// DefaultRole is the default user role.
var DefaultRole Role = UserRole

// TypeFunc is the final link in the call chain.
func TypeFunc() string {
    return "chain complete"
}
