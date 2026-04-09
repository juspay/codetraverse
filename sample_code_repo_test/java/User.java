package com.example;

/**
 * User model class
 */
public class User {
    private String id;
    private String name;
    private String email;
    private boolean active;
    
    public User(String name, String email) {
        this.name = name;
        this.email = email;
        this.active = true;
    }
    
    public String getId() {
        return id;
    }
    
    public void setId(String id) {
        this.id = id;
    }
    
    public String getName() {
        return name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
    
    public String getEmail() {
        return email;
    }
    
    public void setEmail(String email) {
        this.email = email;
    }
    
    public boolean isActive() {
        return active;
    }
    
    public void setActive(boolean active) {
        this.active = active;
    }
}