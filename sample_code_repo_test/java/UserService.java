package com.example;

/**
 * UserService handles user management operations.
 * This is a service class commonly used in test frameworks.
 */
public class UserService {
    
    private UserRepository userRepository;
    private ValidationService validationService;
    
    public UserService() {
        this.userRepository = new UserRepository();
        this.validationService = new ValidationService();
    }
    
    /**
     * Initialize the service
     */
    public void initialize() {
        userRepository.connect();
        validationService.setup();
    }
    
    /**
     * Create a new user
     * @param name User's name
     * @param email User's email
     * @return Created user
     */
    public User createUser(String name, String email) {
        if (!validationService.isValidEmail(email)) {
            throw new IllegalArgumentException("Invalid email format");
        }
        
        User user = new User(name, email);
        return userRepository.save(user);
    }
    
    /**
     * Find user by ID
     */
    public User findUserById(String id) {
        return userRepository.findById(id);
    }
    
    /**
     * Update user information
     */
    public User updateUser(String id, String name) {
        User user = userRepository.findById(id);
        if (user == null) {
            throw new UserNotFoundException("User not found: " + id);
        }
        
        user.setName(name);
        return userRepository.update(user);
    }
    
    /**
     * Delete a user
     */
    public boolean deleteUser(String id) {
        return userRepository.delete(id);
    }
}